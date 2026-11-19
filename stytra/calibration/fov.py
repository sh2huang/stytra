"""Geometry of a projector aimed at a plane (parallel top and bottom edges)."""

import cv2
import numpy as np
from PyQt5.QtGui import QTransform


def corners(pos, size):
    x, y = pos
    w, h = size
    return np.float32([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])


class CorrectedFOV:
    """Map a square-pixel stimulus canvas to the raw projector ROI."""

    def __init__(self, calibration, pos, size):
        top, bottom, height, shift = calibration["measurements"]
        physical = np.float32([
            (shift - top / 2, 0), (shift + top / 2, 0),
            (bottom / 2, height), (-bottom / 2, height),
        ])
        measured = corners(calibration["pos"], calibration["size"])
        to_mm = cv2.getPerspectiveTransform(measured, physical)
        raw = corners(pos, size)
        polygon = cv2.perspectiveTransform(raw[None], to_mm)[0]
        cross = raw.mean(axis=0)
        center = cv2.perspectiveTransform(cross.reshape(1, 1, 2), to_mm)[0, 0]

        # Each edge bounds the scale of a rectangle centered on the original
        # cross. Its furthest corner must still be inside that edge.
        edges = np.roll(polygon, -1, axis=0) - polygon
        normals = np.column_stack((-edges[:, 1], edges[:, 0]))
        margins = ((center - polygon) * normals).sum(axis=1)
        self.size = tuple(size)
        self.mm_px = float(np.min(2 * margins / (np.abs(normals) @ size)))
        if self.mm_px <= 0 or not np.isfinite(self.mm_px):
            raise ValueError("This ROI lies outside the calibrated projection plane.")
        canvas = corners((0, 0), size)
        target = center + (canvas - canvas.mean(axis=0)) * self.mm_px
        output = cv2.perspectiveTransform(target[None], np.linalg.inv(to_mm))[0] - pos
        matrix = cv2.getPerspectiveTransform(canvas, output.astype(np.float32))
        self.transform = QTransform(*matrix.T.ravel())
