"""Typed frame-local detections: scores never travel in a parallel list."""
from dataclasses import dataclass
from typing import Tuple
import math

@dataclass(frozen=True)
class Detection:
    bbox: Tuple[float, float, float, float]
    class_id: int
    class_name: str
    confidence: float
    detection_index: int = 0

    def valid(self):
        return (len(self.bbox) == 4 and all(math.isfinite(x) for x in self.bbox)
                and self.bbox[2] > self.bbox[0] and self.bbox[3] > self.bbox[1]
                and math.isfinite(self.confidence) and 0 <= self.confidence <= 1)

@dataclass(frozen=True)
class TrackResult:
    bbox: Tuple[float, float, float, float]
    track_id: int
    class_id: int
    class_name: str
    confidence: float
    detection_index: int
