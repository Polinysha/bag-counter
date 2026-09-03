"""
A small, dependency-light multi-object tracker in the spirit of SORT:
constant-velocity motion prediction + IoU matching solved with the
Hungarian algorithm. No deep re-identification features are needed
here because the scene is simple (one lane, objects don't occlude
each other much), which keeps the pipeline fast enough for CPU-only
deployment while still giving each bag a stable ID across frames -
the ID is what protects the counter from double-counting the same
bag on consecutive frames.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.config import settings
from app.worker.pipeline.detector import Detection


def iou(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Track:
    track_id: int
    bbox: Tuple[float, float, float, float]
    score: float
    velocity: Tuple[float, float] = (0.0, 0.0)
    hits: int = 1
    age: int = 0
    time_since_update: int = 0
    confirmed: bool = False
    counted: bool = False
    history: List[Tuple[float, float]] = field(default_factory=list)  # centroids
    areas: List[float] = field(default_factory=list)

    @property
    def cx(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2

    def predicted_bbox(self) -> Tuple[float, float, float, float]:
        vx, vy = self.velocity
        x1, y1, x2, y2 = self.bbox
        return (x1 + vx, y1 + vy, x2 + vx, y2 + vy)

    def update(self, det: Detection) -> None:
        prev_cx, prev_cy = self.cx, self.cy
        new_bbox = det.bbox
        self.velocity = (
            (new_bbox[0] + new_bbox[2]) / 2 - prev_cx,
            (new_bbox[1] + new_bbox[3]) / 2 - prev_cy,
        )
        self.bbox = new_bbox
        self.score = det.score
        self.hits += 1
        self.time_since_update = 0
        self.history.append((self.cx, self.cy))
        self.areas.append(det.area)
        if len(self.history) > 60:
            self.history.pop(0)
            self.areas.pop(0)
        if self.hits >= settings.tracker_min_hits:
            self.confirmed = True

    def mark_missed(self) -> None:
        x1, y1, x2, y2 = self.predicted_bbox()
        self.bbox = (x1, y1, x2, y2)
        self.time_since_update += 1


class BagTracker:
    def __init__(self):
        self._next_id = 1
        self.tracks: List[Track] = []

    def _new_id(self) -> int:
        tid = self._next_id
        self._next_id += 1
        return tid

    def update(self, detections: List[Detection]) -> List[Track]:
        for t in self.tracks:
            t.age += 1

        if self.tracks and detections:
            cost = np.zeros((len(self.tracks), len(detections)), dtype=np.float32)
            for i, t in enumerate(self.tracks):
                pred = t.predicted_bbox()
                for j, d in enumerate(detections):
                    cost[i, j] = 1.0 - iou(pred, d.bbox)
            row_ind, col_ind = linear_sum_assignment(cost)

            matched_tracks, matched_dets = set(), set()
            for r, c in zip(row_ind, col_ind):
                if cost[r, c] <= (1.0 - settings.tracker_iou_threshold):
                    self.tracks[r].update(detections[c])
                    matched_tracks.add(r)
                    matched_dets.add(c)

            for i, t in enumerate(self.tracks):
                if i not in matched_tracks:
                    t.mark_missed()
            unmatched_dets = [d for j, d in enumerate(detections) if j not in matched_dets]
        else:
            for t in self.tracks:
                t.mark_missed()
            unmatched_dets = detections

        for d in unmatched_dets:
            new_track = Track(track_id=self._new_id(), bbox=d.bbox, score=d.score)
            new_track.history.append((new_track.cx, new_track.cy))
            new_track.areas.append(d.area)
            self.tracks.append(new_track)

        self.tracks = [
            t for t in self.tracks if t.time_since_update <= settings.tracker_max_age
        ]
        return self.tracks
