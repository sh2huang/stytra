import math

import pytest

from stytra.calibration import CircleCalibrator, CrossCalibrator


def test_circle_calibrator_uses_right_triangle_legs_for_dual_axis_scale():
    calibrator = CircleCalibrator(dh=80)

    assert calibrator.length_px_x == pytest.approx(80.0)
    assert calibrator.length_px_y == pytest.approx(80.0 * math.sqrt(3))

    calibrator.length_mm_x = 40.0
    calibrator.length_mm_y = 96.0
    calibrator.set_physical_scale({"length_mm_x": 40.0, "length_mm_y": 96.0})

    assert calibrator.mm_px_x == pytest.approx(0.5)
    assert calibrator.mm_px_y == pytest.approx(96.0 / (80.0 * math.sqrt(3)))


def test_cross_calibrator_tracks_horizontal_and_vertical_lengths_separately():
    calibrator = CrossCalibrator(calibration_length="outside", mm_px_x=0.5, mm_px_y=0.25)
    calibrator.set_pixel_scale(200, 100)

    assert calibrator.length_px_x == pytest.approx(200.0)
    assert calibrator.length_px_y == pytest.approx(100.0)
    assert calibrator.length_mm_x == pytest.approx(100.0)
    assert calibrator.length_mm_y == pytest.approx(25.0)


def test_calibrator_toggle_keeps_boolean_state():
    calibrator = CircleCalibrator()

    calibrator.toggle()
    assert calibrator.enabled is True

    calibrator.toggle()
    assert calibrator.enabled is False
