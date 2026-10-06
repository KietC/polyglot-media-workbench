# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
# REVIEW SNAPSHOT: redacted task data; see source provenance and audit.
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any


ASR_ROOT = Path(os.environ.get("WORKBENCH_MODEL_ROOT", "models")).resolve()
ASR_SITE_PACKAGES = Path(sys.prefix) / "Lib" / "site-packages"
WHISPER_MODEL = ASR_ROOT / "whisper-turbo"
QWEN_MODEL = ASR_ROOT / "qwen-asr"
QWEN_SCRIPT = Path(__file__).with_name("qwen_worker.py")
DIAR_ROOT = ASR_ROOT / "speaker-cache"
DIAR_REPO = Path(__file__).resolve().parents[2] / "vendor" / "3d-speaker"
DIAR_SCRIPT = DIAR_REPO / "speakerlab" / "bin" / "infer_diarization.py"
DIAR_MODEL_CACHE = DIAR_ROOT


# Reference helper: configure runtime; see recipe prerequisites.
# 参考辅助函数：configure runtime；执行前查看参考脚本依赖。
def configure_runtime() -> None:
    site_text = str(ASR_SITE_PACKAGES)
    if site_text not in sys.path:
        sys.path.insert(0, site_text)
    dll_dirs = [
        ASR_SITE_PACKAGES / "nvidia" / "cublas" / "bin",
        ASR_SITE_PACKAGES / "nvidia" / "cudnn" / "bin",
        ASR_SITE_PACKAGES / "torch" / "lib",
        ASR_SITE_PACKAGES / "ctranslate2",
    ]
    existing = [str(path) for path in dll_dirs if path.is_dir()]
    if existing:
        os.environ["PATH"] = os.pathsep.join(existing + [os.environ.get("PATH", "")])
        if hasattr(os, "add_dll_directory"):
            for item in existing:
                try:
                    os.add_dll_directory(item)
                except OSError:
                    pass
    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = site_text + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    os.environ.update(
        {
            "PYTHONUTF8": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "HF_HOME": str(ASR_ROOT / "hf_home"),
            "MEDIA_WORKBENCH_SPEAKER_CACHE": str(DIAR_MODEL_CACHE),
            "MODELSCOPE_CACHE": str(DIAR_MODEL_CACHE),
        }
    )


configure_runtime()


# Reference helper: now; see recipe prerequisites.
# 参考辅助函数：now；执行前查看参考脚本依赖。
def now() -> str:
    return datetime.now().astimezone().isoformat()


# Reference helper: atomic text; see recipe prerequisites.
# 参考辅助函数：atomic text；执行前查看参考脚本依赖。
def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


# Reference helper: atomic json; see recipe prerequisites.
# 参考辅助函数：atomic json；执行前查看参考脚本依赖。
def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


# Reference helper: read json; see recipe prerequisites.
# 参考辅助函数：read json；执行前查看参考脚本依赖。
def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# Reference helper: valid json; see recipe prerequisites.
# 参考辅助函数：valid json；执行前查看参考脚本依赖。
def valid_json(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0 and read_json(path) is not None
    except Exception:
        return False


# Reference helper: sha256; see recipe prerequisites.
# 参考辅助函数：sha256；执行前查看参考脚本依赖。
def sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest().upper()


# Reference helper: hms; see recipe prerequisites.
# 参考辅助函数：hms；执行前查看参考脚本依赖。
def hms(seconds: float, milliseconds: bool = True) -> str:
    value = max(0.0, float(seconds))
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    secs = value % 60
    if milliseconds:
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    return f"{hours:02d}:{minutes:02d}:{int(secs):02d}"


# Reference helper: subtitle time; see recipe prerequisites.
# 参考辅助函数：subtitle time；执行前查看参考脚本依赖。
def subtitle_time(seconds: float, decimal: str = ",") -> str:
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours, remain = divmod(total_ms, 3_600_000)
    minutes, remain = divmod(remain, 60_000)
    secs, millis = divmod(remain, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{decimal}{millis:03d}"


# Reference helper: probe; see recipe prerequisites.
# 参考辅助函数：probe；执行前查看参考脚本依赖。
def probe(path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed ({proc.returncode}): {proc.stderr.strip()}")
    return json.loads(proc.stdout)


class Pipeline:
    # Reference helper: init; see recipe prerequisites.
    # 参考辅助函数：init；执行前查看参考脚本依赖。
    def __init__(self, source: Path, root: Path) -> None:
        self.source = source.resolve()
        self.root = root.resolve()
        self.preflight_dir = self.root / "01_媒体预检"
        self.whisper_dir = self.root / "02_whisper时间轴"
        self.qwen_dir = self.root / "03_qwen3高精度"
        self.diar_dir = self.root / "04_说话人分离"
        self.final_dir = self.root / "05_最终交付"
        self.state_dir = self.root / "state"
        self.logs_dir = self.root / "logs"
        self.stem = self.source.stem
        self.started_at = now()
        for directory in (
            self.preflight_dir,
            self.whisper_dir,
            self.qwen_dir,
            self.diar_dir,
            self.final_dir,
            self.state_dir,
            self.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    # Reference helper: progress; see recipe prerequisites.
    # 参考辅助函数：progress；执行前查看参考脚本依赖。
    def progress(self, stage: str, status: str, message: str, **extra: Any) -> None:
        payload = {
            "task_id": "reference_asr",
            "stage": stage,
            "status": status,
            "message": message,
            "source": str(self.source),
            "output_root": str(self.root),
            "updated_at": now(),
            **extra,
        }
        atomic_json(self.state_dir / "pipeline_progress.json", payload)
        print(f"[{payload['updated_at']}] {stage} {status}: {message}", flush=True)

    # Reference helper: preflight; see recipe prerequisites.
    # 参考辅助函数：preflight；执行前查看参考脚本依赖。
    def preflight(self) -> dict[str, Any]:
        self.progress("media_preflight", "running", "核验原音频、模型、GPU 与解码能力")
        if not self.source.is_file():
            raise FileNotFoundError(self.source)
        required = [
            WHISPER_MODEL / "model.bin",
            QWEN_MODEL / "model-00001-of-00002.safetensors",
            QWEN_MODEL / "model-00002-of-00002.safetensors",
            QWEN_SCRIPT,
            DIAR_SCRIPT,
            DIAR_MODEL_CACHE,
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise RuntimeError("D 盘 ASR 运行时缺件: " + "; ".join(missing))
        media = probe(self.source)
        audio_streams = [item for item in media.get("streams", []) if item.get("codec_type") == "audio"]
        if len(audio_streams) != 1:
            raise RuntimeError(f"预期 1 条音轨，实际 {len(audio_streams)}")
        audio = audio_streams[0]
        duration = float(media.get("format", {}).get("duration") or audio.get("duration") or 0)
        if duration <= 0:
            raise RuntimeError("无法取得有效音频时长")
        gpu = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        manifest = {
            "task_id": "reference_asr",
            "created_at": now(),
            "privacy": "local_only_no_upload",
            "source_modified": False,
            "source": {
                "path": str(self.source),
                "size_bytes": self.source.stat().st_size,
                "sha256": sha256(self.source),
                "last_write_time": datetime.fromtimestamp(self.source.stat().st_mtime).astimezone().isoformat(),
            },
            "media": {
                "duration_seconds": duration,
                "duration_hms": hms(duration),
                "container": media.get("format", {}).get("format_name"),
                "codec": audio.get("codec_name"),
                "codec_long_name": audio.get("codec_long_name"),
                "sample_rate": int(audio.get("sample_rate") or 0),
                "channels": int(audio.get("channels") or 0),
                "channel_layout": audio.get("channel_layout"),
                "bit_rate": int(audio.get("bit_rate") or media.get("format", {}).get("bit_rate") or 0),
            },
            "runtime": {
                "python": sys.executable,
                "python_version": sys.version,
                "asr_site_packages": str(ASR_SITE_PACKAGES),
                "whisper_model": str(WHISPER_MODEL),
                "qwen3_asr_model": str(QWEN_MODEL),
                "diarization_engine": str(DIAR_SCRIPT),
                "gpu": gpu.stdout.strip() if gpu.returncode == 0 else None,
                "gpu_probe_error": gpu.stderr.strip() if gpu.returncode != 0 else None,
            },
            "raw_ffprobe": media,
        }
        atomic_json(self.preflight_dir / "media_manifest.json", manifest)
        report = (
            "# 媒体预检\n\n"
            f"- 原文件：`{self.source}`\n"
            f"- SHA-256：`{manifest['source']['sha256']}`\n"
            f"- 大小：{manifest['source']['size_bytes']:,} bytes\n"
            f"- 时长：{manifest['media']['duration_hms']}\n"
            f"- 编码：{manifest['media']['codec_long_name']}\n"
            f"- 采样率 / 声道：{manifest['media']['sample_rate']} Hz / {manifest['media']['channels']}\n"
            f"- GPU：{manifest['runtime']['gpu']}\n"
            "- 处理边界：全程本机离线，原音频不修改、不上传。\n"
        )
        atomic_text(self.preflight_dir / "media_preflight_report.md", report)
        self.progress("media_preflight", "done", "预检通过", duration_seconds=duration)
        return manifest

    # Reference helper: whisper paths; see recipe prerequisites.
    # 参考辅助函数：whisper paths；执行前查看参考脚本依赖。
    def whisper_paths(self) -> dict[str, Path]:
        base = self.whisper_dir / self.stem
        return {ext: base.with_suffix(ext) for ext in (".json", ".txt", ".srt", ".vtt")}

    # Reference helper: whisper done; see recipe prerequisites.
    # 参考辅助函数：whisper done；执行前查看参考脚本依赖。
    def whisper_done(self) -> bool:
        paths = self.whisper_paths()
        return all(path.is_file() and path.stat().st_size > 0 for path in paths.values()) and valid_json(paths[".json"])

    # Reference helper: run whisper; see recipe prerequisites.
    # 参考辅助函数：run whisper；执行前查看参考脚本依赖。
    def run_whisper(self, duration: float) -> dict[str, Any]:
        paths = self.whisper_paths()
        if self.whisper_done():
            self.progress("whisper_timeline", "skipped_valid", "已有完整 Whisper 时间轴，继续复用")
            return read_json(paths[".json"])
        self.progress("whisper_timeline", "running", "加载 faster-whisper large-v3-turbo")
        from faster_whisper import BatchedInferencePipeline, WhisperModel

        load_started = time.perf_counter()
        model = WhisperModel(str(WHISPER_MODEL), device="cuda", compute_type="float16")
        batched = BatchedInferencePipeline(model=model)
        load_seconds = time.perf_counter() - load_started
        self.progress("whisper_timeline", "running", "模型已加载，开始带词级时间戳转写", load_seconds=load_seconds)
        infer_started = time.perf_counter()
        segment_iter, info = batched.transcribe(
            str(self.source),
            language=None,
            task="transcribe",
            beam_size=5,
            condition_on_previous_text=False,
            initial_prompt=None,
            word_timestamps=True,
            without_timestamps=False,
            vad_filter=True,
            batch_size=16,
            repetition_penalty=1.05,
            no_repeat_ngram_size=3,
        )
        segments: list[dict[str, Any]] = []
        for index, segment in enumerate(segment_iter, start=1):
            words = []
            for word in segment.words or []:
                words.append(
                    {
                        "start": word.start,
                        "end": word.end,
                        "word": word.word,
                        "probability": word.probability,
                    }
                )
            segments.append(
                {
                    "id": int(segment.id),
                    "start": float(segment.start),
                    "end": float(segment.end),
                    "text": segment.text.strip(),
                    "avg_logprob": float(segment.avg_logprob),
                    "compression_ratio": float(segment.compression_ratio),
                    "no_speech_prob": float(segment.no_speech_prob),
                    "words": words,
                }
            )
            if index == 1 or index % 10 == 0:
                self.progress(
                    "whisper_timeline",
                    "running",
                    f"已生成 {index} 个时间轴片段",
                    segments_done=index,
                    audio_seconds_done=float(segment.end),
                    percent=round(min(100.0, float(segment.end) / duration * 100), 2),
                )
        infer_seconds = time.perf_counter() - infer_started
        if not segments:
            raise RuntimeError("Whisper 未生成任何片段")
        payload = {
            "source": str(self.source),
            "engine": "faster-whisper",
            "model": str(WHISPER_MODEL),
            "device": "cuda",
            "compute_type": "float16",
            "batch_size": 16,
            "beam_size": 5,
            "condition_on_previous_text": False,
            "vad_filter": True,
            "word_timestamps": True,
            "detected_language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "duration_after_vad": info.duration_after_vad,
            "load_seconds": load_seconds,
            "infer_seconds": infer_seconds,
            "segments": segments,
        }
        txt = "\n".join(item["text"] for item in segments if item["text"]).strip() + "\n"
        srt_parts = []
        vtt_parts = ["WEBVTT", ""]
        for index, item in enumerate(segments, start=1):
            srt_parts.extend(
                [
                    str(index),
                    f"{subtitle_time(item['start'])} --> {subtitle_time(item['end'])}",
                    item["text"],
                    "",
                ]
            )
            vtt_parts.extend(
                [
                    f"{subtitle_time(item['start'], '.')} --> {subtitle_time(item['end'], '.')}",
                    item["text"],
                    "",
                ]
            )
        atomic_json(paths[".json"], payload)
        atomic_text(paths[".txt"], txt)
        atomic_text(paths[".srt"], "\n".join(srt_parts))
        atomic_text(paths[".vtt"], "\n".join(vtt_parts))
        del batched
        del model
        gc.collect()
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception:
            pass
        self.progress(
            "whisper_timeline",
            "done",
            f"Whisper 完成，共 {len(segments)} 段",
            segments=len(segments),
            infer_seconds=infer_seconds,
        )
        return payload

    # Reference helper: qwen paths; see recipe prerequisites.
    # 参考辅助函数：qwen paths；执行前查看参考脚本依赖。
    def qwen_paths(self) -> dict[str, Path]:
        base = self.qwen_dir / self.stem
        return {ext: base.with_suffix(ext) for ext in (".json", ".txt")}

    # Reference helper: qwen done; see recipe prerequisites.
    # 参考辅助函数：qwen done；执行前查看参考脚本依赖。
    def qwen_done(self) -> bool:
        paths = self.qwen_paths()
        return all(path.is_file() and path.stat().st_size > 0 for path in paths.values()) and valid_json(paths[".json"])

    # Reference helper: run logged; see recipe prerequisites.
    # 参考辅助函数：run logged；执行前查看参考脚本依赖。
    def run_logged(self, command: list[str], log_path: Path, cwd: Path | None = None) -> None:
        started = time.perf_counter()
        proc = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        log = (
            f"started_at={now()}\ncommand_parts:\n"
            + "\n".join(command)
            + f"\n\nstdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}\n"
            + f"returncode={proc.returncode}\nelapsed_seconds={time.perf_counter() - started:.3f}\n"
        )
        atomic_text(log_path, log)
        if proc.returncode != 0:
            raise RuntimeError(f"命令失败 ({proc.returncode})，见 {log_path}")

    # Reference helper: run qwen; see recipe prerequisites.
    # 参考辅助函数：run qwen；执行前查看参考脚本依赖。
    def run_qwen(self) -> dict[str, Any]:
        paths = self.qwen_paths()
        if self.qwen_done():
            self.progress("qwen3_high_accuracy", "skipped_valid", "已有完整 Qwen3-ASR 稿，继续复用")
            return read_json(paths[".json"])
        self.progress("qwen3_high_accuracy", "running", "运行本地 Qwen3-ASR 1.7B，120 秒分块")
        command = [
            sys.executable,
            str(QWEN_SCRIPT),
            str(self.source),
            "--model",
            str(QWEN_MODEL),
            "--language",
            "Cantonese",
            "--out-dir",
            str(self.qwen_dir),
            "--batch-size",
            "32",
            "--chunk-seconds",
            "120",
            "--chunk-batch-size",
            "4",
            "--max-new-tokens",
            "1024",
            "--progress-file",
            str(self.state_dir / "qwen3_progress.json"),
        ]
        self.run_logged(command, self.logs_dir / "qwen3_asr.log")
        if not self.qwen_done():
            raise RuntimeError("Qwen3-ASR 命令返回成功，但预期输出缺失")
        payload = read_json(paths[".json"])
        self.progress(
            "qwen3_high_accuracy",
            "done",
            f"Qwen3-ASR 完成，共 {len(payload.get('results', []))} 个分块",
            chunks=len(payload.get("results", [])),
            infer_seconds=payload.get("infer_seconds"),
        )
        return payload

    # Reference helper: diar json path; see recipe prerequisites.
    # 参考辅助函数：diar json path；执行前查看参考脚本依赖。
    def diar_json_path(self) -> Path:
        return self.diar_dir / "result" / f"{self.stem}_16k_mono.json"

    # Reference helper: run diarization; see recipe prerequisites.
    # 参考辅助函数：run diarization；执行前查看参考脚本依赖。
    def run_diarization(self) -> list[dict[str, Any]]:
        wav = self.diar_dir / "work" / f"{self.stem}_16k_mono.wav"
        result_dir = self.diar_dir / "result"
        result_dir.mkdir(parents=True, exist_ok=True)
        result_json = self.diar_json_path()
        if valid_json(result_json):
            self.progress("speaker_diarization", "skipped_valid", "已有完整说话人分离结果，继续复用")
        else:
            wav.parent.mkdir(parents=True, exist_ok=True)
            if not wav.is_file() or wav.stat().st_size == 0:
                self.progress("speaker_diarization", "running", "转为 16 kHz 单声道 PCM")
                self.run_logged(
                    [
                        "ffmpeg",
                        "-y",
                        "-v",
                        "error",
                        "-i",
                        str(self.source),
                        "-vn",
                        "-ac",
                        "1",
                        "-ar",
                        "16000",
                        "-c:a",
                        "pcm_s16le",
                        str(wav),
                    ],
                    self.logs_dir / "ffmpeg_16k_mono.log",
                )
            self.progress("speaker_diarization", "running", "运行本地 3D-Speaker/CAMPPlus 自动声纹聚类")
            self.run_logged(
                [
                    sys.executable,
                    str(DIAR_SCRIPT),
                    "--wav",
                    str(wav),
                    "--out_dir",
                    str(result_dir),
                    "--out_type",
                    "json",
                ],
                self.logs_dir / "3dspeaker_diarization.log",
                cwd=DIAR_REPO,
            )
        if not valid_json(result_json):
            raise RuntimeError(f"说话人分离输出无效: {result_json}")
        raw = read_json(result_json)
        items = list(raw.values()) if isinstance(raw, dict) else list(raw)
        normalized = [
            {
                "start": float(item["start"]),
                "end": float(item.get("stop", item.get("end"))),
                "speaker": f"SPEAKER_{int(item['speaker']):02d}",
            }
            for item in items
        ]
        normalized.sort(key=lambda item: (item["start"], item["end"]))
        speakers = sorted({item["speaker"] for item in normalized})
        manifest = {
            "engine": "local 3D-Speaker/CAMPPlus",
            "speaker_count_mode": "automatic",
            "speaker_count": len(speakers),
            "speakers": speakers,
            "segments": len(normalized),
            "voice_seconds": round(sum(max(0.0, item["end"] - item["start"]) for item in normalized), 3),
            "source_result": str(result_json),
            "external_upload": False,
        }
        atomic_json(self.diar_dir / "diarization_manifest.json", manifest)
        self.progress(
            "speaker_diarization",
            "done",
            f"说话人分离完成，自动识别 {len(speakers)} 个声纹簇",
            speaker_count=len(speakers),
            diarization_segments=len(normalized),
        )
        return normalized

    @staticmethod
    # Reference helper: speaker for; see recipe prerequisites.
    # 参考辅助函数：speaker for；执行前查看参考脚本依赖。
    def speaker_for(start: float, end: float, diar: list[dict[str, Any]]) -> str:
        best_speaker = "SPEAKER_UNKNOWN"
        best_overlap = 0.0
        for item in diar:
            if item["start"] >= end:
                break
            if item["end"] <= start:
                continue
            overlap = min(end, item["end"]) - max(start, item["start"])
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = item["speaker"]
        return best_speaker

    # Reference helper: build delivery; see recipe prerequisites.
    # 参考辅助函数：build delivery；执行前查看参考脚本依赖。
    def build_delivery(
        self,
        media_manifest: dict[str, Any],
        whisper: dict[str, Any],
        qwen: dict[str, Any],
        diar: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.progress("delivery", "running", "对齐声纹、生成双 ASR 对照稿和最终交付")
        whisper_segments = whisper["segments"]
        qwen_chunks = qwen.get("results", [])

        speaker_lines = [
            "# 本地录音｜说话人时间轴稿",
            "",
            "> 文字来自 faster-whisper；说话人编号来自自动声纹聚类，不代表真实身份。",
            "",
        ]
        speaker_payload = []
        for item in whisper_segments:
            speaker = self.speaker_for(float(item["start"]), float(item["end"]), diar)
            speaker_payload.append({**item, "speaker": speaker})
            speaker_lines.append(f"[{hms(item['start'])} - {hms(item['end'])}] **{speaker}**：{item['text']}")
            speaker_lines.append("")
        speaker_json = self.final_dir / f"{self.stem}_说话人时间轴稿.json"
        speaker_md = self.final_dir / f"{self.stem}_说话人时间轴稿.md"
        atomic_json(speaker_json, {"source": str(self.source), "segments": speaker_payload})
        atomic_text(speaker_md, "\n".join(speaker_lines).rstrip() + "\n")

        qwen_lines = [
            "# 本地录音｜Qwen3-ASR 高精度逐字稿",
            "",
            "> 由 D 盘本地 Qwen3-ASR-1.7B 生成；每段为约 120 秒音频块，尚未经过人工听校。",
            "",
        ]
        qwen_plain = []
        for index, chunk in enumerate(qwen_chunks, start=1):
            start = float(chunk.get("start") or 0)
            end = float(chunk.get("end") or start)
            text = str(chunk.get("text") or "").strip()
            qwen_lines.extend([f"## {index:02d}｜{hms(start)} - {hms(end)}", "", text, ""])
            if text:
                qwen_plain.append(text)
        qwen_final_md = self.final_dir / f"{self.stem}_Qwen3高精度逐字稿.md"
        qwen_final_txt = self.final_dir / f"{self.stem}_Qwen3高精度逐字稿.txt"
        atomic_text(qwen_final_md, "\n".join(qwen_lines).rstrip() + "\n")
        atomic_text(qwen_final_txt, "\n".join(qwen_plain).rstrip() + "\n")

        compare_lines = [
            "# 本地录音｜双 ASR 对照审校稿",
            "",
            "> Qwen3-ASR 提供 120 秒块级高精度文本；Whisper 提供细时间轴。两路差异保留，未把自动推断冒充人工定稿。",
            "",
        ]
        for index, chunk in enumerate(qwen_chunks, start=1):
            start = float(chunk.get("start") or 0)
            end = float(chunk.get("end") or start)
            relevant = [item for item in speaker_payload if float(item["end"]) > start and float(item["start"]) < end]
            compare_lines.extend(
                [
                    f"## {index:02d}｜{hms(start)} - {hms(end)}",
                    "",
                    "### Qwen3-ASR",
                    "",
                    str(chunk.get("text") or "").strip() or "（空）",
                    "",
                    "### Whisper + 自动声纹",
                    "",
                ]
            )
            if relevant:
                for item in relevant:
                    compare_lines.append(f"- [{hms(item['start'])}] {item['speaker']}：{item['text']}")
            else:
                compare_lines.append("- （该窗口没有 Whisper 语音片段）")
            compare_lines.append("")
        compare_md = self.final_dir / f"{self.stem}_双ASR对照审校稿.md"
        atomic_text(compare_md, "\n".join(compare_lines).rstrip() + "\n")

        duration = float(media_manifest["media"]["duration_seconds"])
        errors: list[str] = []
        warnings: list[str] = []
        if not whisper_segments:
            errors.append("Whisper segments empty")
        if not qwen_chunks:
            errors.append("Qwen3-ASR chunks empty")
        if not diar:
            errors.append("Diarization segments empty")
        expected_chunks = math.ceil(duration / 120.0)
        if len(qwen_chunks) != expected_chunks:
            errors.append(f"Qwen chunk count {len(qwen_chunks)} != expected {expected_chunks}")
        whisper_overlaps = 0
        for previous, current in zip(whisper_segments, whisper_segments[1:]):
            if float(current["start"]) < float(previous["end"]) - 0.02:
                whisper_overlaps += 1
        if whisper_overlaps:
            warnings.append(f"Whisper segment overlaps: {whisper_overlaps}")
        if whisper_segments and float(whisper_segments[-1]["end"]) > duration + 5:
            errors.append("Whisper timeline exceeds source duration by more than 5 seconds")
        qwen_empty = sum(1 for item in qwen_chunks if not str(item.get("text") or "").strip())
        if qwen_empty:
            warnings.append(f"Qwen empty chunks: {qwen_empty}")
        unknown_speaker = sum(1 for item in speaker_payload if item["speaker"] == "SPEAKER_UNKNOWN")
        if unknown_speaker:
            warnings.append(f"Whisper segments without diarization overlap: {unknown_speaker}")

        validation = {
            "validated_at": now(),
            "status": "pass" if not errors else "fail",
            "source_sha256": media_manifest["source"]["sha256"],
            "source_duration_seconds": duration,
            "whisper": {
                "segments": len(whisper_segments),
                "detected_language": whisper.get("detected_language"),
                "language_probability": whisper.get("language_probability"),
                "last_segment_end": whisper_segments[-1]["end"] if whisper_segments else None,
                "overlaps": whisper_overlaps,
            },
            "qwen3_asr": {
                "chunks": len(qwen_chunks),
                "expected_chunks": expected_chunks,
                "empty_chunks": qwen_empty,
                "language_hint": qwen.get("language_hint"),
            },
            "diarization": {
                "segments": len(diar),
                "speaker_count": len({item["speaker"] for item in diar}),
                "unknown_whisper_segments": unknown_speaker,
            },
            "errors": errors,
            "warnings": warnings,
            "human_review_status": "not_performed",
        }
        validation_json = self.final_dir / "ASR处理与校验报告.json"
        atomic_json(validation_json, validation)
        validation_md = self.final_dir / "ASR处理与校验报告.md"
        report_lines = [
            "# ASR 处理与校验报告",
            "",
            f"- 自动校验：**{validation['status'].upper()}**",
            f"- 原音频 SHA-256：`{validation['source_sha256']}`",
            f"- 原音频时长：{hms(duration)}",
            f"- Whisper：{len(whisper_segments)} 段；语言 {whisper.get('detected_language')}；概率 {whisper.get('language_probability')}",
            f"- Qwen3-ASR：{len(qwen_chunks)} / {expected_chunks} 块",
            f"- 自动声纹：{len({item['speaker'] for item in diar})} 簇；{len(diar)} 段",
            f"- 人工听校：未执行",
            "",
            "## 警告",
            "",
        ]
        report_lines.extend([f"- {item}" for item in warnings] or ["- 无"])
        report_lines.extend(["", "## 错误", ""])
        report_lines.extend([f"- {item}" for item in errors] or ["- 无"])
        atomic_text(validation_md, "\n".join(report_lines).rstrip() + "\n")

        manifest_entries = []
        stable_roots = [self.preflight_dir, self.whisper_dir, self.qwen_dir, self.diar_dir, self.final_dir]
        stable_files = (path for directory in stable_roots for path in directory.rglob("*"))
        for path in sorted(stable_files, key=lambda item: str(item).lower()):
            if not path.is_file() or path.suffix == ".tmp" or path.name == "delivery_manifest.json":
                continue
            manifest_entries.append(
                {
                    "relative_path": str(path.relative_to(self.root)),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
        delivery_manifest = {
            "task_id": "reference_asr",
            "generated_at": now(),
            "status": "complete" if validation["status"] == "pass" else "validation_failed",
            "source": str(self.source),
            "source_sha256": media_manifest["source"]["sha256"],
            "source_modified": False,
            "privacy": "local_only_no_upload",
            "human_review_status": "not_performed",
            "files": manifest_entries,
        }
        atomic_json(self.final_dir / "delivery_manifest.json", delivery_manifest)
        if errors:
            raise RuntimeError("自动交付校验失败: " + "; ".join(errors))
        self.progress(
            "delivery",
            "done",
            "双 ASR、声纹时间轴、对照稿和校验清单已生成",
            validation="pass",
            deliverable_files=len(manifest_entries),
        )
        return validation

    # Reference helper: run; see recipe prerequisites.
    # 参考辅助函数：run；执行前查看参考脚本依赖。
    def run(self) -> int:
        try:
            manifest = self.preflight()
            duration = float(manifest["media"]["duration_seconds"])
            whisper = self.run_whisper(duration)
            qwen = self.run_qwen()
            diar = self.run_diarization()
            validation = self.build_delivery(manifest, whisper, qwen, diar)
            final = {
                "task_id": "reference_asr",
                "status": "complete",
                "started_at": self.started_at,
                "finished_at": now(),
                "source": str(self.source),
                "output_root": str(self.root),
                "validation": validation["status"],
            }
            atomic_json(self.state_dir / "pipeline_result.json", final)
            self.progress("pipeline", "complete", "本地 ASR 标准流程完成", validation=validation["status"])
            return 0
        except Exception as exc:
            failure = {
                "task_id": "reference_asr",
                "status": "failed",
                "started_at": self.started_at,
                "failed_at": now(),
                "source": str(self.source),
                "output_root": str(self.root),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            atomic_json(self.state_dir / "pipeline_result.json", failure)
            self.progress("pipeline", "failed", str(exc), error_type=type(exc).__name__)
            print(failure["traceback"], file=sys.stderr, flush=True)
            return 1


# Reference helper: parse args; see recipe prerequisites.
# 参考辅助函数：parse args；执行前查看参考脚本依赖。
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="media_workbench 本地双 ASR + 自动声纹标准流程")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


# Reference helper: main; see recipe prerequisites.
# 参考辅助函数：main；执行前查看参考脚本依赖。
def main() -> int:
    args = parse_args()
    return Pipeline(args.input, args.output).run()


if __name__ == "__main__":
    raise SystemExit(main())
