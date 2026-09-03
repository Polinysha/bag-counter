"""Unit tests for AnomalyMonitor (app/worker/pipeline/anomaly.py)."""

from app.config import settings
from app.worker.pipeline.anomaly import AnomalyMonitor
from app.worker.pipeline.roi import SceneGeometry


def _monitor(fps: float = 10.0) -> AnomalyMonitor:
    return AnomalyMonitor(fps=fps, geometry=SceneGeometry(frame_w=100, frame_h=100))


def test_stall_triggers_after_bags_were_flowing_then_stop():
    fps = 10.0
    monitor = _monitor(fps)
    monitor.observe_frame(frame_idx=0, tracks=[], detections_this_frame=3)

    stall_frames = int(settings.anomaly_stall_seconds * fps) + 2
    for f in range(1, stall_frames):
        monitor.observe_frame(frame_idx=f, tracks=[], detections_this_frame=0)

    types = [a.type for a in monitor.anomalies]
    assert "stall" in types


def test_no_stall_if_no_detection_was_ever_seen():
    monitor = _monitor()
    for f in range(200):
        monitor.observe_frame(frame_idx=f, tracks=[], detections_this_frame=0)
    assert monitor.anomalies == []


def test_possible_double_count_flagged_for_close_crossings():
    monitor = _monitor(fps=10.0)
    monitor.observe_crossing(frame_idx=0, track_id=1, area=1000.0)
    monitor.observe_crossing(frame_idx=1, track_id=2, area=1000.0)  # 0.1s later
    assert any(a.type == "possible_double_count" for a in monitor.anomalies)


def test_unusual_size_not_flagged_with_insufficient_history():
    monitor = _monitor()
    monitor.observe_crossing(frame_idx=0, track_id=1, area=999999.0)
    assert monitor.anomalies == []
