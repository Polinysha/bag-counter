"""
Unit tests for postprocess_detections (app/worker/pipeline/detector.py).

This is the one real logic in the detection module that doesn't require
MMDetection/torch to exercise - it's plain confidence/size filtering and
label-index mapping over numpy arrays, the same shape as what
BagDetector.infer() gets back from inference_detector(). BagDetector
itself still isn't unit-tested (it needs a real loaded model to produce
those arrays in the first place - see README "Known Limitations" /
ROADMAP.md), but this covers the part of it that's actually at risk of
a silent regression: get the threshold direction wrong, or the label
index wrong, and every count downstream is wrong too.
"""

import numpy as np

from app.config import settings
from app.worker.pipeline.detector import postprocess_detections

FRAME_W, FRAME_H = 640, 480
FRAME_AREA = float(FRAME_W * FRAME_H)
CLASS_NAMES = ["person", "bag_candidate", "car"]


def _box_with_area_ratio(ratio: float) -> tuple[float, float, float, float]:
    """A square box near the frame center whose area is `ratio` of the frame."""
    side = (ratio * FRAME_AREA) ** 0.5
    cx, cy = FRAME_W / 2, FRAME_H / 2
    return (cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)


def test_detection_below_score_threshold_is_dropped(monkeypatch):
    monkeypatch.setattr(settings, "detection_score_thr", 0.5)
    boxes = np.array([_box_with_area_ratio(0.05)])
    scores = np.array([0.49])
    labels = np.array([1])

    result = postprocess_detections(
        boxes, scores, labels, class_names=CLASS_NAMES, frame_area=FRAME_AREA
    )
    assert result == []


def test_detection_at_or_above_score_threshold_is_kept(monkeypatch):
    monkeypatch.setattr(settings, "detection_score_thr", 0.5)
    boxes = np.array([_box_with_area_ratio(0.05)])
    scores = np.array([0.5])
    labels = np.array([1])

    result = postprocess_detections(
        boxes, scores, labels, class_names=CLASS_NAMES, frame_area=FRAME_AREA
    )
    assert len(result) == 1
    assert result[0].score == 0.5


def test_box_smaller_than_min_area_ratio_is_dropped(monkeypatch):
    monkeypatch.setattr(settings, "detection_score_thr", 0.0)
    monkeypatch.setattr(settings, "min_box_area_ratio", 0.01)
    monkeypatch.setattr(settings, "max_box_area_ratio", 1.0)
    boxes = np.array([_box_with_area_ratio(0.005)])  # below the 0.01 floor
    scores = np.array([0.9])
    labels = np.array([0])

    result = postprocess_detections(
        boxes, scores, labels, class_names=CLASS_NAMES, frame_area=FRAME_AREA
    )
    assert result == []


def test_box_larger_than_max_area_ratio_is_dropped(monkeypatch):
    monkeypatch.setattr(settings, "detection_score_thr", 0.0)
    monkeypatch.setattr(settings, "min_box_area_ratio", 0.0)
    monkeypatch.setattr(settings, "max_box_area_ratio", 0.2)
    boxes = np.array([_box_with_area_ratio(0.3)])  # above the 0.2 ceiling
    scores = np.array([0.9])
    labels = np.array([0])

    result = postprocess_detections(
        boxes, scores, labels, class_names=CLASS_NAMES, frame_area=FRAME_AREA
    )
    assert result == []


def test_box_within_area_range_is_kept(monkeypatch):
    monkeypatch.setattr(settings, "detection_score_thr", 0.0)
    monkeypatch.setattr(settings, "min_box_area_ratio", 0.01)
    monkeypatch.setattr(settings, "max_box_area_ratio", 0.5)
    boxes = np.array([_box_with_area_ratio(0.1)])
    scores = np.array([0.9])
    labels = np.array([0])

    result = postprocess_detections(
        boxes, scores, labels, class_names=CLASS_NAMES, frame_area=FRAME_AREA
    )
    assert len(result) == 1


def test_label_index_maps_to_class_name(monkeypatch):
    monkeypatch.setattr(settings, "detection_score_thr", 0.0)
    monkeypatch.setattr(settings, "min_box_area_ratio", 0.0)
    monkeypatch.setattr(settings, "max_box_area_ratio", 1.0)
    boxes = np.array([_box_with_area_ratio(0.05)])
    scores = np.array([0.9])
    labels = np.array([1])  # index 1 -> "bag_candidate"

    result = postprocess_detections(
        boxes, scores, labels, class_names=CLASS_NAMES, frame_area=FRAME_AREA
    )
    assert result[0].label == "bag_candidate"


def test_label_index_out_of_range_falls_back_to_raw_value(monkeypatch):
    monkeypatch.setattr(settings, "detection_score_thr", 0.0)
    monkeypatch.setattr(settings, "min_box_area_ratio", 0.0)
    monkeypatch.setattr(settings, "max_box_area_ratio", 1.0)
    boxes = np.array([_box_with_area_ratio(0.05)])
    scores = np.array([0.9])
    labels = np.array([99])  # far beyond len(CLASS_NAMES)

    result = postprocess_detections(
        boxes, scores, labels, class_names=CLASS_NAMES, frame_area=FRAME_AREA
    )
    assert result[0].label == "99"


def test_multiple_detections_filtered_independently(monkeypatch):
    monkeypatch.setattr(settings, "detection_score_thr", 0.5)
    monkeypatch.setattr(settings, "min_box_area_ratio", 0.01)
    monkeypatch.setattr(settings, "max_box_area_ratio", 0.5)
    boxes = np.array(
        [
            _box_with_area_ratio(0.05),  # passes everything
            _box_with_area_ratio(0.05),  # fails on score
            _box_with_area_ratio(0.005),  # fails on min area
        ]
    )
    scores = np.array([0.9, 0.2, 0.9])
    labels = np.array([0, 0, 0])

    result = postprocess_detections(
        boxes, scores, labels, class_names=CLASS_NAMES, frame_area=FRAME_AREA
    )
    assert len(result) == 1


def test_empty_input_returns_empty_list():
    result = postprocess_detections(
        np.empty((0, 4)),
        np.empty((0,)),
        np.empty((0,)),
        class_names=CLASS_NAMES,
        frame_area=FRAME_AREA,
    )
    assert result == []


def test_zero_frame_area_does_not_raise():
    # defensive: a malformed/zero-size frame shouldn't crash the pipeline
    # with a ZeroDivisionError - postprocess_detections treats it as
    # area_ratio 0.0, which the default min_box_area_ratio (> 0) then drops.
    result = postprocess_detections(
        np.array([(0.0, 0.0, 10.0, 10.0)]),
        np.array([0.9]),
        np.array([0]),
        class_names=CLASS_NAMES,
        frame_area=0.0,
    )
    assert result == []
