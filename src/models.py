from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class VideoRecord:
    author: str
    author_url: str
    video_id: str
    video_url: str
    title: str
    published_at: str
    audio_path: str = ""
    media_path: str = ""
    transcript: str = ""
    status: str = "pending"
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoRecord":
        fields = {key: value for key, value in data.items() if key in cls.__dataclass_fields__}
        return cls(**fields)


@dataclass
class RunOptions:
    output_dir: Path
    model: str = "small"
    language: Optional[str] = "zh"
    workers: int = 1
    cookies_file: Optional[Path] = None
    cookies_from_browser: Optional[str] = None
    use_gpu: bool = False
    keep_audio: bool = True
    cleanup_source_videos: bool = True
