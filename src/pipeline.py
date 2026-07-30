import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, List

from .douk_backend import collect_profile_videos, extract_audio
from .exporter import export_excel
from .models import RunOptions, VideoRecord
from .state import StateStore
from .transcriber import Transcriber


Log = Callable[[str], None]


def parse_urls(text: str) -> List[str]:
    urls = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return list(dict.fromkeys(urls))


def check_requirements() -> List[str]:
    missing = []
    if shutil.which("ffmpeg") is None:
        missing.append("未找到 ffmpeg：请安装后重试（macOS 可执行 brew install ffmpeg）。")
    return missing


class SubtitlePipeline:
    def __init__(self, options: RunOptions, log: Log):
        self.options = options
        self.log = log
        self.options.output_dir.mkdir(parents=True, exist_ok=True)
        self.state = StateStore(self.options.output_dir / "任务状态.json")
        self.errors = []

    def _error(self, record: VideoRecord, stage: str, exc: Exception) -> None:
        record.status = "failed"
        record.error = f"{stage}：{exc}"
        self.state.put(record)
        self.errors.append({"video_id": record.video_id, "title": record.title, "stage": stage, "error": str(exc)})
        self.log(f"失败 [{stage}] {record.title}：{exc}")

    def _write_report(self, excel_paths: List[Path]) -> None:
        records = list(self.state.values())
        report = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "excel": [str(path) for path in excel_paths],
            "summary": {
                "done": sum(record.status == "done" for record in records),
                "failed": sum(record.status == "failed" for record in records),
                "pending": sum(record.status not in {"done", "failed"} for record in records),
            },
            "errors": self.errors,
        }
        (self.options.output_dir / "运行报告.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _cleanup_source_videos(self, records: Iterable[VideoRecord]) -> None:
        """删除已成功转写的原视频，保留失败项以便后续重试。"""
        download_root = (self.options.output_dir / "douk_downloads").resolve()
        removed = 0
        for record in records:
            if record.status != "done" or not record.media_path:
                continue
            media_path = Path(record.media_path)
            try:
                resolved_path = media_path.resolve()
                if not resolved_path.is_relative_to(download_root) or not resolved_path.is_file():
                    continue
                resolved_path.unlink()
                removed += 1
            except OSError as exc:
                self.log(f"未能清理原视频：{media_path.name}（{exc}）")
        if removed:
            for directory in sorted(download_root.rglob("*"), reverse=True):
                if directory.is_dir():
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
            self.log(f"已清理 {removed} 个已完成任务的原视频。")

    def run(self, profile_urls: Iterable[str]) -> Path:
        problems = check_requirements()
        if problems:
            raise RuntimeError("\n".join(problems))
        urls = list(profile_urls)
        if not urls:
            raise ValueError("请至少输入一个作者主页链接。")

        discovered = []
        self.log("阶段 1/4：通过 DouK-Downloader 采集作者主页作品")
        try:
            discovered = collect_profile_videos(urls, self.options, self.log)
            for incoming in discovered:
                previous = self.state.get(incoming.video_id)
                if previous:
                    previous.author = incoming.author
                    previous.author_url = incoming.author_url
                    previous.title = incoming.title
                    previous.published_at = incoming.published_at
                    previous.video_url = incoming.video_url
                    previous.media_path = incoming.media_path
                    record = previous
                else:
                    record = incoming
                self.state.put(record)
        except Exception as exc:
            self.errors.append({"stage": "主页采集", "error": str(exc)})
            self.log(f"主页采集失败：{exc}")

        unique = {record.video_id: record for record in discovered}
        records = list(unique.values())
        self.log(f"待处理视频：{len(records)} 条。")
        self.log("阶段 2/4：批量下载全部视频音频")
        for number, record in enumerate(records, 1):
            if record.status == "done" and record.transcript:
                self.log(f"[{number}/{len(records)}] 已完成，跳过下载：{record.title}")
                continue
            try:
                audio_path = Path(record.audio_path) if record.audio_path else None
                if not audio_path or not audio_path.exists():
                    self.log(f"[{number}/{len(records)}] 下载：{record.title}")
                    audio_path = extract_audio(record, self.options, self.log)
                    record.audio_path = str(audio_path)
                record.status = "audio_downloaded"
                record.error = ""
                self.state.put(record)
            except Exception as exc:
                self._error(record, "下载音频", exc)

        self.log("阶段 3/4：从已下载音频中提取口播字幕")
        transcriber = None
        transcribe_records = [
            record for record in records
            if record.status != "done" and record.audio_path and Path(record.audio_path).exists()
        ]
        for number, record in enumerate(transcribe_records, 1):
            audio_path = Path(record.audio_path)
            try:
                self.log(f"[{number}/{len(transcribe_records)}] 转写：{record.title}")
                if transcriber is None:
                    self.log(f"正在加载 Whisper {self.options.model} 模型（首次使用可能需要下载）…")
                    transcriber = Transcriber(
                        self.options.model, self.options.language, self.options.use_gpu, self.log
                    )
                record.transcript = transcriber.transcribe(audio_path)
                record.status = "done"
                record.error = ""
                self.state.put(record)
                if not self.options.keep_audio and audio_path.exists():
                    audio_path.unlink()
                    record.audio_path = ""
                    self.state.put(record)
            except Exception as exc:
                self._error(record, "转写", exc)

        self.log("阶段 4/4：生成 Excel")
        excel_paths = export_excel(self.state.values(), self.options.output_dir / "excel")
        if self.options.cleanup_source_videos:
            self._cleanup_source_videos(records)
        self._write_report(excel_paths)
        self.log("完成：" + "；".join(str(path) for path in excel_paths))
        return excel_paths[0] if len(excel_paths) == 1 else self.options.output_dir / "excel"
