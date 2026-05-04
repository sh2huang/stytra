import numpy as np
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QBrush, QColor
from stytra.stimulation.stimuli import VisualStimulus, InterpolatedStimulus


def _mm_px_xy(experiment):
    calibrator = getattr(experiment, "calibrator", None)
    if calibrator is None:
        return 1.0, 1.0

    return max(float(calibrator.mm_px_x), 1e-9), max(float(calibrator.mm_px_y), 1e-9)

class DotDisplay(VisualStimulus, InterpolatedStimulus):
    def __init__(
        self,
        *args,
        dot_density=0.03,
        dot_radius=1,
        color_dots=(255, 255, 255),
        color_bg=(0, 0, 0),
        velocity=3,
        coherence=0,
        theta=0,
        max_coherent_for=0.5,
        display_size=(100, 100),
        **kwargs
    ):
        """
        Abstract class for display of dot populations

        Parameters
        ----------
        args
        dot_density
            number of dots per mm squared
        dot_radius
            dot radius in mm
        color_dots
            the color of the dots
        color_bg
            the color of the background
        velocity
            motion velocity in mm/s
        coherence
            default coherence (1: dots all move leftwards, -1: dots all move
            rightwards), for intermediate coherences a proportion of the dots
            move randomly
        theta
            angle of the display
        max_coherent_for
            number of seconds after a dot disappears and reappears in another
            location
        display_size
            size of display surface in millimiters
        kwargs
        """

        super().__init__(*args, **kwargs)
        self.dynamic_parameters.extend(["coherence", "frozen"])
        self.dot_density = dot_density
        self.dot_radius = dot_radius
        self.color_dots = color_dots
        self.color_bg = color_bg
        self.velocity = velocity
        self.max_coherent_for = max_coherent_for
        self.coherence = coherence
        self.display_size_mm = display_size
        self.display_size_px = np.array(display_size, dtype=np.int32)
        self.name = "random_dots"
        self.dots = None
        self.coherent_for = None
        self.frozen = 0
        self.theta = theta
        self.radius_px_x = self.dot_radius
        self.radius_px_y = self.dot_radius

    def get_dimensions(self):
        """
        Uses calibration data to calculate dimensions in pixels

        Returns
        -------
        number of dots to display and the displacement amount in pixel coordinates
        """
        mm_px_x, mm_px_y = _mm_px_xy(self._experiment)

        self.display_size_px = np.round(
            np.array(
                [
                    self.display_size_mm[0] / mm_px_x,
                    self.display_size_mm[1] / mm_px_y,
                ]
            )
        ).astype(np.int32)
        self.radius_px_x = int(round(self.dot_radius / mm_px_x))
        self.radius_px_y = int(round(self.dot_radius / mm_px_y))

        n_dots = int(
            round(self.display_size_mm[0] * self.display_size_mm[1] * self.dot_density)
        )

        return n_dots

    def step_vectors_mm(self, angles):
        return (
            np.stack([np.cos(angles), np.sin(angles)], 1) * self._dt * self.velocity
        )

    def step_vector_mm(self, theta):
        return self._dt * self.velocity * np.array([np.cos(theta), np.sin(theta)])

    def paint_dots(self, p, w, h):
        mm_px_x, mm_px_y = _mm_px_xy(self._experiment)
        p.setBrush(QBrush(QColor(*self.color_dots)))

        dw = w / 2 - self.display_size_px[0] / 2
        dh = h / 2 - self.display_size_px[1] / 2

        for i_point in range(self.dots.shape[0]):
            p.drawEllipse(
                QPointF(
                    self.dots[i_point, 0] / mm_px_x + dw,
                    self.dots[i_point, 1] / mm_px_y + dh,
                ),
                self.radius_px_x,
                self.radius_px_y,
            )


class RandomDotKinematogram(DotDisplay):
    """Moving dots where the motion coherence and persistence can be controlled"""

    def update(self):
        super().update()

        n_dots = self.get_dimensions()

        if self.dots is None:
            self.dots = np.random.rand(n_dots, 2) * np.array(self.display_size_mm)[
                None, :
            ]
            self.coherent_for = np.random.rand(n_dots) * self.max_coherent_for

        if self.frozen > 0:
            return None

        # select which dots are reset, and which are to be moved
        # in a coherent or random direction
        to_reset = self.coherent_for > self.max_coherent_for
        n_reset = np.sum(to_reset)
        coherent = np.random.rand(n_dots) < np.abs(self.coherence)

        # put random coordinates and lifetimes on the dots to be reset
        self.dots[to_reset, :] = np.random.rand(n_reset, 2) * np.array(
            self.display_size_mm
        )[None, :]
        self.coherent_for[to_reset] = np.random.rand(n_reset) * self.max_coherent_for

        # move the coherently moving dots in one direction
        coherent_sel = np.logical_and(np.logical_not(to_reset), coherent)
        coherent_angle = self.theta + (np.sign(self.coherence) < 0) * np.pi
        self.dots[coherent_sel, :] += self.step_vectors_mm(
            np.full(np.sum(coherent_sel), coherent_angle)
        )

        # move the randomly moving dots in random directions
        sel_random_motion = np.logical_and(
            np.logical_not(to_reset), np.logical_not(coherent)
        )
        angles = np.random.rand(np.sum(sel_random_motion)) * (2 * np.pi)
        self.dots[sel_random_motion, :] += self.step_vectors_mm(angles)

        # wrap the dots around if they exceed the boundaries of the drawing area
        for dim in [0, 1]:
            self.dots[:, dim] = np.remainder(
                self.dots[:, dim], self.display_size_mm[dim]
            )

        # record the lifetime of a dot
        self.coherent_for[np.logical_not(to_reset)] += self._dt

    def paint(self, p, w, h):
        # draw background
        p.resetTransform()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(*self.color_bg)))

        self.clip(p, w, h)
        p.drawRect(QRectF(-1.0, -1.0, float(w) + 2.0, float(h) + 2.0))

        self.paint_dots(p, w, h)


class ContinuousRandomDotKinematogram(DotDisplay):
    def __init__(self, *args, theta_relative=0, **kwargs):
        """A version of the random dot kinematogram, as above, but with two
        improvements:

        1) dots which are chose to move coherently keep moving in
           the same direction through their lifetime

        2) coherent motion is defined directly in screen physical coordinates, so
           anisotropic x/y calibration does not distort motion direction

        Parameters
        ----------

        theta_relative
            an amount of extra rotation
        """
        super().__init__(*args, **kwargs)
        self.is_coherent = None
        self.previous_coherence = None
        self.theta_relative = theta_relative

    def update(self):
        super().update()

        # get space and time dimensions
        n_dots = self.get_dimensions()

        if self.dots is None:
            self.dots = np.random.rand(n_dots, 2) * np.array(self.display_size_mm)[
                None, :
            ]
            self.coherent_for = np.random.rand(n_dots) * self.max_coherent_for
            self.is_coherent = np.random.rand(n_dots) < np.abs(self.coherence)

        if self.frozen > 0:
            return None

        if self.previous_coherence != self.coherence:
            self.is_coherent = np.random.rand(n_dots) < np.abs(self.coherence)

        # select which dots are reset, and which are to be moved
        # in a coherent or random direction
        to_reset = self.coherent_for > self.max_coherent_for
        n_reset = np.sum(to_reset)

        # put random coordinates and lifetimes on the dots to be reset
        self.dots[to_reset, :] = np.random.rand(n_reset, 2) * np.array(
            self.display_size_mm
        )[None, :]
        self.coherent_for[to_reset] = np.random.rand(n_reset) * self.max_coherent_for

        # move the coherently moving dots in one direction
        theta_mov = (
            self.theta + self.theta_relative + (np.sign(self.coherence) < 0) * np.pi
        )
        coherent_sel = np.logical_and(np.logical_not(to_reset), self.is_coherent)
        self.dots[coherent_sel, :] += self.step_vector_mm(theta_mov)[None, :]

        # move the randomly moving dots in random directions
        sel_random_motion = np.logical_and(
            np.logical_not(to_reset), np.logical_not(self.is_coherent)
        )
        angles = np.random.rand(np.sum(sel_random_motion)) * (2 * np.pi)
        self.dots[sel_random_motion, :] += self.step_vectors_mm(angles)

        # wrap the dots around if they exceed the boundaries of the drawing area
        for dim in [0, 1]:
            self.dots[:, dim] = np.remainder(
                self.dots[:, dim], self.display_size_mm[dim]
            )

        # record the lifetime of a dot
        self.coherent_for[np.logical_not(to_reset)] += self._dt
        self.previous_coherence = self.coherence

    def paint(self, p, w, h):
        # draw background
        p.resetTransform()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(*self.color_bg)))

        self.clip(p, w, h)
        p.drawRect(QRectF(-1.0, -1.0, float(w) + 2.0, float(h) + 2.0))

        self.paint_dots(p, w, h)
