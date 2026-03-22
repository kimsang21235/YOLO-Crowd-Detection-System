# Architecture Notes

## 전체 구조

```
Client (React)
    │
    ├── REST API (HTTP)
    │       POST /process-video   → 업로드 영상 분석
    │       GET  /videos/:name    → 결과 영상 스트리밍
    │       GET  /events/:id      → 이벤트 로그 조회
    │
    └── WebSocket  /ws/video_feed/:stream_id
            ← bytes  (JPEG 프레임)
            ← text   "PLAY_SOUND"
            → JSON   { type: "update_analysis", payload: [...] }

FastAPI (backend)
    ├── app.py              lifespan 등록, CORS, 라우터 마운트
    ├── video_monitor/
    │   ├── routes.py       엔드포인트 정의
    │   ├── config.py       pydantic-settings 기반 환경변수 로드
    │   ├── dependencies.py YOLO 모델 싱글톤
    │   ├── schemas.py      Pydantic 응답 모델
    │   └── services/
    │       ├── stream_service.py    실시간 처리 (FFmpeg + YOLO)
    │       └── video_processor.py  업로드 영상 후처리
    └── config/
        ├── streams.json    스트림 소스 목록
        └── roi.json        ROI 구역 좌표
```

## 실시간 스트리밍 흐름

```
WebSocket 연결
    │
    ├── client_listener task  ← 클라이언트 분석옵션 변경 수신
    │
    └── producer task
            │
            ▼
        stream_frames()
            │
            ├── StreamRegistry.get_stream_details()
            │       yt-dlp / OpenCV 로 소스 URL 해석 (5분 캐싱)
            │
            ├── FFmpeg subprocess (rawvideo pipe)
            │       scale → width×height×BGR bytes
            │
            ├── asyncio.to_thread → FrameProcessor.process()
            │       YOLO track (ByteTrack)
            │       heatmap / mosaic / count 오버레이
            │       JPEG 인코딩
            │
            └── EventStore.maybe_save()  혼잡 시 이벤트 이미지 저장
```

## 설계 결정

### FFmpeg 파이프라인 채택 이유
`cv2.VideoCapture`는 일부 YouTube/RTSP 스트림에서 디코딩 실패가 발생했습니다.
FFmpeg는 스트림 호환성이 넓고, `-vf scale` 옵션으로 해상도 조정도 한 번에 처리됩니다.

### 모자이크 구현 통일
업로드 영상(`video_processor.py`)과 실시간 스트리밍(`stream_service.py`) 모두
`_apply_mosaic()` 함수(픽셀화 방식)를 공유합니다.
GaussianBlur와 픽셀화가 혼재하던 이전 구조를 통일했습니다.

### 혼잡도 임계값 환경변수화
`CONGESTION_THRESHOLD`를 `.env`에서 관리하므로 코드 변경 없이 운영 환경별로 조정 가능합니다.

### EventStore 비동기 큐
이벤트 이미지 저장은 별도 worker task가 처리합니다.
WebSocket 전송 루프를 블로킹하지 않으면서 파일 I/O를 수행합니다.
