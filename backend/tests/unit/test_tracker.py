"""Unit tests for BagTracker (app/worker/pipeline/tracker.py)."""

from app.worker.pipeline.detector import Detection
from app.worker.pipeline.tracker import BagTracker, iou


def _det(x1, y1, x2, y2, score=0.9, label="bag_candidate") -> Detection:
    return Detection(x1=x1, y1=y1, x2=x2, y2=y2, score=score, label=label)


def test_iou_identical_boxes_is_one():
    box = (0.0, 0.0, 10.0, 10.0)
    assert iou(box, box) == 1.0


def test_iou_disjoint_boxes_is_zero():
    assert iou((0.0, 0.0, 5.0, 5.0), (100.0, 100.0, 110.0, 110.0)) == 0.0


def test_new_detection_creates_unconfirmed_track():
    tracker = BagTracker()
    tracks = tracker.update([_det(0, 0, 10, 10)])
    assert len(tracks) == 1
    assert tracks[0].confirmed is False
    assert tracks[0].hits == 1


def test_track_confirms_after_min_hits_consecutive_matches():
    tracker = BagTracker()
    for _ in range(3):
        tracks = tracker.update([_det(0, 0, 10, 10)])
    assert len(tracks) == 1
    assert tracks[0].confirmed is True
    assert tracks[0].track_id == 1  # same track reused across frames, not recreated


def test_track_is_dropped_after_max_age_unmatched_frames():
    from app.config import settings

    tracker = BagTracker()
    tracker.update([_det(0, 0, 10, 10)])
    for _ in range(settings.tracker_max_age + 1):
        tracks = tracker.update([])
    assert tracks == []
