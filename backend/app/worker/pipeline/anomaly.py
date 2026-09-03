"""
Anomaly monitoring.

The task deliberately leaves "what counts as an anomaly" open. We
focus on signals that specifically threaten *counting correctness*
(as opposed to generic video-quality issues), each cheap to compute
from data the pipeline already has on hand every frame:

  * stall            - no detections in the ROI for an extended period
                        after bags had been flowing (belt stopped /
                        camera view blocked / lighting failure).
  * unusual_size      - a counted bag's box area is far from the
                        running median (two bags merged into one
                        detection, or a spurious detection).
  * possible_double_count - two distinct tracks cross the counting
                        line within an implausibly short time of each
                        other (tracker ID switch / bag split in two).
  * lost_near_line    - a track disappears close to the counting line
                        before ever being confirmed as counted (likely
                        a missed/undercounted bag).
  * low_confidence    - the rolling average detector confidence drops,
                        meaning any counts in that window are less
                        trustworthy (occlusion, motion blur, glare).

Each anomaly is a small dict so it serializes directly into the Job's
JSON column and the API response, and is cheap to overlay on the
output video.
"""

from collections import deque
from dataclasses import dataclass

from app.config import settings
from app.worker.pipeline.roi import SceneGeometry
from app.worker.pipeline.tracker import Track


@dataclass
class Anomaly:
    frame: int
    timestamp_sec: float
    type: str
    severity: str  # "info" | "warning" | "critical"
    message: str

    def to_dict(self) -> dict:
        return {
            "frame": self.frame,
            "timestamp_sec": round(self.timestamp_sec, 2),
            "type": self.type,
            "severity": self.severity,
            "message": self.message,
        }


class AnomalyMonitor:
    def __init__(self, fps: float, geometry: SceneGeometry):
        self.fps = fps or 25.0
        self.geometry = geometry
        self.anomalies: list[Anomaly] = []

        self._frames_since_any_detection = 0
        self._has_seen_detection_ever = False
        self._stall_flagged = False

        self._median_area_window: deque = deque(maxlen=50)
        self._last_crossing_frame: int | None = None

        self._confidence_window: deque = deque(maxlen=settings.anomaly_low_confidence_window)
        self._low_conf_flagged_until = -1

        self._seen_track_ids: set[int] = set()

    def _ts(self, frame_idx: int) -> float:
        return frame_idx / self.fps

    def _add(self, frame_idx: int, type_: str, severity: str, message: str) -> None:
        self.anomalies.append(Anomaly(frame_idx, self._ts(frame_idx), type_, severity, message))

    def observe_frame(
        self, frame_idx: int, tracks: list[Track], detections_this_frame: int
    ) -> None:
        # -- stall detection -------------------------------------------------
        if detections_this_frame > 0:
            self._has_seen_detection_ever = True
            self._frames_since_any_detection = 0
            self._stall_flagged = False
        else:
            self._frames_since_any_detection += 1
            stall_frames = settings.anomaly_stall_seconds * self.fps
            if (
                self._has_seen_detection_ever
                and not self._stall_flagged
                and self._frames_since_any_detection >= stall_frames
            ):
                self._add(
                    frame_idx,
                    "stall",
                    "warning",
                    f"No bags detected in ROI for over {settings.anomaly_stall_seconds:.0f}s "
                    f"- conveyor may have stopped or the camera view is obstructed.",
                )
                self._stall_flagged = True

        # -- low confidence window -------------------------------------------
        for t in tracks:
            if t.time_since_update == 0:
                self._confidence_window.append(t.score)
        if len(self._confidence_window) == self._confidence_window.maxlen:
            avg_conf = sum(self._confidence_window) / len(self._confidence_window)
            if (
                avg_conf < settings.anomaly_low_confidence_thr
                and frame_idx - self._low_conf_flagged_until > self._confidence_window.maxlen
            ):
                self._add(
                    frame_idx,
                    "low_confidence",
                    "info",
                    f"Average detector confidence dropped to {avg_conf:.2f} over the last "
                    f"{self._confidence_window.maxlen} frames - counts in this window are less certain.",
                )
                self._low_conf_flagged_until = frame_idx

        # -- lost near line (track disappeared right before the line) --------
        for t in tracks:
            if t.track_id in self._seen_track_ids:
                continue
            if t.confirmed and not t.counted and t.time_since_update >= settings.tracker_max_age:
                dist = _point_to_segment_distance(
                    (t.cx, t.cy), self.geometry.line[0], self.geometry.line[1]
                )
                if dist < 0.15 * max(self.geometry.w, self.geometry.h):
                    self._add(
                        frame_idx,
                        "lost_near_line",
                        "warning",
                        f"Track #{t.track_id} disappeared near the counting line without being "
                        f"confirmed as counted - a bag may have been missed.",
                    )
                    self._seen_track_ids.add(t.track_id)

    def observe_crossing(self, frame_idx: int, track_id: int, area: float) -> None:
        # -- unusual size -----------------------------------------------------
        if len(self._median_area_window) >= 5:
            sorted_areas = sorted(self._median_area_window)
            median = sorted_areas[len(sorted_areas) // 2]
            if median > 0 and abs(area - median) / median > settings.anomaly_size_deviation:
                self._add(
                    frame_idx,
                    "unusual_size",
                    "warning",
                    f"Bag #{track_id} crossed the line with an area {area:.0f}px "
                    f"far from the recent median ({median:.0f}px) - possibly two bags "
                    f"merged into one detection, or a false positive.",
                )
        self._median_area_window.append(area)

        # -- possible double count --------------------------------------------
        if self._last_crossing_frame is not None:
            gap_sec = (frame_idx - self._last_crossing_frame) / self.fps
            if gap_sec < settings.anomaly_double_count_seconds:
                self._add(
                    frame_idx,
                    "possible_double_count",
                    "critical",
                    f"Bag #{track_id} crossed only {gap_sec:.2f}s after the previous one - "
                    f"check for a tracker ID switch or a bag that split into two detections.",
                )
        self._last_crossing_frame = frame_idx

    def to_list(self) -> list[dict]:
        return [a.to_dict() for a in self.anomalies]


def _point_to_segment_distance(p, a, b) -> float:
    import math

    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)
