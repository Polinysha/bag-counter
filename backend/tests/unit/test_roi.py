"""Unit tests for SceneGeometry (app/worker/pipeline/roi.py). Pure
geometry - no video, no model, no DB - so these run in milliseconds
and don't need the lite/full image distinction at all."""

from app.worker.pipeline.roi import SceneGeometry


def test_point_in_roi_true_for_center_of_default_polygon():
    geometry = SceneGeometry(frame_w=100, frame_h=100)
    assert geometry.point_in_roi(30, 60) is True


def test_point_in_roi_false_far_outside_polygon():
    geometry = SceneGeometry(frame_w=100, frame_h=100)
    assert geometry.point_in_roi(99, 5) is False


def test_crossed_line_detects_forward_crossing():
    geometry = SceneGeometry(frame_w=100, frame_h=100)
    (x1, y1), (x2, y2) = geometry.line
    # a point just on each side of the line, perpendicular offset
    nx, ny = -(y2 - y1), (x2 - x1)
    mid = ((x1 + x2) / 2, (y1 + y2) / 2)
    prev_pt = (mid[0] + nx * 0.05, mid[1] + ny * 0.05)
    cur_pt = (mid[0] - nx * 0.05, mid[1] - ny * 0.05)
    # one of the two directions must register as a crossing
    assert geometry.crossed_line(prev_pt, cur_pt) or geometry.crossed_line(cur_pt, prev_pt)


def test_crossed_line_false_when_staying_on_one_side():
    geometry = SceneGeometry(frame_w=100, frame_h=100)
    assert geometry.crossed_line((5, 5), (6, 6)) is False
