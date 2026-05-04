import math

import cv2
import numpy as np
from PyQt5.QtCore import QRectF, QPointF, QLineF
from PyQt5.QtGui import QPainter, QPen, QColor, QBrush, QPolygonF

from lightparam.param_qt import ParametrizedQt, Param


class CalibrationException(Exception):
    """ """

    pass


class Calibrator(ParametrizedQt):
    """ """

    def __init__(self, mm_px_x=0.2, mm_px_y=0.2):
        super().__init__(name="stimulus/calibration_params")
        self.enabled = False

        self.mm_px_x = Param(mm_px_x)
        self.mm_px_y = Param(mm_px_y)
        self.length_mm_x = Param(30.0, limits=(1, 800), unit="mm")
        self.length_mm_y = Param(30.0, limits=(1, 800), unit="mm")
        self.length_px_x = Param(None)
        self.length_px_y = Param(None)
        self.cam_to_proj = Param(None)
        self.proj_to_cam = Param(None)

        self.length_to_measure_x = "do not use the base class as a calibrator"
        self.length_to_measure_y = "do not use the base class as a calibrator"

        self.sig_param_changed.connect(self.set_physical_scale)

    def toggle(self):
        """ """
        self.enabled = not self.enabled

    @staticmethod
    def _safe_scale(value):
        return max(float(value), 1e-9)

    def mm_to_px_x(self, value):
        return value / self._safe_scale(self.mm_px_x)

    def mm_to_px_y(self, value):
        return value / self._safe_scale(self.mm_px_y)

    def px_to_mm_x(self, value):
        return value * self._safe_scale(self.mm_px_x)

    def px_to_mm_y(self, value):
        return value * self._safe_scale(self.mm_px_y)

    def mm_to_px(self, x, y):
        return self.mm_to_px_x(x), self.mm_to_px_y(y)

    def px_to_mm(self, x, y):
        return self.px_to_mm_x(x), self.px_to_mm_y(y)

    def distance_squared_mm(self, dx_px, dy_px):
        return self.px_to_mm_x(dx_px) ** 2 + self.px_to_mm_y(dy_px) ** 2

    def scale_for_angle(self, theta):
        return np.sqrt(
            (np.cos(theta) * self._safe_scale(self.mm_px_x)) ** 2
            + (np.sin(theta) * self._safe_scale(self.mm_px_y)) ** 2
        )

    def set_physical_scale(self, change):
        """Calculate mm/px from calibrator length"""
        self.block_signal = True

        if change.get("length_mm_x", None) is not None and self.length_px_x is not None:
            self.mm_px_x = self.length_mm_x / self.length_px_x
        if change.get("length_mm_y", None) is not None and self.length_px_y is not None:
            self.mm_px_y = self.length_mm_y / self.length_px_y

        if change.get("length_px_x", None) is not None and self.length_px_x is not None:
            self.length_mm_x = self.px_to_mm_x(self.length_px_x)
        if change.get("length_px_y", None) is not None and self.length_px_y is not None:
            self.length_mm_y = self.px_to_mm_y(self.length_px_y)

        if change.get("mm_px_x", None) is not None and self.length_px_x is not None:
            self.length_mm_x = self.px_to_mm_x(self.length_px_x)
        if change.get("mm_px_y", None) is not None and self.length_px_y is not None:
            self.length_mm_y = self.px_to_mm_y(self.length_px_y)

        self.block_signal = False

    def set_pixel_scale(self, w, h):
        """ "Set pixel size, need to be called by the projector widget on resizes"""
        self.block_signal = True
        self.length_px_x = w
        self.length_px_y = h
        self.length_mm_x = self.px_to_mm_x(self.length_px_x)
        self.length_mm_y = self.px_to_mm_y(self.length_px_y)
        self.block_signal = False

    def paint_calibration_pattern(self, p, h, w):
        """

        Parameters
        ----------
        p :

        h :

        w :


        Returns
        -------

        """
        pass


class CrossCalibrator(Calibrator):
    """ """

    def __init__(
        self,
        *args,
        fixed_length=60,
        calibration_length="outside",
        transparent=True,
        **kwargs
    ):
        super().__init__(*args, **kwargs)

        self.length_px_x = self.mm_to_px_x(self.length_mm_x)
        self.length_px_y = self.mm_to_px_y(self.length_mm_y)
        self.length_is_fixed = False
        self.transparent = transparent

        if calibration_length == "outside":
            self.outside = True
            self.length_to_measure_x = "width of the rectangle"
            self.length_to_measure_y = "height of the rectangle"

        else:
            self.outside = False
            self.length_to_measure_x = "horizontal arm of the cross"
            self.length_to_measure_y = "vertical arm of the cross"
            if fixed_length is not None:
                self.length_px_x = fixed_length
                self.length_px_y = fixed_length
                self.length_is_fixed = True

    def paint_calibration_pattern(self, p, h, w):
        """

        Parameters
        ----------
        p :

        h :

        w :


        Returns
        -------

        """
        p.setPen(QPen(QColor(255, 0, 0)))
        if self.transparent:
            p.setBrush(QBrush(QColor(0, 0, 0, 0)))
        else:
            p.setBrush(QBrush(QColor(0, 0, 0, 255)))
        p.drawRect(QRectF(1.0, 1.0, float(w) - 2.0, float(h) - 2.0))
        l2x = self.length_px_x / 2
        l2y = self.length_px_y / 2
        cw = w // 2
        ch = h // 2

        # draw the cross and the axis labels
        p.drawLine(QLineF(float(cw - l2x), float(ch), float(cw + l2x), float(h // 2)))
        p.drawText(QPointF(float(w * 3 // 4), float(ch - 5)), "x")
        p.drawLine(QLineF(float(cw), float(h // 2 + l2y), float(cw), float(ch - l2y)))
        p.drawText(QPointF(float(cw + 5), float(h * 3 // 4)), "y")

        # draw the "fish outline"
        p.drawEllipse(QRectF(float(cw - 5), float(ch - 8), 3.0, 5.0))
        p.drawEllipse(QRectF(float(cw + 2), float(ch - 8), 3.0, 5.0))
        p.drawPolygon(
            QPolygonF(
                [
                    QPointF(float(cw - 3), float(ch + 2)),
                    QPointF(float(cw + 3), float(ch + 2)),
                    QPointF(float(cw), float(ch + 20)),
                ]
            )
        )

    def set_pixel_scale(self, w, h):
        """ "Set pixel size, need to be called by the projector widget on resizes"""
        if not self.length_is_fixed:
            self.block_signal = True
            if self.outside:
                self.length_px_x = w
                self.length_px_y = h
            else:
                self.length_px_x = w / 2
                self.length_px_y = h / 2
            self.length_mm_x = self.px_to_mm_x(self.length_px_x)
            self.length_mm_y = self.px_to_mm_y(self.length_px_y)
            self.block_signal = False


class CircleCalibrator(Calibrator):
    """ " Class for a calibration pattern which displays 3 dots in a 30 60 90 triangle"""

    def __init__(self, *args, dh=80, r=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.triangle_length = Param(dh, (2, 400), unit="px")
        self.r = r
        self.points = None
        self.points_cam = None
        self.length_to_measure_x = "horizontal right-angle side (between lower dots)"
        self.length_to_measure_y = "vertical right-angle side (between left dots)"
        self.set_pixel_scale(None, None)

    def _half_triangle_width_px(self):
        return float(self.triangle_length) / 2.0

    def _half_triangle_height_px(self):
        return float(self.triangle_length) * math.sqrt(3) / 2.0

    def _right_triangle_side_lengths_px(self):
        return float(self.triangle_length), 2.0 * self._half_triangle_height_px()

    def _centres(self, w, h):
        d2h = self._half_triangle_width_px()
        d2w = self._half_triangle_height_px()
        ch = h / 2.0
        cw = w / 2.0
        return np.array(
            [
                (cw - d2h, ch + d2w),
                (cw + d2h, ch + d2w),
                (cw - d2h, ch - d2w),
            ],
            dtype=float,
        )

    def set_pixel_scale(self, w, h):
        """ "Set pixel size, need to be called by the projector widget on resizes"""
        self.block_signal = True
        self.length_px_x, self.length_px_y = self._right_triangle_side_lengths_px()
        self.length_mm_x = self.px_to_mm_x(self.length_px_x)
        self.length_mm_y = self.px_to_mm_y(self.length_px_y)
        self.block_signal = False

    def set_physical_scale(self, change):
        super().set_physical_scale(change)
        if change.get("triangle_length", None) is not None:
            self.set_pixel_scale(None, None)

    def paint_calibration_pattern(self, p, h, w, draw=True):
        """

        Parameters
        ----------
        p :

        h :

        w :

        draw :
             (Default value = True)

        Returns
        -------

        """
        assert isinstance(p, QPainter)

        # the three points sorted in ascending angle order (30, 60, 90)
        centres = self._centres(w, h)
        self.points = centres[np.argsort(CircleCalibrator._find_angles(centres)), :]

        if draw:
            p.setPen(QPen(QColor(255, 0, 0)))
            p.setBrush(QBrush(QColor(255, 0, 0)))
            for centre in centres:
                p.drawEllipse(
                    QPointF(float(centre[0]), float(centre[1])),
                    float(self.r),
                    float(self.r),
                )

    @staticmethod
    def _find_angles(kps):
        """

        Parameters
        ----------
        kps :


        Returns
        -------

        """
        angles = np.empty(3)
        for i, pt in enumerate(kps):
            pt_prev = kps[(i - 1) % 3]
            pt_next = kps[(i + 1) % 3]
            # angles are calculated from the dot product
            angles[i] = np.abs(
                np.arccos(
                    np.sum((pt_prev - pt) * (pt_next - pt))
                    / np.product(
                        [np.sqrt(np.sum((pt2 - pt) ** 2)) for pt2 in [pt_prev, pt_next]]
                    )
                )
            )
        return angles

    @staticmethod
    def _find_triangle(image, blob_params=None):
        """Finds the three dots for calibration in the image
        (of a 30 60 90 degree triangle)

        Parameters
        ----------
        image :
            return: the three triangle points
        blob_params :
             (Default value = None)

        Returns
        -------
        type
            the three triangle points

        """
        if blob_params is None:
            blobdet = cv2.SimpleBlobDetector_create()
        else:
            blobdet = cv2.SimpleBlobDetector_create(blob_params)
        # TODO check if blob detection is robust
        scaled_im = 255 - (image.astype(np.float32) * 255 / np.max(image)).astype(
            np.uint8
        )
        keypoints = blobdet.detect(scaled_im)
        if len(keypoints) != 3:
            raise CalibrationException("3 points for calibration not found")
        kps = np.array([k.pt for k in keypoints])

        # Find the angles between the points
        # and return the points sorted by the angles

        return kps[np.argsort(CircleCalibrator._find_angles(kps)), :]

    @staticmethod
    def arr_to_tuple(arr):
        """

        Parameters
        ----------
        arr :


        Returns
        -------

        """
        return tuple(tuple(r for r in row) for row in arr)

    def find_transform_matrix(self, image):
        """

        Parameters
        ----------
        image :


        Returns
        -------

        """
        self.points_cam = self._find_triangle(image)
        points_proj = self.points

        x_proj = np.vstack([points_proj.T, np.ones(3)])
        x_cam = np.vstack([self.points_cam.T, np.ones(3)])

        self.proj_to_cam = self.arr_to_tuple(self.points_cam.T @ np.linalg.inv(x_proj))
        self.cam_to_proj = self.arr_to_tuple(points_proj.T @ np.linalg.inv(x_cam))
