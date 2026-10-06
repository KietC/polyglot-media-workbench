# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import av
import numpy as np
import torch
from qwen_asr import Qwen3ASRModel


# Reference helper: write progress; see recipe prerequisites.
# 参考辅助函数：write progress；执行前查看参考脚本依赖。
def write_progress(path: Path | None, payload: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# Reference helper: decode chunks; see recipe prerequisites.
# 参考辅助函数：decode chunks；执行前查看参考脚本依赖。
def decode_chunks(
    audio_path: Path, chunk_seconds: float, sample_rate: int = 16000
) -> list[tuple[np.ndarray, int, float, float]]:
    container = av.open(str(audio_path))
    stream = container.streams.audio[0]
    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=sample_rate)
    chunk_samples = int(chunk_seconds * sample_rate)
    chunks: list[tuple[np.ndarray, int, float, float]] = []
    buffers: list[np.ndarray] = []
    buffered = 0
    chunk_start = 0.0

    # Reference helper: emit from buffer; see recipe prerequisites.
    # 参考辅助函数：emit from buffer；执行前查看参考脚本依赖。
    def emit_from_buffer(force: bool = False) -> None:
        nonlocal buffered, buffers, chunk_start
        while buffered >= chunk_samples or (force and buffered > 0):
            take = min(chunk_samples, buffered)
            joined = np.concatenate(buffers)
            current = joined[:take]
            remaining = joined[take:]
            buffers = [remaining] if remaining.size else []
            buffered = int(remaining.size)
            duration = current.size / sample_rate
            chunks.append((current.astype(np.float32) / 32768.0, sample_rate, chunk_start, chunk_start + duration))
            chunk_start += duration
            if not force:
                break

    for packet in container.demux(stream):
        for frame in packet.decode():
            frames = resampler.resample(frame)
            if not isinstance(frames, list):
                frames = [frames]
            for out in frames:
                arr = out.to_ndarray()
                if arr.ndim == 2:
                    arr = arr[0]
                arr = np.asarray(arr, dtype=np.int16)
                if arr.size == 0:
                    continue
                buffers.append(arr)
                buffered += int(arr.size)
                emit_from_buffer(force=False)
    emit_from_buffer(force=True)
    return chunks


# Reference helper: main; see recipe prerequisites.
# 参考辅助函数：main；执行前查看参考脚本依赖。
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument(
        "--model",
        default="models/media_workbench/07_本地AI运行环境_勿移动路径索引/cantonese_stt/models/hf_transformers/Qwen3-ASR-1.7B",
    )
    parser.add_argument("--language", default="Cantonese")
    parser.add_argument(
        "--out-dir", default="models/media_workbench/07_本地AI运行环境_勿移动路径索引/cantonese_stt/outputs/qwen3_asr"
    )
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--chunk-seconds",
        type=float,
        default=0,
        help="Split long audio and process chunk batches. 0 disables chunking.",
    )
    parser.add_argument("--chunk-batch-size", type=int, default=16)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--progress-file", default=None)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_path = Path(args.audio)
    progress_file = Path(args.progress_file) if args.progress_file else None

    write_progress(progress_file, {"stage": "loading_model", "updated_at": time.time()})
    started = time.perf_counter()
    model = Qwen3ASRModel.from_pretrained(
        args.model,
        dtype=torch.bfloat16,
        device_map="cuda:0",
        max_inference_batch_size=args.batch_size,
        max_new_tokens=args.max_new_tokens,
    )
    load_seconds = time.perf_counter() - started
    write_progress(progress_file, {"stage": "model_loaded", "load_seconds": load_seconds, "updated_at": time.time()})

    infer_started = time.perf_counter()
    chunk_payloads: list[dict] = []
    if args.chunk_seconds and args.chunk_seconds > 0:
        write_progress(progress_file, {"stage": "decoding_audio", "updated_at": time.time()})
        chunks = decode_chunks(audio_path, args.chunk_seconds)
        total = len(chunks)
        write_progress(
            progress_file,
            {
                "stage": "transcribing",
                "chunks_done": 0,
                "chunks_total": total,
                "percent": 0,
                "updated_at": time.time(),
            },
        )
        for offset in range(0, total, args.chunk_batch_size):
            batch = chunks[offset : offset + args.chunk_batch_size]
            audios = [(samples, sr) for samples, sr, _, _ in batch]
            languages = [args.language] * len(audios)
            results = model.transcribe(audio=audios, language=languages)
            for (samples, sr, start, end), result in zip(batch, results):
                chunk_payloads.append(
                    {
                        "start": start,
                        "end": end,
                        "language": getattr(result, "language", None),
                        "text": getattr(result, "text", str(result)),
                    }
                )
            done = min(offset + len(batch), total)
            write_progress(
                progress_file,
                {
                    "stage": "transcribing",
                    "chunks_done": done,
                    "chunks_total": total,
                    "percent": round(done / total * 100, 2) if total else 100,
                    "updated_at": time.time(),
                },
            )
    else:
        results = model.transcribe(audio=str(audio_path), language=args.language)
        chunk_payloads = [
            {
                "start": None,
                "end": None,
                "language": getattr(result, "language", None),
                "text": getattr(result, "text", str(result)),
            }
            for result in results
        ]
    infer_seconds = time.perf_counter() - infer_started

    payload = {
        "audio": str(audio_path),
        "model": args.model,
        "language_hint": args.language,
        "load_seconds": load_seconds,
        "infer_seconds": infer_seconds,
        "chunk_seconds": args.chunk_seconds,
        "chunk_batch_size": args.chunk_batch_size,
        "results": chunk_payloads,
    }
    base = out_dir / audio_path.with_suffix("").name
    txt = "\n".join(item["text"] for item in payload["results"])
    base.with_suffix(".txt").write_text(txt + ("\n" if txt else ""), encoding="utf-8")
    base.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_progress(
        progress_file,
        {
            "stage": "done",
            "txt": str(base.with_suffix(".txt")),
            "json": str(base.with_suffix(".json")),
            "infer_seconds": infer_seconds,
            "chunks_total": len(chunk_payloads),
            "updated_at": time.time(),
        },
    )
    print(
        json.dumps(
            {
                "txt": str(base.with_suffix(".txt")),
                "json": str(base.with_suffix(".json")),
                "infer_seconds": infer_seconds,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
