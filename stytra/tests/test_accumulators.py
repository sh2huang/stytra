from collections import deque, namedtuple
from datetime import datetime, timedelta
from queue import Empty

from stytra.collectors.accumulators import QueueDataAccumulator


class NonBlockingQueue:
    def __init__(self, items):
        self.items = deque(items)

    def get_nowait(self):
        if not self.items:
            raise Empty
        return self.items.popleft()


class ProtocolRunner:
    running = True


class Experiment:
    def __init__(self, t0):
        self.t0 = t0
        self.protocol_runner = ProtocolRunner()


def test_queue_data_accumulator_processes_bounded_batches():
    t0 = datetime.now()
    result_type = namedtuple("Result", "value")
    items = [
        (t0 + timedelta(milliseconds=i), result_type(i)) for i in range(5)
    ]
    data_queue = NonBlockingQueue(items)
    accumulator = QueueDataAccumulator(
        data_queue=data_queue,
        experiment=Experiment(t0),
        max_items_per_update=2,
    )

    assert accumulator.update_list() == 2
    assert [item.value for item in accumulator.stored_data] == [0, 1]
    assert len(data_queue.items) == 3

    assert accumulator.update_list() == 2
    assert [item.value for item in accumulator.stored_data] == [0, 1, 2, 3]

    assert accumulator.update_list() == 1
    assert [item.value for item in accumulator.stored_data] == [0, 1, 2, 3, 4]


def test_queue_data_accumulator_rejects_empty_batches():
    t0 = datetime.now()
    try:
        QueueDataAccumulator(
            data_queue=NonBlockingQueue([]),
            experiment=Experiment(t0),
            max_items_per_update=0,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Expected max_items_per_update=0 to be rejected")
