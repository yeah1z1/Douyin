from pathlib import Path
from typing import Optional


class Transcriber:
    def __init__(
        self,
        model_name: str,
        language: Optional[str],
        beam_size: int,
        workers: int,
        cpu_threads: int,
    ):
        from faster_whisper import WhisperModel
        from opencc import OpenCC

        self.language = language or None
        self.converter = OpenCC("t2s") if self.language == "zh" else None
        self.beam_size = beam_size
        settings = {"device": "cpu", "compute_type": "int8", "num_workers": workers}
        if cpu_threads:
            settings["cpu_threads"] = cpu_threads
        self.model = WhisperModel(model_name, **settings)

    def transcribe(self, audio_path: Path) -> str:
        segments, _info = self.model.transcribe(
            str(audio_path), language=self.language, vad_filter=True, beam_size=self.beam_size
        )
        text = "".join(segment.text.strip() for segment in segments).strip()
        if not text:
            raise RuntimeError("未识别到可用口播内容。")
        return self.converter.convert(text) if self.converter else text
