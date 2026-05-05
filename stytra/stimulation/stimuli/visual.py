from numbers import Real

import numpy as np
import pims
import qimage2ndarray
from pathlib import Path

from PyQt5.QtCore import QPoint, QRectF, QPointF, QLineF, Qt
from PyQt5.QtGui import (
    QPainter,
    QBrush,
    QColor,
    QPen,
    QPolygon,
    QPolygonF,
    QRegion,
)

from stytra.stimulation.stimuli import (
    Stimulus,
    DynamicStimulus,
    InterpolatedStimulus,
    CombinerStimulus,
)
from stytra.stimulation.stimuli.backgrounds import existing_file_background


def _mm_px_xy(experiment):
    calibrator = getattr(experiment, "calibrator", None)
    if calibrator is None:
        return 1.0, 1.0

    return max(float(calibrator.mm_px_x), 1e-9), max(float(calibrator.mm_px_y), 1e-9)


def _screen_mm_axes(w, h, experiment):
    mm_px_x, mm_px_y = _mm_px_xy(experiment)
    x_mm = (np.arange(w) - w / 2) * mm_px_x
    y_mm = (np.arange(h) - h / 2) * mm_px_y
    return x_mm, y_mm


def _local_mm_coords(w, h, experiment, theta=0, x=0, y=0):
    x_mm, y_mm = _screen_mm_axes(w, h, experiment)
    x_grid, y_grid = np.meshgrid(x_mm, y_mm)

    local_x = np.cos(theta) * x_grid + np.sin(theta) * y_grid - x
    local_y = -np.sin(theta) * x_grid + np.cos(theta) * y_grid - y

    return local_x, local_y


class VisualStimulus(Stimulus):
    """Stimulus class to paint programmatically on a canvas.
    For this subclass of Stimulus, their core function (paint()) is
    not called by the ProtocolRunner, but directly from the
    StimulusDisplayWindow. Since a StimulusDisplayWindow is directly linked to
    a ProtocolRunner, at every time the paint() method that is called
    is the one from the correct current stimulus.

    Parameters
    ----------
    clip_mask :
        mask for clipping the stimulus. Unfortunately we cannot pass a QPolygon here,
        se to allow for some flexibility there are some heuristics to figure out the
        clipping shape depending on the argument type and dimensions.
        There's tree possible cases for the mask:
            - **Circular mask**: If `clip_mask` is a single number, or a tuple of three numbers, the
              mask will be a circle.
              - A single number specifies the diameter of the circle,
                in relative screen size units;
              - A tuple of three numbers specifies center x, y and diameter of the circle,
                in  relative screen size units.

            - **Polygon mask**: If `clip_mask` is a list of tuples with 2 elements each, the mask will
              be a polygon that uses the tuples of the list as (x, y) coordinates
              (there should be at least three elements there)

            - **Rectangular mask**: If `clip_mask` is a tuple of four numbers, the mask will be a rectangle
              that interprets the coordinates as (x_pos, y_pos, width, height).

    Returns
    -------

    """

    def __init__(self, *args, clip_mask=None, **kwargs):
        """ """
        super().__init__(*args, **kwargs)
        self.clip_mask = clip_mask

    def paint(self, p, w, h):
        """Paint function. Called by the StimulusDisplayWindow update method
        (NOT by the `ProtocolRunner.update()` !).

        Parameters
        ----------
        p : QPainter object
            Painter object for drawing
        w :
            width of the display window
        h :
            height of the display window

        Returns
        -------

        """
        pass

    @staticmethod
    def _full_field_rect(w, h):
        return QRectF(-1.0, -1.0, float(w) + 2.0, float(h) + 2.0)

    def clip(self, p, w, h):
        """Clip image before painting

        Parameters
        ----------
        p :
            QPainter object used for painting
        w :
            image width
        h :
            image height

        Returns
        -------

        """
        if self.clip_mask is not None:
            if isinstance(self.clip_mask, Real):  # centered circle
                diameter_x = float(self.clip_mask) * w * 2
                diameter_y = float(self.clip_mask) * h * 2
                a = QRegion(
                    int(round(w / 2 - diameter_x / 2)),
                    int(round(h / 2 - diameter_y / 2)),
                    int(round(diameter_x)),
                    int(round(diameter_y)),
                    type=QRegion.Ellipse,
                )
                p.setClipRegion(a)
            elif len(self.clip_mask) == 3 and all(
                isinstance(v, Real) for v in self.clip_mask
            ):
                centre_x, centre_y, diameter = self.clip_mask
                diameter_x = float(diameter) * w
                diameter_y = float(diameter) * h
                a = QRegion(
                    int(round(float(centre_x) * w - diameter_x / 2)),
                    int(round(float(centre_y) * h - diameter_y / 2)),
                    int(round(diameter_x)),
                    int(round(diameter_y)),
                    type=QRegion.Ellipse,
                )
                p.setClipRegion(a)
            elif isinstance(self.clip_mask[0], tuple):  # polygon
                points = [QPoint(int(w * x), int(h * y)) for (x, y) in self.clip_mask]
                p.setClipRegion(QRegion(QPolygon(points)))
            else:
                p.setClipRect(
                    QRectF(
                        float(self.clip_mask[0]) * w,
                        float(self.clip_mask[1]) * h,
                        float(self.clip_mask[2]) * w,
                        float(self.clip_mask[3]) * h,
                    )
                )


class VisualCombinerStimulus(VisualStimulus, CombinerStimulus):
    """
    Class to have two visual stimuli happening pseudo-simultaneously (one update
    still has to be called before the other one).
    """

    def paint(self, p, w, h):
        for s in self._stim_list:
            s.paint(p, w, h)
            # p.end()


class FullFieldVisualStimulus(VisualStimulus):
    """Class for painting a full field flash of a specific color.

    Parameters
    ----------
    color : (int, int, int) tuple
         color of the full field flash (int tuple)
    """

    def __init__(self, *args, color=(255, 0, 0), **kwargs):
        """ """
        super().__init__(*args, **kwargs)
        self.color = color
        self.name = "flash"

    def paint(self, p, w, h):
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(*self.color)))  # Use chosen color
        self.clip(p, w, h)
        p.drawRect(self._full_field_rect(w, h))  # draw full field rectangle


class DynamicLuminanceStimulus(FullFieldVisualStimulus, InterpolatedStimulus):
    """A luminance stimulus that has dynamically specified luminance.


    Parameters
    ----------

    luminance: float
        a multiplier (0-1) from black to full luminance



    """

    def __init__(self, *args, color=(255, 0, 0), luminance=0.0, **kwargs):
        self.luminance = luminance
        super().__init__(*args, dynamic_parameters=["luminance"], **kwargs)
        self.original_color = np.array(color)
        self.color = color
        self.name = "luminance"

    def update(self):
        super().update()
        self.color = tuple(self.luminance * self.original_color)


class Pause(FullFieldVisualStimulus):
    """Class for painting full field black stimuli."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, color=(0, 0, 0), **kwargs)
        self.name = "pause"


class VideoStimulus(VisualStimulus, DynamicStimulus):
    """Displays videos using PIMS, at a specified framerate."""

    def __init__(self, *args, video_path, framerate=None, duration=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.name = "video"

        self.dynamic_parameters.append("i_frame")
        self.i_frame = 0
        self.video_path = video_path

        self._current_frame = None
        self._last_frame_display_time = 0
        self._video_seq = None

        self.framerate = framerate
        self.duration = duration

    def initialise_external(self, *args, **kwargs):
        super().initialise_external(*args, **kwargs)
        self._video_seq = pims.Video(self._experiment.asset_dir + "/" + self.video_path)

        self._current_frame = self._video_seq.get_frame(self.i_frame)
        try:
            metadata = self._video_seq.get_metadata()

            if self.framerate is None:
                self.framerate = metadata["fps"]
            if self.duration is None:
                self.duration = metadata["duration"]

        except AttributeError:
            if self.framerate is None:
                self.framerate = self._video_seq.frame_rate

            if self.duration is None:
                self.duration = self._video_seq.duration

    def update(self):
        super().update()
        # if the video restarted, it means the last display time
        # is incorrect, it has to be reset
        if self._elapsed < self._last_frame_display_time:
            self._last_frame_display_time = 0
        if self._elapsed >= self._last_frame_display_time + 1 / self.framerate:
            self.i_frame = int(round(self._elapsed * self.framerate))
            next_frame = self._video_seq.get_frame(self.i_frame)
            if next_frame is not None:
                self._current_frame = next_frame
                self._last_frame_display_time = self._elapsed

    def paint(self, p, w, h):
        display_centre = (w / 2, h / 2)
        img = qimage2ndarray.array2qimage(self._current_frame)
        p.drawImage(
            QPointF(
                float(display_centre[0] - self._current_frame.shape[1] / 2),
                float(display_centre[1] - self._current_frame.shape[0] / 2),
            ),
            img,
        )


class PositionStimulus(VisualStimulus, DynamicStimulus):
    """Stimulus with a defined position and orientation to the fish."""

    def __init__(self, *args, x=0, y=0, theta=0, **kwargs):
        """ """
        self.x = x
        self.y = y
        self.theta = theta
        super().__init__(*args, dynamic_parameters=["x", "y", "theta"], **kwargs)


class BackgroundStimulus(PositionStimulus):
    """Stimulus with a tiling background"""

    def __init__(self, *args, background_color=(0, 0, 0), **kwargs):
        self.background_color = background_color
        super().__init__(*args, **kwargs)

    def screen_mm_axes(self, w, h):
        mm_px_x, mm_px_y = _mm_px_xy(self._experiment)
        return np.arange(w) * mm_px_x, np.arange(h) * mm_px_y

    def rotation_centre_mm(self, w, h):
        return 0.0, 0.0

    def local_mm_coords(self, w, h):
        x_mm, y_mm = self.screen_mm_axes(w, h)
        x_grid, y_grid = np.meshgrid(x_mm, y_mm)

        centre_x, centre_y = self.rotation_centre_mm(w, h)
        x_shifted = x_grid - centre_x
        y_shifted = y_grid - centre_y

        cos_theta = np.cos(self.theta)
        sin_theta = np.sin(self.theta)

        local_x = cos_theta * x_shifted + sin_theta * y_shifted + centre_x - self.x
        local_y = -sin_theta * x_shifted + cos_theta * y_shifted + centre_y - self.y

        return local_x, local_y

    def background_image(self, w, h, local_x, local_y):
        return None

    def paint(self, p, w, h):
        p.resetTransform()
        self.clip(p, w, h)

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(*self.background_color)))
        p.drawRect(self._full_field_rect(w, h))

        image = self.background_image(w, h, *self.local_mm_coords(w, h))
        if image is not None:
            p.drawImage(QPointF(0.0, 0.0), qimage2ndarray.array2qimage(image))


class CenteredBackgroundStimulus(BackgroundStimulus):
    def rotation_centre_mm(self, w, h):
        mm_px_x, mm_px_y = _mm_px_xy(self._experiment)
        return (w / 2) * mm_px_x, (h / 2) * mm_px_y


class BaseSeamlessImageStimulus:
    """Displays an image which should tile seamlessly.

    The top of the image should match with the bottom and the left
    with the right, so there are no discontinuities). An even checkerboard
    works, but with
    some image editing any texture can be adjusted to be seamless.
    """

    def __init__(self, *args, background, background_name=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "seamless_image"
        self._background = background
        if background_name is not None:
            self.background_name = background_name
        else:
            if isinstance(background, str):
                self.background_name = background
            elif isinstance(background, Path):
                self.background_name = background.name
            else:
                self.background_name = "array {}x{}".format(*self._background.shape)
        self._background_array = None

    def initialise_external(self, experiment):
        super().initialise_external(experiment)

        if isinstance(self._background, str):
            self._background_array = np.asarray(
                existing_file_background(
                    self._experiment.asset_dir + "/" + self._background
                )
            )
        elif isinstance(self._background, Path):
            self._background_array = np.asarray(
                existing_file_background(self._background)
            )
        else:
            self._background_array = np.asarray(self._background)

    def background_image(self, w, h, local_x, local_y):
        mm_px_x, mm_px_y = _mm_px_xy(self._experiment)
        bg_h, bg_w = self._background_array.shape[:2]

        x_px = np.floor(np.mod(local_x, bg_w * mm_px_x) / mm_px_x).astype(int) % bg_w
        y_px = np.floor(np.mod(local_y, bg_h * mm_px_y) / mm_px_y).astype(int) % bg_h

        return self._background_array[y_px, x_px]


class SeamlessImageStimulus(BaseSeamlessImageStimulus, BackgroundStimulus):
    pass


class CenteredSeamlessImageStimulus(
    BaseSeamlessImageStimulus, CenteredBackgroundStimulus
):
    pass


class GratingStimulus(BackgroundStimulus):
    """Class for creating a grating pattern by tiling a numpy array that
    defines the stimulus profile. Can be square or sinusoidal.
    For having moving grating stimulus, use subclass MovingGratingStimulus.

    Parameters
    ----------
    grating_angle : float
        fixed angle for the stripes (in radiants)
    grating_period : float
        spatial period of the gratings (in mm)
    grating_col_1 : (int, int, int) tuple
        first color (default=(255, 255, 255))
    grating_col_2 : (int, int, int) tuple
        second color (default=(0, 0, 0))
    """

    def __init__(
        self,
        *args,
        grating_angle=0,
        grating_period=10,
        wave_shape="square",
        grating_col_1=(255,) * 3,
        grating_col_2=(0,) * 3,
        **kwargs
    ):
        super().__init__(*args, background_color=grating_col_2, **kwargs)
        self.theta = grating_angle
        self.grating_period = grating_period
        self.wave_shape = wave_shape
        self.color_1 = grating_col_1
        self.color_2 = grating_col_2
        self._pattern = None
        self.name = "gratings"

    def _weights(self, local_x):
        phase = np.mod(local_x, self.grating_period) / self.grating_period

        if self.wave_shape == "square":
            return (phase < 0.5).astype(float)
        elif self.wave_shape == "sine":
            return (np.sin(2 * np.pi * phase) + 1.0) / 2.0
        else:
            raise ValueError("Unsupported wave shape {}".format(self.wave_shape))

    def paint(self, p, w, h):
        local_x, _ = _local_mm_coords(
            w, h, self._experiment, theta=self.theta, x=self.x, y=self.y
        )
        weights = self._weights(local_x)

        image = (
            weights[:, :, None] * np.array(self.color_1)[None, None, :]
            + (1 - weights)[:, :, None] * np.array(self.color_2)[None, None, :]
        ).astype(np.uint8)

        p.setPen(Qt.NoPen)
        self.clip(p, w, h)
        p.drawImage(QPointF(0.0, 0.0), qimage2ndarray.array2qimage(image))


class PaintGratingStimulus(BackgroundStimulus):
    """Class for creating a grating pattern drawing rectangles with PyQt.
    Note that this class does not move
    the grating pattern, to move you need to subclass this together with a dynamic
    stimulus where the x of the gratings is changing (see `MovingGratingStimulus`).

    """

    def __init__(
        self,
        *args,
        grating_angle=0,
        grating_period=10,
        grating_col_1=(255, 255, 255),
        grating_col_2=(0, 0, 0),
        **kwargs
    ):
        """
        :param grating_angle: fixed angle for the stripes
        :param grating_period: spatial period of the gratings (unit?)
        :param grating_color: color for the non-black stripes (int tuple)
        """
        super().__init__(*args, background_color=grating_col_2, **kwargs)
        self.theta = grating_angle
        self.grating_period = grating_period
        self.color = grating_col_1
        self.name = "moving_gratings"
        self.barheight = 100

    def paint(self, p, w, h):
        local_x, _ = _local_mm_coords(
            w, h, self._experiment, theta=self.theta, x=self.x, y=self.y
        )
        mask = np.mod(local_x, self.grating_period) < (self.grating_period / 2.0)

        image = np.zeros((h, w, 3), dtype=np.uint8)
        image[:, :, :] = self.background_color
        image[mask] = self.color

        p.setPen(Qt.NoPen)
        p.setRenderHint(QPainter.Antialiasing)
        self.clip(p, w, h)
        p.drawImage(QPointF(0.0, 0.0), qimage2ndarray.array2qimage(image))


class MovingGratingStimulus(PaintGratingStimulus, InterpolatedStimulus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dynamic_parameters.append("x")


class HalfFieldStimulus(PositionStimulus):
    """Phototaxis stimulus which fill half visual field
    with a white background.
    """

    def __init__(
        self, *args, left=False, color=(255, 255, 255), center_dist=0, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.left = left
        self.center_dist = center_dist
        self.color = color
        self.name = "half_field"

    def paint(self, p, w, h):
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(*self.color)))
        p.setRenderHint(QPainter.Antialiasing)

        points = []
        if self.left:
            dtheta = np.pi / 2
        else:
            dtheta = -np.pi / 2

        theta = self.theta

        sx = (
            self.x
            + h / 2 * np.cos(theta)
            + self.center_dist * np.cos(theta - np.pi / 2)
        )
        sy = (
            self.y
            + h / 2 * np.sin(theta)
            + self.center_dist * np.sin(theta - np.pi / 2)
        )
        points.append(QPointF(float(sx), float(sy)))
        theta += dtheta

        sx += w * np.cos(theta)
        sy += w * np.sin(theta)
        points.append(QPointF(float(sx), float(sy)))
        theta += dtheta

        sx += h * np.cos(theta)
        sy += h * np.sin(theta)
        points.append(QPointF(float(sx), float(sy)))
        theta += dtheta

        sx += w * np.cos(theta)
        sy += w * np.sin(theta)
        points.append(QPointF(float(sx), float(sy)))
        theta += dtheta

        sx += h * np.cos(theta)
        sy += h * np.sin(theta)
        points.append(QPointF(float(sx), float(sy)))

        poly = QPolygonF(points)
        p.drawPolygon(poly)


class RadialSineStimulus(VisualStimulus):
    """Circular grating pattern that moves concentrically
    which makes the fish move to the center of the dish.

    """

    def __init__(self, period=8, velocity=5, duration=1, **kwargs):
        super().__init__(**kwargs)
        self.phase = 0
        self.velocity = velocity
        self.duration = duration
        self.period = period
        self.phase = 0
        self.image = None
        self.name = "radial_sine_centering"
        self._dt = 0
        self._past_t = 0

    def update(self):
        self._dt = self._elapsed - self._past_t
        self._past_t = self._elapsed
        self.phase += self._dt * self.velocity

    def paint(self, p, w, h):
        x, y = _screen_mm_axes(w, h, self._experiment)
        radius = np.sqrt(x[None, :] ** 2 + y[:, None] ** 2)
        self.image = np.round(
            (np.sin(2 * np.pi * radius / self.period + self.phase) + 1.0) * 127
        ).astype(np.uint8)
        p.drawImage(QPointF(0.0, 0.0), qimage2ndarray.array2qimage(self.image))


class FishOverlayStimulus(PositionStimulus):
    """For testing freely-swimming closed loop, draws a fish in the corresponding
    region on the projector.

    """

    def __init__(self, color=(255, 50, 0), **kwargs):
        super().__init__(**kwargs)
        self.color = color
        self.name = "fish_overlay"

    def paint(self, p, w, h):
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(*self.color)))
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.drawEllipse(QPointF(self.x, self.y), 1.5, 1.5)
        p.setPen(QPen(QColor(*self.color)))
        l = 20
        p.drawLine(
            QLineF(
                self.x,
                self.y,
                self.x + np.cos(self.theta) * l,
                self.y + np.sin(self.theta) * l,
            )
        )

class WindmillStimulus(CenteredBackgroundStimulus):
    """Class for drawing a rotating windmill (radial wedges in alternating colors).
    For moving gratings use subclass

    Parameters
    ----------
    n_arms : int
        number of colored arms of the windmill
    color : (int, int, int) tuple
        color for the non-black stripes (int tuple)

    """

    def __init__(
        self,
        *args,
        color_1=(255,) * 3,
        wave_shape="sinusoidal",
        color_2=(0,) * 3,
        n_arms=8,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.color_1 = color_1
        self.color_2 = color_2
        self.n_arms = n_arms
        self.wave_shape = wave_shape
        self.name = "windmill"
        self._pattern = None

    def _weights(self, local_x, local_y):
        angle = np.arctan2(local_y, local_x)
        weights = (np.cos(self.n_arms * angle) + 1.0) / 2.0

        if self.wave_shape == "square":
            return (weights >= 0.5).astype(float)

        return weights

    def paint(self, p, w, h):
        local_x, local_y = _local_mm_coords(
            w, h, self._experiment, theta=self.theta, x=self.x, y=self.y
        )
        weights = self._weights(local_x, local_y)
        image = (
            weights[:, :, None] * np.array(self.color_1)[None, None, :]
            + (1 - weights)[:, :, None] * np.array(self.color_2)[None, None, :]
        ).astype(np.uint8)

        p.setPen(Qt.NoPen)
        self.clip(p, w, h)
        p.drawImage(QPointF(0.0, 0.0), qimage2ndarray.array2qimage(image))


class MovingWindmillStimulus(WindmillStimulus, InterpolatedStimulus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dynamic_parameters.append("theta")


class HighResWindmillStimulus(CenteredBackgroundStimulus):
    """Class for drawing a rotating windmill with sharp edges.
    Instead of rotating an image, this class use a painter to draw triangles
    of the windmill at every timestep.
    Compared with the WindmillStimulus class, this windmill has better
    resolution because it avoids distortions and artifacts from image rotation.
    On the other side, it cannot be used for sinusoidal windmill and
    currently does not support a different background color, and takes
    slightly longer to draw the stimulus
    Ideally will be obsolete once the problems of the WindmillStimulus class
    are solved.

    Parameters
    ----------
    n_arms : int
        number of colored arms of the windmill
    color : (int, int, int) tuple
        color for the non-black stripes (int tuple)

    """

    def __init__(self, *args, color=(255,) * 3, n_arms=8, **kwargs):
        super().__init__(*args, **kwargs)
        self.color = color
        self.n_arms = n_arms
        self.name = "windmill"

    def paint(self, p, w, h):
        local_x, local_y = _local_mm_coords(
            w, h, self._experiment, theta=self.theta, x=self.x, y=self.y
        )
        mask = np.cos(self.n_arms * np.arctan2(local_y, local_x)) >= 0

        image = np.zeros((h, w, 3), dtype=np.uint8)
        image[:, :, :] = 0
        image[mask] = self.color

        p.setPen(Qt.NoPen)
        p.setRenderHint(QPainter.Antialiasing)
        self.clip(p, w, h)
        p.drawImage(QPointF(0.0, 0.0), qimage2ndarray.array2qimage(image))


class HighResMovingWindmillStimulus(HighResWindmillStimulus, InterpolatedStimulus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dynamic_parameters.append("theta")


class CircleStimulus(VisualStimulus, DynamicStimulus):
    """A filled circle stimulus, which in combination with interpolation
    can be used to make looming stimuli

    Parameters
    ---------
    origin : tuple(float, float)
        positions of the circle centre (as fraction of screen size)

    radius : float
        circle radius (as fraction of screen size)

    backgroud_color : tuple(int, int, int)
        RGB color of the background

    circle_color : tuple(int, int, int)
        RGB color of the circle


    """

    def __init__(
        self,
        *args,
        origin=(0.5, 0.5),
        radius=10,
        background_color=(0, 0, 0),
        circle_color=(255, 255, 255),
        **kwargs
    ):
        super().__init__(*args, dynamic_parameters=["x", "y", "radius"], **kwargs)
        self.x = origin[0]
        self.y = origin[1]
        self.radius = radius
        self.background_color = background_color
        self.circle_color = circle_color
        self.name = "circle"

    def paint(self, p, w, h):
        super().paint(p, w, h)

        # draw the background
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(*self.background_color)))
        self.clip(p, w, h)
        p.drawRect(self._full_field_rect(w, h))

        # draw the circle
        p.setBrush(QBrush(QColor(*self.circle_color)))
        p.drawEllipse(QPointF(self.x * w, self.y * h), self.radius * w, self.radius * h)


class CalibratedCircleStimulus(VisualStimulus, DynamicStimulus):
    """A filled circle stimulus, which in combination with interpolation
    can be used to make looming stimuli

    Parameters
    ---------
    origin : tuple(float, float)
        positions of the circle centre (in mm)

    radius : float
        circle radius (in mm)

    backgroud_color : tuple(int, int, int)
        RGB color of the background

    circle_color : tuple(int, int, int)
        RGB color of the circle


    """

    def __init__(
        self,
        *args,
        origin=(0.5, 0.5),
        radius=10,
        background_color=(0, 0, 0),
        circle_color=(255, 255, 255),
        **kwargs
    ):
        super().__init__(*args, dynamic_parameters=["x", "y", "radius"], **kwargs)
        self.x = origin[0]
        self.y = origin[1]
        self.radius = radius
        self.background_color = background_color
        self.circle_color = circle_color
        self.name = "circle"

    def paint(self, p, w, h):
        super().paint(p, w, h)

        mm_px_x, mm_px_y = _mm_px_xy(self._experiment)

        # draw the background
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(*self.background_color)))
        self.clip(p, w, h)
        p.drawRect(self._full_field_rect(w, h))

        # draw the circle
        p.setBrush(QBrush(QColor(*self.circle_color)))
        p.drawEllipse(
            QPointF(self.x / mm_px_x, self.y / mm_px_y),
            self.radius / mm_px_x,
            self.radius / mm_px_y,
        )


class FixationCrossStimulus(FullFieldVisualStimulus):
    """Draws a simple cross in the center of the visual field"""

    def __init__(
        self,
        cross_color=(255, 0, 0),
        position=(0.5, 0.5),
        arm_len=0.05,
        arm_width=4,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.cross_color = cross_color
        self.arm_len = arm_len
        self.arm_width = arm_width
        self.position = position
        self.name = "fixation_cross"

    def paint(self, p, w, h):
        super().paint(p, w, h)
        pen = QPen(QColor(*self.cross_color))
        pen.setWidthF(float(self.arm_width))
        p.setPen(pen)
        #    p.setBrush(QBrush(QColor(0, 0, 0, 255)))
        l = w * self.arm_len
        w_p = w * self.position[0]
        h_p = h * self.position[1]
        p.drawLine(QLineF(w_p - l, h_p, w_p + l, h_p))
        p.drawLine(QLineF(w_p, h_p - l, w_p, h_p + l))
