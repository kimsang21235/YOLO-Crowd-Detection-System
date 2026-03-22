from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from video_monitor.services.stream_service import _apply_mosaic


class UploadedVideoProcessor:
    """업로드된 영상 파일을 프레임 단위로 분석 후 결과 mp4를 저장합니다."""

    def __init__(self, model: YOLO) -> None:
        self.model = model

    def process(self, input_path: Path, output_path: Path, analysis_type: str) -> None:
        cap = cv2.VideoCapture(str(input_path))
        if not cap.isOpened():
            raise RuntimeError(f'Cannot open input video: {input_path}')

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
        track_history: dict[int, list[tuple[float, float]]] = defaultdict(list)

        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break

                if analysis_type == 'mosaic':
                    writer.write(self._apply_mosaic_frame(frame))
                elif analysis_type == 'tracking':
                    writer.write(self._apply_tracking_frame(frame, track_history))
                else:
                    raise ValueError(f'Unsupported analysis type: {analysis_type}')
        finally:
            cap.release()
            writer.release()

    def _apply_mosaic_frame(self, frame: np.ndarray) -> np.ndarray:
        """모자이크(픽셀화) 처리 — stream_service._apply_mosaic 와 동일 방식."""
        result = frame.copy()
        results = self.model.predict(
            source=frame, conf=0.25, imgsz=640, verbose=False, classes=[0]
        )
        if not results or results[0].boxes is None or len(results[0].boxes) == 0:
            return result

        for box in results[0].boxes.xyxy.cpu().numpy():
            x1, y1, x2, y2 = map(int, box)
            _apply_mosaic(result, x1, y1, x2, y2)

        return result

    def _apply_tracking_frame(
        self,
        frame: np.ndarray,
        track_history: dict[int, list[tuple[float, float]]],
    ) -> np.ndarray:
        result = frame.copy()
        results = self.model.track(
            source=frame,
            persist=True,
            verbose=False,
            tracker='bytetrack.yaml',
            classes=[0],
        )

        if (
            not results
            or results[0].boxes is None
            or results[0].boxes.id is None
        ):
            return result

        boxes = results[0].boxes.xywh.cpu()
        track_ids = results[0].boxes.id.int().cpu().tolist()

        for box, track_id in zip(boxes, track_ids):
            x, y, w, h = box
            history = track_history[track_id]
            history.append((float(x), float(y)))
            if len(history) > 30:
                history.pop(0)

            x1, y1 = int(x - w / 2), int(y - h / 2)
            x2, y2 = int(x + w / 2), int(y + h / 2)
            cv2.rectangle(result, (x1, y1), (x2, y2), (0, 255, 0), 2)

            points = np.array(history, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(result, [points], isClosed=False, color=(230, 230, 230), thickness=4)

        return result
