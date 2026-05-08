import numpy as np

from stytra.tracking.eyes import EyeTrackingMethod, _fit_ellipse


def test_fit_ellipse_sorts_eyes_by_center_x(monkeypatch):
    left_contour = np.array(
        [[[10, 100]], [[11, 101]], [[12, 102]], [[13, 103]], [[14, 104]]],
        dtype=np.int32,
    )
    right_contour = np.array(
        [[[30, 10]], [[31, 11]], [[32, 12]], [[33, 13]], [[34, 14]]],
        dtype=np.int32,
    )
    ellipses = {
        10: ((11.0, 101.0), (6.0, 4.0), 12.0),
        30: ((31.0, 11.0), (8.0, 5.0), -4.0),
    }

    monkeypatch.setattr(
        "stytra.tracking.eyes.cv2.findContours",
        lambda *args, **kwargs: ([right_contour, left_contour], None),
    )
    monkeypatch.setattr(
        "stytra.tracking.eyes.cv2.fitEllipse",
        lambda contour: ellipses[int(contour[0, 0, 0])],
    )

    fitted = _fit_ellipse(np.zeros((32, 32), dtype=np.uint8))

    assert fitted == [ellipses[10], ellipses[30]]


def test_eye_tracking_output_preserves_xy_and_axis_names(monkeypatch):
    monkeypatch.setattr(
        "stytra.tracking.eyes._fit_ellipse",
        lambda _: [
            ((10.0, 20.0), (30.0, 40.0), 50.0),
            ((60.0, 70.0), (80.0, 90.0), 100.0),
        ],
    )

    method = EyeTrackingMethod()
    output = method._process(
        np.zeros((64, 64), dtype=np.uint8),
        wnd_pos=(0, 0),
        wnd_dim=(16, 16),
        threshold=1,
    )

    assert output.data == (
        10.0,
        20.0,
        30.0,
        40.0,
        -50.0,
        60.0,
        70.0,
        80.0,
        90.0,
        -100.0,
    )
