import json
import threading
from pathlib import Path
from typing import Dict, Iterable

from .models import VideoRecord


class StateStore:
    """在中断后保留每个视频的状态，避免重复下载和转写。"""

    def __init__(self, path: Path):
        self.path = path
        self.records: Dict[str, VideoRecord] = {}
        self.lock = threading.RLock()
        self.load()

    def load(self) -> None:
        with self.lock:
            if not self.path.exists():
                return
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.records = {item["video_id"]: VideoRecord.from_dict(item) for item in raw}
            except (json.JSONDecodeError, OSError, KeyError, TypeError):
                self.records = {}

    def values(self) -> Iterable[VideoRecord]:
        with self.lock:
            return list(self.records.values())

    def get(self, video_id: str) -> VideoRecord:
        with self.lock:
            return self.records.get(video_id)

    def put(self, record: VideoRecord) -> None:
        with self.lock:
            self.records[record.video_id] = record
            self.save()

    def save(self) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = [record.to_dict() for record in self.records.values()]
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
