import logging
import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from app.config import settings
from app.worker.pipeline.anomaly import AnomalyMonitor
from app.worker.pipeline.counter import BagCounter
from app.worker.pipeline.detector import build_detector
from app.worker.pipeline.roi import SceneGeometry
from app.worker.pipeline.tracker import BagTracker

log = logging.getLogger(__name__)

_ACTIVE_ANOMALY_BANNER_FRAMES = 45  # how long a fresh anomaly stays on screen


class ProcessingResult:
    def __init__(self, bag_count: int, anomalies: list, total_frames: int, fps: float):
        self.bag_count = bag_count
        self.anomalies = anomalies
        self.total_frames = total_frames
        self.fps = fps


def process_video(
    input_path: str,
    output_path: str,
    progress_cb: Callable[[int, int], None] | None = None,
) -> ProcessingResult:
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open input video: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or None

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*settings.output_fourcc)  # type: ignore[attr-defined]
    writer = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

    geometry = SceneGeometry(w, h)
    detector = build_detector()
    tracker = BagTracker()
    counter = BagCounter(geometry)
    monitor = AnomalyMonitor(fps, geometry)

    last_anomaly_frame = -10_000
    frame_idx = 0
    t0 = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        detections = detector.infer(frame)
        roi_detections = [d for d in detections if geometry.point_in_roi(d.cx, d.cy)]

        tracks = tracker.update(roi_detections)
        events = counter.process(tracks, frame_idx)
        for ev in events:
            monitor.observe_crossing(ev.frame_idx, ev.track_id, ev.area)
        monitor.observe_frame(frame_idx, tracks, len(roi_detections))

        if monitor.anomalies and monitor.anomalies[-1].frame == frame_idx:
            last_anomaly_frame = frame_idx

        _draw_overlay(
            frame,
            geometry,
            tracks,
            counter.count,
            recent_anomaly=(frame_idx - last_anomaly_frame) < _ACTIVE_ANOMALY_BANNER_FRAMES,
            anomaly_text=monitor.anomalies[-1].message if monitor.anomalies else None,
        )
        writer.write(frame)

        frame_idx += 1
        if progress_cb and (frame_idx % 10 == 0 or frame_idx == total_frames):
            progress_cb(frame_idx, total_frames or frame_idx)

    cap.release()
    writer.release()

    elapsed = time.time() - t0
    log.info(
        "Processed %s frames in %.1fs (%.1f fps) - %d bags counted, %d anomalies",
        frame_idx,
        elapsed,
        frame_idx / elapsed if elapsed else 0,
        counter.count,
        len(monitor.anomalies),
    )

    return ProcessingResult(
        bag_count=counter.count,
        anomalies=monitor.to_list(),
        total_frames=frame_idx,
        fps=fps,
    )


def _draw_overlay(frame, geometry: SceneGeometry, tracks, count, recent_anomaly, anomaly_text):
    if settings.draw_roi:
        cv2.polylines(frame, [geometry.roi_polygon], True, (80, 200, 255), 2, cv2.LINE_AA)
    (lx1, ly1), (lx2, ly2) = geometry.line
    cv2.line(frame, (int(lx1), int(ly1)), (int(lx2), int(ly2)), (0, 0, 255), 2, cv2.LINE_AA)

    for t in tracks:
        if not t.confirmed:
            continue
        x1, y1, x2, y2 = (int(v) for v in t.bbox)
        color = (0, 200, 0) if t.counted else (0, 165, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            frame,
            f"#{t.track_id}",
            (x1, max(0, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2,
            cv2.LINE_AA,
        )
        if settings.draw_trails and len(t.history) > 1:
            pts = np.array(t.history, dtype=np.int32)
            cv2.polylines(frame, [pts], False, color, 1, cv2.LINE_AA)

    _draw_counter_badge(frame, count)
    if recent_anomaly and anomaly_text:
        _draw_anomaly_banner(frame, anomaly_text)


def _draw_counter_badge(frame, count: int):
    h, w = frame.shape[:2]
    text = f"Bags: {count}"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
    pad = 10
    cv2.rectangle(frame, (10, 10), (10 + tw + 2 * pad, 10 + th + 2 * pad), (30, 30, 30), -1)
    cv2.putText(
        frame,
        text,
        (10 + pad, 10 + th + pad // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )


def _draw_anomaly_banner(frame, text: str):
    h, w = frame.shape[:2]
    banner_h = 30
    cv2.rectangle(frame, (0, h - banner_h), (w, h), (0, 0, 180), -1)
    cv2.putText(
        frame,
        f"ANOMALY: {text[:90]}",
        (8, h - 9),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
