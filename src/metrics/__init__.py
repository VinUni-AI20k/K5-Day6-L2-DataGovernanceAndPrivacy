"""Metric library for T14 (box matching). `src/metrics/tracks.py` wires it into the T14 evaluator."""
from .detection import iou_xywh, match_detections, detection_prf

__all__ = ["iou_xywh", "match_detections", "detection_prf"]
