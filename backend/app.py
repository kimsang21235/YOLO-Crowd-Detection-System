from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from video_monitor.config import settings
from video_monitor.routes import router, event_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 권장 방식의 lifespan 이벤트 핸들러."""
    import asyncio
    worker_task = asyncio.create_task(event_store.worker())
    yield
    worker_task.cancel()


app = FastAPI(
    title='Video Crowd Monitoring API',
    version='1.0.0',
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(router)


@app.get('/health')
def health_check() -> dict:
    return {
        'status': 'ok',
        'model_path': str(settings.model_path),
        'streams': list(settings.stream_sources.keys()),
    }
