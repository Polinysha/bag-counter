from dataclasses import dataclass

from app.worker.pipeline.roi import SceneGeometry
from app.worker.pipeline.tracker import Track


@dataclass
class CrossingEvent:
    frame_idx: int
    track_id: int
    area: float


class BagCounter:
    """
    Counts a bag exactly once, the moment its track's centroid crosses
    the counting line in the belt's travel direction. Using a
    per-track `counted` flag (rather than e.g. counting every frame a
    box overlaps the line) is what prevents a single bag - which spans
    several frames and pixels around the line - from being counted
    more than once, and is robust to a couple of missed detections
    right at the line since the track itself persists (tracker_max_age).
    """

    def __init__(self, geometry: SceneGeometry):
        self.geometry = geometry
        self.count = 0

    def process(self, tracks: list[Track], frame_idx: int) -> list[CrossingEvent]:
        events: list[CrossingEvent] = []
        for t in tracks:
            if not t.confirmed or t.counted:
                continue
            if len(t.history) < 2:
                continue
            prev_pt, cur_pt = t.history[-2], t.history[-1]
            if self.geometry.crossed_line(prev_pt, cur_pt):
                t.counted = True
                self.count += 1
                area = t.areas[-1] if t.areas else 0.0
                events.append(CrossingEvent(frame_idx=frame_idx, track_id=t.track_id, area=area))
        return events
