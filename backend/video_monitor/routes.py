from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from video_monitor.config import settings
from video_monitor.dependencies import get_model
from video_monitor.schemas import CleanupResponse, EventItem, VideoProcessResponse
from video_monitor.services.stream_service import EventStore, StreamRegistry, stream_frames
from video_monitor.services.video_processor import UploadedVideoProcessor

router = APIRouter()
registry = StreamRegistry()
event_store = EventStore()


# ---------------------------------------------------------------------------
# 업로드 영상 분석
# ---------------------------------------------------------------------------

@router.post('/process-video', response_model=VideoProcessResponse)
async def process_video_endpoint(
    file: UploadFile = File(...),
    anonymize: str = Form('false'),
    visualize: str = Form('false'),
) -> VideoProcessResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail='No file selected')

    temp_filename = f'{uuid.uuid4().hex}_{file.filename}'
    input_path = settings.uploads_dir / temp_filename
    input_path.write_bytes(await file.read())

    is_anonymize = anonymize.lower() == 'true'
    analysis_type = 'mosaic' if is_anonymize else 'tracking'
    output_filename = f'result_{analysis_type}_{Path(temp_filename).stem}.mp4'
    output_path = settings.outputs_dir / output_filename

    processor = UploadedVideoProcessor(get_model())
    try:
        await run_in_threadpool(processor.process, input_path, output_path, analysis_type)
    finally:
        input_path.unlink(missing_ok=True)

    return VideoProcessResponse(
        message='Video processing complete.',
        analysis_type=analysis_type,
        processed_video_url=f'/videos/{output_filename}',
    )


@router.get('/videos/{filename}')
async def serve_video(filename: str):
    file_path = settings.outputs_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail='File not found')
    return FileResponse(file_path)


# ---------------------------------------------------------------------------
# 실시간 스트리밍 (WebSocket)
# ---------------------------------------------------------------------------

@router.websocket('/ws/video_feed/{stream_id}')
async def websocket_video_feed(
    websocket: WebSocket,
    stream_id: str,
    analysis: str = 'count',
) -> None:
    await websocket.accept()
    analysis_config: dict[str, list[str]] = {'types': analysis.split(',') if analysis else []}
    data_queue: asyncio.Queue[bytes | str | None] = asyncio.Queue()

    async def client_listener() -> None:
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if payload.get('type') == 'update_analysis':
                    analysis_config['types'] = payload.get('payload', [])
        except WebSocketDisconnect:
            return

    async def producer() -> None:
        try:
            async for data in stream_frames(
                stream_id, analysis_config, get_model(), registry, event_store
            ):
                await data_queue.put(data)
        finally:
            await data_queue.put(None)

    listener_task = asyncio.create_task(client_listener())
    producer_task = asyncio.create_task(producer())

    try:
        while True:
            item = await data_queue.get()
            if item is None:
                break
            try:
                if isinstance(item, bytes):
                    await websocket.send_bytes(item)
                else:
                    await websocket.send_text(item)
            except (WebSocketDisconnect, RuntimeError):
                break
    except WebSocketDisconnect:
        pass
    finally:
        listener_task.cancel()
        producer_task.cancel()
        await asyncio.gather(listener_task, producer_task, return_exceptions=True)


# ---------------------------------------------------------------------------
# 이벤트 이미지 조회
# ---------------------------------------------------------------------------

@router.get('/outputs/{stream_id}/{filename}')
async def serve_event_file(stream_id: str, filename: str):
    file_path = settings.outputs_dir / stream_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail='File not found')
    return FileResponse(file_path)


@router.get('/events/{stream_id}', response_model=list[EventItem])
async def get_events(stream_id: str) -> list[EventItem]:
    events_dir = settings.outputs_dir / stream_id
    if not events_dir.exists():
        return []

    events: list[EventItem] = []
    # mp4 파일 기준으로 이벤트 목록 구성
    for file_path in events_dir.glob('event_*.mp4'):
        try:
            parts = file_path.stem.split('_')
            timestamp_str = f'{parts[1]}_{parts[2]}'
            person_count = int(parts[3])
            dt_obj = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
        except (IndexError, ValueError):
            continue

        thumb_name = file_path.stem + '_thumb.jpg'
        thumb_path = events_dir / thumb_name
        thumbnail_url = (
            f'/outputs/{stream_id}/{thumb_name}'
            if thumb_path.exists()
            else ''
        )

        events.append(EventItem(
            id=file_path.name,
            status=f'혼잡도 감지: {person_count}명',
            timestamp=dt_obj.strftime('%Y-%m-%d %H:%M:%S'),
            video_url=f'/outputs/{stream_id}/{file_path.name}',
            thumbnail_url=thumbnail_url,
        ))

    events.sort(key=lambda e: e.timestamp, reverse=True)
    return events


# ---------------------------------------------------------------------------
# 관리자 — 이벤트 이미지 전체 삭제 (시크릿 키 인증)
# ---------------------------------------------------------------------------

def _verify_cleanup_secret(x_cleanup_secret: str = Header(...)) -> None:
    if x_cleanup_secret != settings.cleanup_secret:
        raise HTTPException(status_code=403, detail='Invalid cleanup secret')


@router.post(
    '/admin/cleanup-events',
    response_model=CleanupResponse,
    dependencies=[Depends(_verify_cleanup_secret)],
)
async def cleanup_old_events() -> CleanupResponse:
    deleted = 0
    for pattern in ('event_*.mp4', 'event_*_thumb.jpg'):
        for file_path in settings.outputs_dir.rglob(pattern):
            file_path.unlink(missing_ok=True)
            deleted += 1
    return CleanupResponse(deleted=deleted)
