from __future__ import annotations

from ultralytics import YOLO

from video_monitor.config import settings

_model: YOLO | None = None


def get_model() -> YOLO:
    """YOLO 모델 싱글톤을 반환합니다."""
    global _model
    if _model is None:
        import torch
        _model = YOLO(str(settings.model_path))
        device = f'GPU: {torch.cuda.get_device_name(0)}' if torch.cuda.is_available() else 'CPU'
        print(f'[YOLO] Model loaded: {settings.model_path.name} | Device: {device}')
    return _model
