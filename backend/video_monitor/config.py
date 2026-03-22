from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parent.parent


def _load_json(path: Path, default: Any) -> Any:
    if path.exists():
        with path.open(encoding='utf-8') as f:
            return json.load(f)
    return default


class Settings(BaseSettings):
    # 모델
    model_path: Path = BASE_DIR / 'models' / 'yolov8n.pt'

    # 디렉터리
    uploads_dir: Path = BASE_DIR / 'data' / 'uploads'
    outputs_dir: Path = BASE_DIR / 'data' / 'outputs'

    # 스트림/ROI 설정 파일 경로
    stream_config_path: Path = BASE_DIR / 'config' / 'streams.json'
    roi_config_path: Path = BASE_DIR / 'config' / 'roi.json'

    # CORS — 쉼표로 구분된 오리진 목록
    allowed_origins_raw: str = 'http://localhost:3000'

    # 혼잡도
    congestion_threshold: int = 5
    event_save_interval_seconds: float = 5.0
    event_sound_interval_seconds: float = 3.0

    # 영상 품질
    frame_jpeg_quality: int = 85
    stream_target_width: int = 854
    stream_target_height: int = 480

    # YouTube 쿠키 (선택)
    youtube_cookie_file: str | None = None

    # 관리자 API 시크릿
    cleanup_secret: str = 'changeme'

    class Config:
        env_file = BASE_DIR / '.env'
        env_file_encoding = 'utf-8'

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins_raw.split(',') if o.strip()]

    @property
    def stream_sources(self) -> dict:
        return _load_json(self.stream_config_path, {})

    @property
    def roi_config(self) -> dict:
        return _load_json(
            self.roi_config_path,
            {'base_resolution': [1920, 1080], 'zones': {}},
        )

    def setup_dirs(self) -> None:
        for d in (self.uploads_dir, self.outputs_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.setup_dirs()
