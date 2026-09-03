"""Unit tests for BagCounter (app/worker/pipeline/counter.py) - the
module responsible for "count each bag exactly once"."""

from app.worker.pipeline.counter import BagCounter
from app.worker.pipeline.roi import SceneGeometry
from app.worker.pipeline.tracker import Track


def _make_geometry() -> SceneGeometry:
    return SceneGeometry(frame_w=100, frame_h=100)


def _crossing_points(geometry: SceneGeometry):
    (x1, y1), (x2, y2) = geometry.line
    nx, ny = -(y2 - y1), (x2 - x1)
    mid = ((x1 + x2) / 2, (y1 + y2) / 2)
    a = (mid[0] + nx * 0.05, mid[1] + ny * 0.05)
    b = (mid[0] - nx * 0.05, mid[1] - ny * 0.05)
    if geometry.crossed_line(a, b):
        return a, b
    return b, a


def test_confirmed_track_crossing_line_is_counted_once():
    geometry = _make_geometry()
    prev_pt, cur_pt = _crossing_points(geometry)
    counter = BagCounter(geometry)

    track = Track(track_id=1, bbox=(0, 0, 10, 10), score=0.9, confirmed=True)
    track.history = [prev_pt, cur_pt]
    track.areas = [100.0]

    events = counter.process([track], frame_idx=10)

    assert len(events) == 1
    assert counter.count == 1
    assert track.counted is True

    # a second call with the same (now-counted) track must not double count
    events_again = counter.process([track], frame_idx=11)
    assert events_again == []
    assert counter.count == 1


def test_unconfirmed_track_is_never_counted():
    geometry = _make_geometry()
    prev_pt, cur_pt = _crossing_points(geometry)
    counter = BagCounter(geometry)

    track = Track(track_id=2, bbox=(0, 0, 10, 10), score=0.9, confirmed=False)
    track.history = [prev_pt, cur_pt]

    events = counter.process([track], frame_idx=1)
    assert events == []
    assert counter.count == 0


def test_track_with_less_than_two_history_points_is_skipped():
    geometry = _make_geometry()
    counter = BagCounter(geometry)
    track = Track(track_id=3, bbox=(0, 0, 10, 10), score=0.9, confirmed=True)
    track.history = [(1.0, 1.0)]

    events = counter.process([track], frame_idx=1)
    assert events == []
