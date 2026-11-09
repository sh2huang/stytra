"""Protocol-independent setup pattern matching the four maximum E10 loom3 looms."""

import numpy as np
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QPainter, QPainterPath


class LoomAlignmentPattern:
    """Four static 60-degree squares on the 18 mm radius cylindrical arena.

    The eye is 4 mm above the floor. The 38 mm projector radius maps to the
    bottom of the wall, with 1:1 wall and floor mapping, as in the E10 setup.
    These fixed reference dimensions do not depend on the selected protocol.
    """

    angles_deg = (-105.0, -35.0, 35.0, 105.0)
    full_angle_deg = 60.0
    animal_height_mm = 4.0
    arena_radius_mm = 18.0
    arena_height_mm = 18.0
    projector_radius_mm = 38.0

    @staticmethod
    def ring_sector(w, h, mm_px, center, beta, inner_radius, outer_radius):
        """Map an annular sector to pixels using the current calibrated scale."""
        angles = np.linspace(center - beta, center + beta, 181)
        cx, cy = float(w) / 2.0, float(h) / 2.0
        scale = max(float(mm_px), 1e-12)
        path = QPainterPath()
        path.moveTo(
            QPointF(
                cx + outer_radius * np.cos(angles[0]) / scale,
                cy + outer_radius * np.sin(angles[0]) / scale,
            )
        )
        for radius, edge_angles in (
            (outer_radius, angles[1:]),
            (inner_radius, angles[::-1]),
        ):
            for angle in edge_angles:
                path.lineTo(
                    QPointF(
                        cx + radius * np.cos(angle) / scale,
                        cy + radius * np.sin(angle) / scale,
                    )
                )
        path.closeSubpath()
        return path

    def paint(self, p, w, h, mm_px):
        """Draw white background and the four black wall-and-floor shadows."""
        beta = np.deg2rad(self.full_angle_deg) / 2.0
        wall_offset = self.arena_radius_mm * np.tan(beta)
        wall_lower = np.clip(self.animal_height_mm - wall_offset, 0, self.arena_height_mm)
        wall_upper = np.clip(self.animal_height_mm + wall_offset, 0, self.arena_height_mm)
        wall_inner = self.projector_radius_mm - wall_upper
        wall_outer = self.projector_radius_mm - wall_lower
        floor_inner = np.clip(
            self.animal_height_mm / np.tan(beta), 0, self.arena_radius_mm
        )

        p.setRenderHint(QPainter.Antialiasing, False)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.drawRect(QRectF(-1.0, -1.0, float(w) + 2.0, float(h) + 2.0))
        p.setBrush(QBrush(QColor(0, 0, 0)))
        for angle in self.angles_deg:
            # E10 orientation: fish heading pi/2 plus projector offset pi.
            center = 1.5 * np.pi + np.deg2rad(angle)
            p.drawPath(self.ring_sector(w, h, mm_px, center, beta, wall_inner, wall_outer))
            if floor_inner < self.arena_radius_mm:
                p.drawPath(
                    self.ring_sector(
                        w, h, mm_px, center, beta, floor_inner, self.arena_radius_mm
                    )
                )
