"""사람 감지. 안치실 벽면은 움직이지 않으므로 '움직임 = 참배객'이 가장 싸고 확실한 신호다.
OpenCV 4.x면 HOG 보행자 감지를, 모델 파일이 있으면 YuNet 얼굴 감지를 함께 쓴다(있으면 켜지고 없으면 조용히 건너뜀)."""
import os
import time

import cv2
import numpy as np


class MotionDetector:
    """MOG2 배경 차분. 화면의 min_area 비율 이상이 움직이면 사람으로 본다."""

    def __init__(self, min_area_ratio: float = 0.004, warmup_frames: int = 30) -> None:
        self.bg = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=32, detectShadows=False)
        self.min_area_ratio = min_area_ratio
        self.warmup = warmup_frames
        self.frames = 0

    def detect(self, small: np.ndarray) -> int:
        self.frames += 1
        mask = self.bg.apply(small)
        if self.frames < self.warmup:
            return 0
        mask = cv2.medianBlur(mask, 5)
        mask = cv2.dilate(mask, None, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_area = small.shape[0] * small.shape[1] * self.min_area_ratio
        return sum(1 for c in contours if cv2.contourArea(c) >= min_area)


class HOGDetector:
    available = hasattr(cv2, "HOGDescriptor")

    def __init__(self) -> None:
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, small: np.ndarray) -> int:
        rects, weights = self.hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
        return int(sum(1 for w in weights if w > 0.5)) if len(rects) else 0


class YuNetFaceDetector:
    def __init__(self, model_path: str) -> None:
        self.det = cv2.FaceDetectorYN.create(model_path, "", (320, 320), score_threshold=0.7)

    def detect(self, small: np.ndarray) -> int:
        h, w = small.shape[:2]
        self.det.setInputSize((w, h))
        _, faces = self.det.detect(small)
        return 0 if faces is None else len(faces)


class PersonDetector:
    """여러 감지기를 합치고, 마지막 감지 뒤 hold_seconds 동안 '사람 있음'을 유지한다(깜박임 방지)."""

    def __init__(self, hold_seconds: float = 3.0, work_width: int = 480) -> None:
        self.hold = hold_seconds
        self.work_width = work_width
        self.detectors: list = [MotionDetector()]
        self.names = ["motion"]
        if HOGDetector.available:
            self.detectors.append(HOGDetector())
            self.names.append("hog")
        model = os.getenv("FACE_MODEL_PATH", "")
        if model and os.path.exists(model) and hasattr(cv2, "FaceDetectorYN"):
            self.detectors.append(YuNetFaceDetector(model))
            self.names.append("yunet")
        self.last_seen = 0.0
        self.persons = 0

    def update(self, frame: np.ndarray) -> tuple[bool, int]:
        h, w = frame.shape[:2]
        scale = self.work_width / w
        small = cv2.resize(frame, (self.work_width, int(h * scale)), interpolation=cv2.INTER_AREA)
        persons = 0
        for d in self.detectors:
            try:
                persons = max(persons, d.detect(small))
            except cv2.error:
                continue
        now = time.time()
        if persons:
            self.last_seen = now
            self.persons = persons
        occupied = now - self.last_seen < self.hold
        if not occupied:
            self.persons = 0
        return occupied, self.persons
