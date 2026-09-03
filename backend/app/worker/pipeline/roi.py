from typing import List, Tuple

import cv2
import numpy as np

from app.config import settings


class SceneGeometry:
    """Resolves the normalized ROI polygon / counting line from
    config.py into pixel coordinates for a specific video resolution."""

    def __init__(self, frame_w: int, frame_h: int):
        self.w, self.h = frame_w, frame_h
        self.roi_polygon = np.array(
            [[x * frame_w, y * frame_h] for x, y in settings.roi_polygon],
            dtype=np.int32,
        )
        (lx1, ly1), (lx2, ly2) = settings.counting_line
        self.line = (
            (lx1 * frame_w, ly1 * frame_h),
            (lx2 * frame_w, ly2 * frame_h),
        )

    def point_in_roi(self, x: float, y: float) -> bool:
        return cv2.pointPolygonTest(self.roi_polygon, (float(x), float(y)), False) >= 0

    @staticmethod
    def _side(p, a, b) -> float:
        """Sign of the cross product => which side of line a->b point p is on."""
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])

    def crossed_line(self, prev_pt: Tuple[float, float], cur_pt: Tuple[float, float]) -> bool:
        """True if the segment prev_pt->cur_pt crosses the counting line
        in the configured 'forward' direction (belt travel direction)."""
        a, b = self.line
        side_prev = self._side(prev_pt, a, b)
        side_cur = self._side(cur_pt, a, b)
        if side_prev == 0 or side_cur == 0:
            return False
        crossed = (side_prev > 0) != (side_cur > 0)
        if not crossed:
            return False
        if settings.count_direction == "forward":
            return side_prev > 0 and side_cur < 0
        return side_prev < 0 and side_cur > 0
