from pydantic import BaseModel


class VideoProcessResponse(BaseModel):
    message: str
    analysis_type: str
    processed_video_url: str


class EventItem(BaseModel):
    id: str
    status: str
    timestamp: str
    video_url: str
    thumbnail_url: str


class CleanupResponse(BaseModel):
    deleted: int
