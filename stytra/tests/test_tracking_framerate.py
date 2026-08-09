from datetime import datetime, timedelta
from collections import namedtuple
from queue import Empty

import numpy as np

from stytra.tracking.tracking_process import TrackingProcess


class FinishedSignal:
    def __init__(self):
        self.finished = False

    def is_set(self):
        return self.finished


class InputQueue:
    def __init__(self, items, finished_signal):
        self.items = list(items)
        self.finished_signal = finished_signal

    def get(self, timeout=None):
        if self.items:
            return self.items.pop(0)
        self.finished_signal.finished = True
        raise Empty


class OutputQueue:
    def __init__(self):
        self.items = []

    def put(self, *items, **kwargs):
        self.items.append((items, kwargs))


class RecordingSignal:
    @staticmethod
    def is_set():
        return True


class Pipeline:
    result_type = namedtuple("Result", "value")

    def __init__(self):
        self.diagnostic_image = None
        self.n_processed = 0

    def setup(self):
        pass

    def run(self, frame):
        self.n_processed += 1
        return [], self.result_type(int(frame[0]))


class TrackingHarness:
    def __init__(self, frames, timestamps):
        self.finished_signal = FinishedSignal()
        self.frame_queue = InputQueue(
            [
                (timestamp, i, frame)
                for i, (timestamp, frame) in enumerate(zip(timestamps, frames))
            ],
            self.finished_signal,
        )
        self.pipeline_cls = Pipeline
        self.pipeline = None
        self.tracking_every_n_frame = 5
        self.recording_signal = RecordingSignal()
        self.frame_copy_queue = OutputQueue()
        self.message_queue = OutputQueue()
        self.output_queue = OutputQueue()
        self.second_output_queue = None
        self.gui_frames = []

    def retrieve_params(self):
        pass

    def publish_state(self):
        pass

    def update_framerate(self):
        pass

    def send_to_gui(self, timestamp, frame):
        self.gui_frames.append((timestamp, frame))


def test_tracking_limit_does_not_limit_recording_frames():
    t0 = datetime.now()
    timestamps = [t0 + timedelta(seconds=i / 150.0) for i in range(150)]
    frames = [np.array([i], dtype=np.uint8) for i in range(150)]
    harness = TrackingHarness(frames, timestamps)

    TrackingProcess.run(harness)

    assert len(harness.frame_copy_queue.items) == 150
    assert len(harness.output_queue.items) == 30
    assert harness.pipeline.n_processed == 30
