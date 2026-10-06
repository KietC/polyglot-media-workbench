"""Dual ASR, speaker clustering and explicit editorial checkpoints.
双路识别、说话人聚类及明确的人工校对状态。
"""

from __future__ import annotations
from collections import Counter
from difflib import SequenceMatcher
import gc
import json
import math
import os
from pathlib import Path
import re
import sys

from .core import (
    cached,
    command,
    fingerprint,
    offline_environment,
    prepare_cuda_runtime,
    probe,
    read_json,
    save_json,
    sha256,
    timestamp,
)


def prepare(source, output, config):
    """Create a hashed analysis copy without changing the source or its first audio track.
    保存带哈希的分析副本，不修改原媒体；明确选择第一音轨。
    """
    source = Path(source).resolve()
    output = Path(output).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output == source or source.is_relative_to(output):
        raise ValueError("Keep source media outside the task output / 原媒体应位于任务输出目录之外")
    output.mkdir(parents=True, exist_ok=True)
    media = probe(source, config)
    audio_streams = [s for s in media["streams"] if s["codec_type"] == "audio"]
    if not audio_streams:
        raise ValueError("No audio stream / 未找到音轨")
    duration = float(media["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Invalid media duration / 媒体时长无效")
    original_hash = sha256(source)
    wav = output / "audio.wav"
    old = read_json(output / "source.json") if (output / "source.json").exists() else {}
    if old.get("source_sha256") != original_hash or not wav.exists() or old.get("wav_sha256") != sha256(wav):
        partial = output / "audio.partial.wav"
        command(
            [
                config["ffmpeg"],
                "-v",
                "error",
                "-nostdin",
                "-y",
                "-i",
                source,
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                partial,
            ],
            config["command_timeout"],
        )
        os.replace(partial, wav)
    result = dict(
        source=str(source),
        source_sha256=original_hash,
        wav=str(wav),
        wav_sha256=sha256(wav),
        duration=duration,
        audio_streams=len(audio_streams),
        selected_stream="0:a:0",
        source_modified=False,
    )
    save_json(output / "source.json", result)
    return result


def release_gpu(*models):
    # Callers delete their own references before this cache cleanup.
    # 调用者须先删除模型引用，再清理显存缓存。
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def whisper(media, config):
    """Transcribe local CTranslate2 weights; retain word timing and confidence signals.
    用本地CTranslate2权重转写，保留词级时间与置信信息。
    """
    if config["device"] != "cpu":
        prepare_cuda_runtime()
    from faster_whisper import BatchedInferencePipeline, WhisperModel

    model = WhisperModel(
        config["models"]["whisper"],
        device=config["device"],
        compute_type=config["whisper_compute_type"],
        cpu_threads=config["cpu_threads"],
        local_files_only=True,
    )
    pipeline = BatchedInferencePipeline(model=model)
    # Disable VAD by default for quiet speech; use explicit full-duration windows.
    # 默认关闭VAD，以完整时间窗口复核低声语音。
    clips = [
        {"start": s, "end": min(s + config["chunk_seconds"], media["duration"])}
        for s in range(0, math.ceil(media["duration"]), config["chunk_seconds"])
    ]
    kwargs = dict(
        language=None,
        multilingual=True,
        task="transcribe",
        beam_size=config["beam_size"],
        initial_prompt=None,
        condition_on_previous_text=False,
        word_timestamps=True,
        vad_filter=config["whisper_vad"],
        batch_size=config["batch_size"],
    )
    if not config["whisper_vad"]:
        kwargs["clip_timestamps"] = clips
    segments, info = pipeline.transcribe(media["wav"], **kwargs)
    rows = [
        dict(
            start=s.start,
            end=s.end,
            text=s.text.strip(),
            avg_logprob=s.avg_logprob,
            no_speech_prob=s.no_speech_prob,
            words=[dict(start=w.start, end=w.end, word=w.word, probability=w.probability) for w in s.words or []],
        )
        for s in segments
    ]
    del pipeline, model
    release_gpu()
    if not rows:
        raise RuntimeError("Whisper returned no segments; inspect silence before accepting / 无分段，请检查静音")
    return dict(engine="faster-whisper", language=info.language, segments=rows, task="transcribe", initial_prompt=None)


def qwen(media, config):
    """Recognize every window with automatic language and bounded OOM backoff.
    逐窗口自动判断语种，显存不足时有界缩小批次。
    """
    import soundfile as sf
    import torch
    from qwen_asr import Qwen3ASRModel

    gpu = config["device"] != "cpu"
    model = Qwen3ASRModel.from_pretrained(
        config["models"]["qwen"],
        dtype=torch.bfloat16 if gpu else torch.float32,
        device_map="cuda:0" if gpu else "cpu",
        max_inference_batch_size=config["batch_size"],
        max_new_tokens=512,
    )
    audio, sr = sf.read(media["wav"], dtype="float32")
    duration = len(audio) / sr
    chunks = [
        (s, min(s + config["chunk_seconds"], duration)) for s in range(0, math.ceil(duration), config["chunk_seconds"])
    ]
    rows = []
    batch_size = config["batch_size"]
    index = 0
    while index < len(chunks):
        batch = chunks[index : index + batch_size]
        try:
            results = model.transcribe(
                audio=[(audio[int(s * sr) : int(e * sr)], sr) for s, e in batch], language=[None] * len(batch)
            )
        except torch.cuda.OutOfMemoryError:
            if batch_size == 1:
                raise
            batch_size = max(1, batch_size // 2)
            release_gpu()
            continue
        # Never silently truncate a missing model response with zip().
        # 不允许zip()静默截断模型缺失的返回项。
        if len(results) != len(batch):
            raise RuntimeError("Qwen response count differs from input chunk count / 返回数量与输入块数不同")
        rows.extend(dict(start=s, end=e, text=r.text, language=r.language) for (s, e), r in zip(batch, results))
        index += len(batch)
    del model
    release_gpu()
    return dict(engine="Qwen3-ASR-1.7B", chunk_seconds=config["chunk_seconds"], language_hint=None, results=rows)


def diar(media, output, config):
    """Run vendored voice clustering after checking the explicit local model cache.
    检查显式本地模型缓存后运行附带的声音聚类引擎。
    """
    # Keep the optional upstream engine in an independent child process.
    # 可选上游说话人引擎在独立子进程中运行。
    vendor = Path(__file__).resolve().parents[2] / "vendor/3d-speaker"
    if not vendor.exists():
        vendor = Path(config.get("speaker_repo", "vendor/3d-speaker")).resolve()
    if not (vendor / "speakerlab/bin/infer_diarization.py").exists():
        raise FileNotFoundError("3D-Speaker source missing; set speaker_repo / 请配置说话人引擎目录")
    required = ["iic/speech_campplus_sv_zh_en_16k-common_advanced", "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"]
    if config["offline"]:
        missing = [
            name for name in required if not (Path(config["speaker_cache"]) / name / "configuration.json").exists()
        ]
        if missing:
            raise FileNotFoundError(f"Speaker cache missing; download explicitly first: {missing}")
    key = fingerprint(media["source_sha256"], "diar", config)
    folder = Path(output) / "speaker_raw" / key[:16]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(vendor) + os.pathsep + env.get("PYTHONPATH", "")
    env["MEDIA_WORKBENCH_SPEAKER_CACHE"] = config["speaker_cache"]
    command(
        [
            sys.executable,
            vendor / "speakerlab/bin/infer_diarization.py",
            "--wav",
            media["wav"],
            "--out_dir",
            folder,
            "--out_type",
            "json",
        ],
        config["command_timeout"],
        cwd=vendor,
        env=env,
    )
    raw = read_json(folder / (Path(media["wav"]).stem + ".json"))
    items = raw.values() if isinstance(raw, dict) else raw
    rows = sorted(
        [
            dict(
                start=float(r["start"]),
                end=float(r.get("stop", r.get("end"))),
                speaker=f"SPEAKER_{int(r['speaker']):02d}",
            )
            for r in items
        ],
        key=lambda r: (r["start"], r["end"]),
    )
    return dict(engine="3D-Speaker/CAMPPlus", segments=rows, identity_inference=False)


def speaker_for(start, end, segments):
    """Assign the voice group with the largest accumulated temporal overlap.
    按累计时间重叠最多的声音簇分组，不推断人物身份。
    """
    score = Counter()
    for r in segments:
        overlap = min(end, r["end"]) - max(start, r["start"])
        if overlap > 0:
            score[r["speaker"]] += overlap
    return score.most_common(1)[0][0] if score else "SPEAKER_UNKNOWN"


def fuse(output):
    """Keep both model texts and mark disagreements rather than inventing a consensus.
    同时保留两路文字并标记分歧，不补造所谓一致原话。
    """
    output = Path(output)
    w, q, d = (read_json(output / (name + ".json")) for name in ("whisper", "qwen", "diar"))

    def norm(text):
        return re.sub(r"[^\w\u3400-\u9fff]", "", text).lower()

    units = []
    for i, r in enumerate(q["results"]):
        words = [
            word
            for s in w["segments"]
            for word in s["words"]
            if r["start"] <= (word["start"] + word["end"]) / 2 < r["end"]
        ]
        wt = "".join(word["word"] for word in words).strip()
        similarity = SequenceMatcher(None, norm(wt), norm(r["text"])).ratio()
        review = similarity < 0.70 or (len(norm(r["text"])) > 15 and len(norm(wt)) < len(norm(r["text"])) * 0.55)
        units.append(
            dict(
                id=f"U{i + 1:05}",
                start=r["start"],
                end=r["end"],
                original=r["text"],
                whisper=wt,
                language=r.get("language", ""),
                speaker=speaker_for(r["start"], r["end"], d["segments"]),
                words=words,
                similarity=round(similarity, 4),
                needs_review=review,
                zh="",
            )
        )
    # A comparison score selects review targets; it does not certify the transcript.
    # 对照分数用于选择复核区间，不代表原话已通过听校。
    return dict(editorial_status="pending", units=units, review_units=sum(u["needs_review"] for u in units))


def align(media, output, config):
    """Align supplied wording; unsupported language and uncertain boundaries stay visible.
    对齐已提供的文字；不支持的语种与待核边界保持可见。
    """
    import soundfile as sf
    import torch
    from qwen_asr import Qwen3ForcedAligner

    payload = read_json(Path(output) / "fuse.json")
    audio, sr = sf.read(media["wav"], dtype="float32")
    model = Qwen3ForcedAligner.from_pretrained(
        config["models"]["aligner"],
        dtype=torch.bfloat16 if config["device"] != "cpu" else torch.float32,
        device_map="cuda:0" if config["device"] != "cpu" else "cpu",
        attn_implementation="sdpa",
    )
    supported = {
        "Chinese",
        "English",
        "Cantonese",
        "French",
        "German",
        "Italian",
        "Japanese",
        "Korean",
        "Portuguese",
        "Russian",
        "Spanish",
    }
    units = []
    for u in payload["units"]:
        unit = dict(u)
        if not u["original"] or u["language"] not in supported:
            unit["alignment"] = "skipped_unsupported_or_empty"
        else:
            results = model.align(
                audio=[(audio[int(u["start"] * sr) : int(u["end"] * sr)], sr)],
                text=[u["original"]],
                language=[u["language"]],
            )
            if len(results) != 1:
                raise RuntimeError("Aligner response count mismatch")
            unit["words"] = [
                dict(
                    word=w.text,
                    start=max(u["start"], min(u["end"], float(w.start_time) + u["start"])),
                    end=max(u["start"], min(u["end"], float(w.end_time) + u["start"])),
                )
                for w in results[0]
            ]
            unit["alignment"] = "forced_aligner_requires_review"
        units.append(unit)
    del model
    release_gpu()
    return dict(editorial_status="pending", units=units)


def export(output, filename="fuse.json"):
    """Export original language and its alternative, with no automatic editorial approval.
    导出原语言和对照文字，不自动宣称听校通过。
    """
    output = Path(output)
    payload = read_json(output / filename)
    text = ["# Original-language transcript / 原语言转写", "", "Editorial status: pending / 听校状态：待核", ""]
    for u in payload["units"]:
        text += [
            f"## {u['id']} · {timestamp(u['start'])}–{timestamp(u['end'])} · {u['speaker']}",
            "",
            u["original"],
            "",
            "Whisper comparison / Whisper对照： " + u.get("whisper", ""),
            "",
            "Review required / 需要复核： " + str(u.get("needs_review", True)),
            "",
        ]
    (output / "transcript.md").write_text("\n".join(text), encoding="utf8")
    return dict(file="transcript.md", editorial_status="pending")


def run(source, output, config, stages):
    """Execute ordered stages, reuse matching content fingerprints and record failures.
    顺序执行阶段、复用匹配内容指纹的结果，并记录失败。
    """
    offline_environment(config)
    output = Path(output).resolve()
    media = prepare(source, output, config)
    result = {}
    for stage in stages:
        save_json(output / "state.json", dict(stage=stage, status="running"))
        try:
            upstream = {}
            if stage in ("fuse", "align", "export"):
                needed = {"fuse": ["whisper", "qwen", "diar"], "align": ["fuse"], "export": ["fuse"]}[stage]
                for name in needed:
                    upstream[name] = sha256(output / (name + ".json"))
            key = fingerprint(media["source_sha256"], stage, dict(config, upstream=upstream))
            target = output / (stage + ".json")
            data = cached(target, key)
            if data is None:
                if stage in ("whisper", "qwen"):
                    data = globals()[stage](media, config)
                elif stage in ("diar", "align"):
                    data = globals()[stage](media, output, config)
                elif stage == "fuse":
                    data = fuse(output)
                elif stage == "export":
                    data = export(output)
                else:
                    raise ValueError(f"Unknown stage: {stage}")
                save_json(target, dict(data, status="complete", fingerprint=key, source_sha256=media["source_sha256"]))
            elif stage == "export" and not (output / "transcript.md").exists():
                export(output)
            result[stage] = "complete"
            save_json(output / "state.json", dict(stage=stage, status="complete"))
        except Exception as exc:
            save_json(output / "state.json", dict(stage=stage, status="failed", error=str(exc)))
            raise
    if sha256(source) != media["source_sha256"]:
        raise RuntimeError("Source media changed during processing / 原媒体处理期间发生变化")
    save_json(output / "run.json", dict(stages=result, editorial_status="pending", source_modified=False))
    return result
