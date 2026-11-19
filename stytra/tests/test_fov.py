import cv2
import numpy as np
import pytest

from stytra.calibration.fov import CorrectedFOV, corners


@pytest.mark.parametrize("top,bottom,shift", [(90, 90, 0), (60, 120, 18), (115, 65, -27)])
def test_corrected_canvas_on_physical_plane(top, bottom, shift):
    size = (460, 300)
    pos = (80, 50)
    raw = corners((0, 0), size)
    height = 75
    measured = np.float32([(shift - top / 2, 0), (shift + top / 2, 0),
                           (bottom / 2, height), (-bottom / 2, height)])
    optics = cv2.getPerspectiveTransform(raw, measured)
    fov = CorrectedFOV(dict(measurements=(top, bottom, height, shift),
                            pos=pos, size=size), pos, size)
    projected = np.float32([fov.transform.map(float(x), float(y)) for x, y in raw])
    physical = cv2.perspectiveTransform(projected[None], optics)[0]
    center = cv2.perspectiveTransform(raw.mean(0).reshape(1, 1, 2), optics)[0, 0]
    np.testing.assert_allclose(physical, center + (raw - raw.mean(0)) * fov.mm_px,
                               atol=2e-5)
    # The largest fitting rectangle touches at least one boundary.
    margins = np.minimum(projected, size - projected)
    assert abs(margins.min()) < 1e-4
