"""
Thin wrapper around an MMDetection model.

Design note (see README "Подход к детекции" for the full rationale):
the conveyor is a controlled scene where the only moving foreground
objects inside the belt ROI are bags. Rather than requiring a
bag-labelled training set (none was provided with the task), we run a
standard MMDetection COCO-pretrained detector and keep every detection
above a confidence/size threshold whose center falls inside the
conveyor ROI, regardless of the COCO label the model assigned it
(class-agnostic use of the detector). This is a pragmatic choice for
the scope of this task; swapping in a fine-tuned single-class "bag"
checkpoint later is a one-line config change (BC_MMDET_CONFIG /
BC_MMDET_CHECKPOINT) and nothing else in the pipeline has to change.
"""

from dataclasses import dataclass

import numpy as np

from app.config import settings


@dataclass
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    score: float
    label: str

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def area(self) -> float:
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)

    @property
    def bbox(self):
        return (self.x1, self.y1, self.x2, self.y2)


class BagDetector:
    """Loads once per worker process, reused across all frames/videos."""

    def __init__(self):
        from mmdet.apis import init_detector  # local import: heavy dep

        self._model = init_detector(
            settings.mmdet_config,
            settings.mmdet_checkpoint,
            device=settings.mmdet_device,
        )
        self._class_names = self._model.dataset_meta["classes"]

    def infer(self, frame_bgr: np.ndarray) -> list[Detection]:
        from mmdet.apis import inference_detector

        h, w = frame_bgr.shape[:2]
        frame_area = float(h * w)
        result = inference_detector(self._model, frame_bgr)

        pred = result.pred_instances
        boxes = pred.bboxes.cpu().numpy()
        scores = pred.scores.cpu().numpy()
        labels = pred.labels.cpu().numpy()

        detections: list[Detection] = []
        for box, score, label in zip(boxes, scores, labels, strict=False):
            if score < settings.detection_score_thr:
                continue
            x1, y1, x2, y2 = box.tolist()
            area_ratio = ((x2 - x1) * (y2 - y1)) / frame_area
            if not (settings.min_box_area_ratio <= area_ratio <= settings.max_box_area_ratio):
                continue
            detections.append(
                Detection(
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    score=float(score),
                    label=self._class_names[int(label)]
                    if int(label) < len(self._class_names)
                    else str(label),
                )
            )
        return detections


class MockDetector:
    """
    Motion-based stand-in used automatically when MMDetection / the
    checkpoint isn't available (e.g. quick local smoke-tests without
    downloading model weights). Never used when BC_MMDET_CHECKPOINT
    loads successfully. See README for details.
    """

    def __init__(self):
        import cv2

        self._bgsub = cv2.createBackgroundSubtractorMOG2(
            history=300, varThreshold=40, detectShadows=False
        )

    def infer(self, frame_bgr: np.ndarray) -> list[Detection]:
        import cv2

        h, w = frame_bgr.shape[:2]
        frame_area = float(h * w)
        mask = self._bgsub.apply(frame_bgr)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.dilate(mask, np.ones((9, 9), np.uint8), iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections: list[Detection] = []
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            area_ratio = (bw * bh) / frame_area
            if not (settings.min_box_area_ratio <= area_ratio <= settings.max_box_area_ratio):
                continue
            detections.append(
                Detection(
                    x1=x,
                    y1=y,
                    x2=x + bw,
                    y2=y + bh,
                    score=0.5,
                    label="bag_candidate",
                )
            )
        return detections


def build_detector():
    try:
        return BagDetector()
    except Exception as exc:  # pragma: no cover - environment dependent
        import logging

        logging.getLogger(__name__).warning(
            "Falling back to MockDetector, MMDetection unavailable: %s", exc
        )
        return MockDetector()
