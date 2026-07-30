from pathlib import Path
from typing import Callable, Optional


Log = Callable[[str], None]


class Transcriber:
    def __init__(self, model_name: str, language: Optional[str], use_gpu: bool, log: Log):
        from faster_whisper import WhisperModel
        from opencc import OpenCC

        self.language = language or None
        self.converter = OpenCC("t2s") if self.language == "zh" else None
        device = "cuda" if use_gpu else "cpu"
        compute_type = "float16" if use_gpu else "int8"
        try:
            self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
        except Exception as exc:
            if not use_gpu:
                raise
            log(f"GPU 初始化失败，已回退至 CPU：{exc}")
            self.model = WhisperModel(model_name, device="cpu", compute_type="int8")

    def transcribe(self, audio_path: Path) -> str:
        segments, _info = self.model.transcribe(
            str(audio_path), language=self.language, vad_filter=True, beam_size=5
        )
        text = "".join(segment.text.strip() for segment in segments).strip()
        if not text:
            raise RuntimeError("未识别到可用口播内容。")
        return self.converter.convert(text) if self.converter else text
