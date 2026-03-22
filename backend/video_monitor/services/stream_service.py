from __future__ import annotations

import asyncio
import collections
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

import cv2
import numpy as np
import yt_dlp
from ultralytics import YOLO

from video_monitor.config import settings


# ---------------------------------------------------------------------------
# 스트림 메타데이터
# ---------------------------------------------------------------------------

@dataclass
class StreamDetails:
    source_path: str
    width: int
    height: int


class StreamRegistry:
    """스트림 설정을 로드하고 소스 URL을 캐싱합니다."""

    CACHE_TTL = 300  # seconds

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, StreamDetails]] = {}

    def _roi_config(self) -> dict:
        return settings.roi_config

    def get_stream_details(self, stream_id: str) -> StreamDetails:
        now = time.time()
        cached = self._cache.get(stream_id)
        if cached and now - cached[0] < self.CACHE_TTL:
            return cached[1]

        streams = settings.stream_sources
        stream_info = streams.get(stream_id)
        if not stream_info:
            raise KeyError(f'Unknown stream_id: {stream_id}')

        stream_type = stream_info.get('type')
        path = stream_info.get('path')
        if not stream_type or not path:
            raise ValueError(f'Invalid stream configuration for {stream_id}')

        details = self._resolve(stream_type, path)
        self._cache[stream_id] = (now, details)
        return details

    def _resolve(self, stream_type: str, path: str) -> StreamDetails:
        if stream_type == 'youtube':
            ydl_opts: dict = {'format': '94', 'noplaylist': True}
            if settings.youtube_cookie_file:
                ydl_opts['cookiefile'] = settings.youtube_cookie_file
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(path, download=False)
            return StreamDetails(
                source_path=info['url'],
                width=info.get('width') or 1280,
                height=info.get('height') or 720,
            )

        if stream_type in {'local', 'http', 'rtsp'}:
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                raise RuntimeError(f'Cannot open stream source: {path}')
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
            cap.release()
            return StreamDetails(source_path=path, width=width, height=height)

        raise ValueError(f'Unsupported stream type: {stream_type}')

    def get_scaled_zones(self, stream_id: str, frame_w: int, frame_h: int) -> np.ndarray:
        roi_cfg = self._roi_config()
        base_w, base_h = roi_cfg.get('base_resolution', [1920, 1080])
        zones_raw = roi_cfg.get('zones', {}).get(stream_id, [])
        original = np.array(zones_raw, dtype=np.float32)

        if len(original) == 0:
            return np.array([], dtype=np.int32)
        if frame_w == base_w and frame_h == base_h:
            return original.astype(np.int32)

        scale = np.array([frame_w / base_w, frame_h / base_h], dtype=np.float32)
        return (original * scale).astype(np.int32)


# ---------------------------------------------------------------------------
# 이벤트 저장 (비동기 큐)
# ---------------------------------------------------------------------------

def _save_event_video_blocking(
    file_path: Path,
    thumb_path: Path,
    frames: list,
    fps: float,
) -> None:
    """mp4 영상 + 썸네일 jpg를 동기로 저장합니다."""
    if not frames:
        return
    file_path.parent.mkdir(parents=True, exist_ok=True)
    h, w = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*'avc1')
    writer = cv2.VideoWriter(str(file_path), fourcc, fps, (w, h))
    for f in frames:
        writer.write(f)
    writer.release()

    # 썸네일: 중간 프레임
    mid = frames[len(frames) // 2]
    cv2.imwrite(str(thumb_path), mid)


class EventStore:
    """혼잡 이벤트 영상(mp4)을 비동기 큐로 저장합니다."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self._last_saved: dict[str, float] = {}

    async def worker(self) -> None:
        while True:
            item = await self.queue.get()
            try:
                file_path, thumb_path, frames, fps = item
                await asyncio.to_thread(
                    _save_event_video_blocking, file_path, thumb_path, frames, fps
                )
                print(f'[EventStore] Saved: {file_path.name}')
            except Exception as e:
                print(f'[EventStore error] {e}')
            finally:
                self.queue.task_done()

    def should_save(self, stream_id: str) -> bool:
        now = time.time()
        return now - self._last_saved.get(stream_id, 0.0) >= settings.event_save_interval_seconds

    def mark_saved(self, stream_id: str) -> None:
        self._last_saved[stream_id] = time.time()

    async def save_video(
        self,
        stream_id: str,
        frames: list,
        fps: float,
        person_count: int,
    ) -> None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base = f'event_{timestamp}_{person_count}'
        file_path = settings.outputs_dir / stream_id / f'{base}.mp4'
        thumb_path = settings.outputs_dir / stream_id / f'{base}_thumb.jpg'
        await self.queue.put((file_path, thumb_path, list(frames), fps))


# ---------------------------------------------------------------------------
# 프레임 처리
# ---------------------------------------------------------------------------

def _apply_mosaic(frame: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> None:
    """픽셀화 방식의 모자이크를 frame에 in-place로 적용합니다."""
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return
    h, w = roi.shape[:2]
    pixel_w = max(1, w // 15)
    pixel_h = max(1, h // 15)
    small = cv2.resize(roi, (pixel_w, pixel_h), interpolation=cv2.INTER_LINEAR)
    frame[y1:y2, x1:x2] = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


class FrameProcessor:
    """YOLO 추론 + 분석 옵션 적용 + JPEG 인코딩."""

    def __init__(self, model: YOLO, registry: StreamRegistry) -> None:
        self.model = model
        self.registry = registry
        self._last_sound_time: dict[str, float] = {}

    def process(
        self,
        frame: np.ndarray,
        analysis_types: list[str],
        stream_id: str,
    ) -> tuple[bytes | None, int, bool, bool]:
        """
        Returns:
            (jpeg_bytes | None, person_count, trigger_sound, is_congested)
        """
        zones = self.registry.get_scaled_zones(stream_id, frame.shape[1], frame.shape[0])
        processed = frame.copy()

        # YOLO 추적
        results = self.model.track(
            source=frame,
            persist=True,
            verbose=False,
            half=False,
            tracker='bytetrack.yaml',
            classes=[0],
            imgsz=640,
        )

        detections: list[dict] = []
        if results and results[0].boxes is not None and len(results[0].boxes) > 0:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            classes = results[0].boxes.cls.int().cpu().tolist()

            # boxes.id 가 None 이면 임시 ID 부여 (추적 없이 탐지만)
            if results[0].boxes.id is not None:
                track_ids = results[0].boxes.id.int().cpu().tolist()
            else:
                track_ids = [f'det_{i}' for i in range(len(boxes))]

            for track_id, box, cls in zip(track_ids, boxes, classes):
                x1, y1, x2, y2 = map(int, box)
                detections.append({
                    'track_id': track_id,
                    'box': (x1, y1, x2, y2),
                    'foot_point': ((x1 + x2) // 2, y2),
                })

        person_count = len(detections)
        zone_counts = np.zeros(len(zones), dtype=np.int32)

        # 히트맵
        if 'heatmap' in analysis_types and len(zones) > 0:
            overlay = processed.copy()
            for det in detections:
                fp = det['foot_point']
                for idx, zone in enumerate(zones):
                    if cv2.pointPolygonTest(zone, fp, False) >= 0:
                        zone_counts[idx] += 1
                        break

            max_count = float(max(settings.congestion_threshold, 1))
            for idx, zone in enumerate(zones):
                if zone_counts[idx] <= 0:
                    continue
                normalized = min(1.0, zone_counts[idx] / max_count)
                color_bgr = cv2.applyColorMap(
                    np.array([[normalized * 255]], dtype=np.uint8),
                    cv2.COLORMAP_JET,
                )[0][0]
                cv2.fillPoly(overlay, [zone], tuple(int(c) for c in color_bgr))

            processed = cv2.addWeighted(overlay, 0.5, processed, 0.5, 0)

            for idx, zone in enumerate(zones):
                cv2.polylines(processed, [zone], True, (255, 255, 0), 1)
                m = cv2.moments(zone)
                if m['m00'] != 0:
                    cx = int(m['m10'] / m['m00'])
                    cy = int(m['m01'] / m['m00'])
                    cv2.putText(processed, str(zone_counts[idx]), (cx, cy),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        # 혼잡 경고
        is_congested = any(c >= settings.congestion_threshold for c in zone_counts)
        trigger_sound = False
        if is_congested:
            now = time.time()
            if int(now * 2) % 2 == 0:
                h, w = processed.shape[:2]
                cv2.rectangle(processed, (0, 0), (w, h), (0, 0, 255), 20)
            last_sound = self._last_sound_time.get(stream_id, 0.0)
            if now - last_sound >= settings.event_sound_interval_seconds:
                trigger_sound = True
                self._last_sound_time[stream_id] = now

        # 바운딩박스 + 모자이크
        for det in detections:
            x1, y1, x2, y2 = det['box']
            if 'mosaic' in analysis_types:
                _apply_mosaic(processed, x1, y1, x2, y2)
            cv2.rectangle(processed, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # 인원 수 표시
        if 'count' in analysis_types:
            cv2.putText(processed, f'People: {person_count}', (40, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)

        ok, buf = cv2.imencode(
            '.jpg', processed,
            [cv2.IMWRITE_JPEG_QUALITY, settings.frame_jpeg_quality],
        )
        return (buf.tobytes() if ok else None, person_count, trigger_sound, is_congested)


# ---------------------------------------------------------------------------
# streamlink Python API 기반 프레임 읽기
# ---------------------------------------------------------------------------

def _streamlink_reader_thread(
    youtube_url: str,
    quality: str,
    width: int,
    height: int,
    needs_scale: bool,
    target_w: int,
    target_h: int,
    frame_queue: queue.Queue,
) -> None:
    """streamlink Python API로 스트림을 열고 FFmpeg으로 디코딩해 큐에 넣습니다."""
    try:
        from streamlink import Streamlink
        session = Streamlink()
        streams = session.streams(youtube_url)

        # 품질 선택: 360p → 480p → best 순으로 fallback
        quality_order = [quality, '480p', '360p', 'best']
        stream = None
        for q in quality_order:
            if q in streams:
                stream = streams[q]
                print(f'[streamlink] Opening stream: {q}')
                break
        if stream is None:
            print(f'[streamlink] No suitable stream found. Available: {list(streams.keys())}')
            return

        fd = stream.open()

        ffmpeg_output_args: list[str] = []
        if needs_scale:
            ffmpeg_output_args += ['-vf', f'scale={target_w}:{target_h}']
        ffmpeg_output_args += ['-f', 'image2pipe', '-pix_fmt', 'bgr24', '-vcodec', 'rawvideo', '-']

        ffmpeg_cmd = ['ffmpeg', '-i', 'pipe:0', '-loglevel', 'error'] + ffmpeg_output_args
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        # streamlink fd → FFmpeg stdin 을 별도 스레드로 복사
        def _copy_to_ffmpeg():
            try:
                while True:
                    chunk = fd.read(65536)
                    if not chunk:
                        break
                    proc.stdin.write(chunk)
            except Exception:
                pass
            finally:
                try:
                    proc.stdin.close()
                    fd.close()
                except Exception:
                    pass

        copy_thread = threading.Thread(target=_copy_to_ffmpeg, daemon=True)
        copy_thread.start()

        frame_size = width * height * 3
        while True:
            buf = b''
            while len(buf) < frame_size:
                chunk = proc.stdout.read(frame_size - len(buf))
                if not chunk:
                    err = b''
                    try:
                        err = proc.stderr.read(2000)
                    except Exception:
                        pass
                    if err:
                        print(f'[FFmpeg] {err.decode(errors="ignore").strip()}')
                    return
                buf += chunk
            if len(buf) == frame_size:
                frame_queue.put(buf)

    except Exception as e:
        import traceback
        print(f'[streamlink thread error] {e}')
        traceback.print_exc()
    finally:
        frame_queue.put(None)


def _cv2_reader_thread(
    source_path: str,
    width: int,
    height: int,
    frame_queue: queue.Queue,
) -> None:
    """local/http/rtsp 소스를 OpenCV로 읽어 큐에 넣습니다."""
    cap = cv2.VideoCapture(source_path)
    if not cap.isOpened():
        print(f'[cv2 reader] Cannot open: {source_path}')
        frame_queue.put(None)
        return
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height))
            # BGR raw bytes
            frame_queue.put(frame.tobytes())
    except Exception as e:
        print(f'[cv2 reader error] {e}')
    finally:
        cap.release()
        frame_queue.put(None)


# ---------------------------------------------------------------------------
# FFmpeg 기반 스트리밍 제너레이터
# ---------------------------------------------------------------------------

async def stream_frames(
    stream_id: str,
    analysis_config: dict[str, list[str]],
    model: YOLO,
    registry: StreamRegistry,
    event_store: EventStore,
) -> AsyncGenerator[bytes | str, None]:
    """streamlink(YouTube) 또는 OpenCV(기타)로 프레임을 읽고 YOLO 처리 후 JPEG를 yield합니다.
    
    혼잡 감지 시 앞뒤 2초 프레임을 mp4로 저장합니다.
    """
    details = registry.get_stream_details(stream_id)

    target_w = settings.stream_target_width
    target_h = settings.stream_target_height
    needs_scale = details.width > target_w or details.height > target_h
    width  = target_w if needs_scale else details.width
    height = target_h if needs_scale else details.height

    stream_type = settings.stream_sources.get(stream_id, {}).get('type', '')
    original_path = settings.stream_sources.get(stream_id, {}).get('path', '')

    processor = FrameProcessor(model=model, registry=registry)
    frame_queue: queue.Queue = queue.Queue(maxsize=30)

    if stream_type == 'youtube':
        read_width, read_height = 640, 360
        print(f'[stream {stream_id}] Starting streamlink: {read_width}x{read_height}')
        reader_thread = threading.Thread(
            target=_streamlink_reader_thread,
            args=(original_path, '360p', read_width, read_height, False, read_width, read_height, frame_queue),
            daemon=True,
        )
    else:
        print(f'[stream {stream_id}] Starting OpenCV: {width}x{height}')
        reader_thread = threading.Thread(
            target=_cv2_reader_thread,
            args=(details.source_path, width, height, frame_queue),
            daemon=True,
        )
        read_width, read_height = width, height

    reader_thread.start()

    # FPS 측정
    fps_counter = 0
    fps_timer = time.time()
    measured_fps: float = 15.0  # 초기값

    # 앞뒤 2초 버퍼 설정 (FPS 40 기준 80프레임)
    PRE_SECONDS  = 2.0
    POST_SECONDS = 2.0
    PRE_FRAMES   = int(measured_fps * PRE_SECONDS) or 80

    pre_buffer: collections.deque = collections.deque(maxlen=PRE_FRAMES)
    recording_post: bool = False
    post_frames: list = []
    post_target: int = 0
    event_person_count: int = 0

    try:
        while True:
            buf = await asyncio.to_thread(frame_queue.get)
            if buf is None:
                break

            frame = np.frombuffer(buf, np.uint8).reshape((read_height, read_width, 3)).copy()
            analysis_types = analysis_config.get('types', [])

            jpeg_bytes, person_count, trigger_sound, is_congested = await asyncio.to_thread(
                processor.process, frame, analysis_types, stream_id
            )

            # FPS 측정 (5초마다 갱신)
            fps_counter += 1
            elapsed = time.time() - fps_timer
            if elapsed >= 5.0:
                measured_fps = fps_counter / elapsed
                print(f'[stream {stream_id}] FPS: {measured_fps:.1f}')
                # 버퍼 크기 갱신
                PRE_FRAMES = int(measured_fps * PRE_SECONDS)
                pre_buffer = collections.deque(pre_buffer, maxlen=PRE_FRAMES)
                fps_counter = 0
                fps_timer = time.time()

            # 원본 프레임을 pre_buffer에 추가
            pre_buffer.append(frame.copy())

            # post 수집 중이면 프레임 추가
            if recording_post:
                post_frames.append(frame.copy())
                if len(post_frames) >= post_target:
                    # pre + post 합쳐서 mp4 저장
                    all_frames = list(pre_buffer) + post_frames
                    await event_store.save_video(
                        stream_id, all_frames, measured_fps, event_person_count
                    )
                    recording_post = False
                    post_frames = []

            # 혼잡 감지 && 저장 간격 충족 && 현재 post 수집 중 아닐 때
            elif is_congested and event_store.should_save(stream_id):
                event_store.mark_saved(stream_id)
                recording_post = True
                post_frames = []
                post_target = int(measured_fps * POST_SECONDS) or 80
                event_person_count = person_count

            if jpeg_bytes:
                yield jpeg_bytes
            if trigger_sound:
                yield 'PLAY_SOUND'

    except asyncio.CancelledError:
        pass
