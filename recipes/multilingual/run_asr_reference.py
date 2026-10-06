# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
from __future__ import annotations
import argparse, gc, importlib.util, json, math, os, sys, time, traceback
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(os.environ.get("WORKBENCH_TASK_ROOT", "work")).resolve()
for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
    os.environ[k] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
SHARED = Path(__file__).resolve().parents[1] / "legacy/shared_pipeline.py"
spec = importlib.util.spec_from_file_location("standard_asr", SHARED)
standard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(standard)
save = standard.atomic_json
import torch

torch.set_num_threads(8)
torch.set_num_interop_threads(4)
import soundfile as sf


# Reference helper: emit; see recipe prerequisites.
# 参考辅助函数：emit；执行前查看参考脚本依赖。
def emit(stage, code, **kw):
    d = dict(stage=stage, code=code, updated_at=standard.now(), pid=os.getpid(), **kw)
    save(ROOT / "_work/state/asr_progress.json", d)
    print(json.dumps(d, ensure_ascii=False), flush=True)


# Reference helper: sources; see recipe prerequisites.
# 参考辅助函数：sources；执行前查看参考脚本依赖。
def sources(only):
    inv = json.loads((ROOT / "06_核验材料/source_inventory.json").read_text(encoding="utf8"))
    for v in inv:
        if only and v["code"] not in only:
            continue
        p = ROOT / "06_核验材料/downloads" / f"{v['code']}.json"
        while True:
            try:
                d = json.loads(p.read_text(encoding="utf8")) if p.exists() else {}
            except json.JSONDecodeError:
                d = {}
            if d.get("status") == "complete":
                break
            if d.get("status") == "failed":
                emit("source_failed", v["code"], error=d.get("error"))
                d = None
                break
            emit("waiting_for_download", v["code"])
            time.sleep(10)
        if d:
            dest = ROOT / "_work/asr" / v["code"]
            dest.mkdir(parents=True, exist_ok=True)
            yield d, dest


# Reference helper: done; see recipe prerequisites.
# 参考辅助函数：done；执行前查看参考脚本依赖。
def done(p, d):
    if not p.exists():
        return False
    try:
        v = json.loads(p.read_text(encoding="utf8"))
        return v.get("status") == "complete" and v.get("source_sha256") == d["sha256"]
    except Exception:
        return False


# Reference helper: qwen; see recipe prerequisites.
# 参考辅助函数：qwen；执行前查看参考脚本依赖。
def qwen(only):
    from qwen_asr import Qwen3ASRModel

    model = None
    for d, out in sources(only):
        file = out / "qwen.json"
        if done(file, d):
            emit("qwen_cached", d["code"])
            continue
        if model is None:
            model = Qwen3ASRModel.from_pretrained(
                str(standard.QWEN_MODEL),
                dtype=torch.bfloat16,
                device_map="cuda:0",
                max_inference_batch_size=16,
                max_new_tokens=512,
            )
        audio, sr = sf.read(d["wav_path"], dtype="float32")
        dur = len(audio) / sr
        chunks = [(s, min(s + 30, dur)) for s in range(0, math.ceil(dur), 30)]
        rows = []
        started = time.time()
        if file.exists():
            old = json.loads(file.read_text(encoding="utf8"))
            if old.get("source_sha256") == d["sha256"]:
                rows = old.get("results", [])
        for j in range(len(rows), len(chunks), 16):
            chunk = chunks[j : j + 16]
            batch = [(audio[int(s * sr) : int(e * sr)], sr) for s, e in chunk]
            try:
                results = model.transcribe(audio=batch, language=[None] * len(batch))
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                results = []
                for b in batch:
                    results.extend(model.transcribe(audio=[b], language=[None]))
            for (s, e), res in zip(chunk, results):
                rows.append(dict(start=s, end=e, text=res.text, language=res.language))
            save(
                file,
                dict(
                    status="complete" if len(rows) == len(chunks) else "running",
                    source_sha256=d["sha256"],
                    source=d["wav_path"],
                    engine="Qwen3-ASR-1.7B",
                    chunk_seconds=30,
                    language_hint=None,
                    results=rows,
                    duration=dur,
                    elapsed=time.time() - started,
                ),
            )
            emit("qwen", d["code"], done=len(rows), total=len(chunks))
    del model
    gc.collect()
    torch.cuda.empty_cache()


# Reference helper: whisper; see recipe prerequisites.
# 参考辅助函数：whisper；执行前查看参考脚本依赖。
def whisper(only):
    from faster_whisper import WhisperModel, BatchedInferencePipeline

    model = None
    for d, out in sources(only):
        file = out / "whisper.json"
        if done(file, d):
            emit("whisper_cached", d["code"])
            continue
        if model is None:
            model = WhisperModel(str(standard.WHISPER_MODEL), device="cuda", compute_type="float16", cpu_threads=8)
            batched = BatchedInferencePipeline(model=model)
        started = time.time()
        segs, info = batched.transcribe(
            d["wav_path"],
            language=None,
            multilingual=True,
            task="transcribe",
            beam_size=5,
            condition_on_previous_text=False,
            initial_prompt=None,
            word_timestamps=True,
            without_timestamps=False,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 300},
            batch_size=16,
            repetition_penalty=1.05,
            no_repeat_ngram_size=3,
        )
        rows = []
        for seg in segs:
            rows.append(
                dict(
                    id=seg.id,
                    start=seg.start,
                    end=seg.end,
                    text=seg.text.strip(),
                    avg_logprob=seg.avg_logprob,
                    no_speech_prob=seg.no_speech_prob,
                    compression_ratio=seg.compression_ratio,
                    words=[
                        dict(start=w.start, end=w.end, word=w.word, probability=w.probability) for w in seg.words or []
                    ],
                )
            )
            if len(rows) % 30 == 0:
                emit("whisper", d["code"], segments=len(rows), audio_seconds=seg.end)
        if not rows:
            raise RuntimeError(f"Empty Whisper {d['code']}")
        save(
            file,
            dict(
                status="complete",
                source_sha256=d["sha256"],
                source=d["wav_path"],
                engine="faster-whisper-large-v3-turbo",
                initial_prompt=None,
                multilingual=True,
                language=info.language,
                duration=info.duration,
                duration_after_vad=info.duration_after_vad,
                elapsed=time.time() - started,
                segments=rows,
            ),
        )
        emit("whisper_done", d["code"], segments=len(rows))
    if model is not None:
        del batched, model
    gc.collect()
    torch.cuda.empty_cache()


# Reference helper: diar; see recipe prerequisites.
# 参考辅助函数：diar；执行前查看参考脚本依赖。
def diar(only):
    for d, out in sources(only):
        file = out / "diarization.json"
        if done(file, d):
            emit("diarization_cached", d["code"])
            continue
        p = standard.Pipeline(Path(d["wav_path"]), out / "standard_diar")
        rows = p.run_diarization()
        save(
            file,
            dict(
                status="complete",
                source_sha256=d["sha256"],
                engine="3D-Speaker/CAMPPlus",
                segments=rows,
                speaker_count=len(set(r["speaker"] for r in rows)),
                identity_inference=False,
            ),
        )
        emit("diarization_done", d["code"], segments=len(rows))


# Reference helper: fuse; see recipe prerequisites.
# 参考辅助函数：fuse；执行前查看参考脚本依赖。
def fuse(only):
    import re

    norm = lambda t: re.sub(r"[^\w\u4e00-\u9fff]", "", t).lower()
    for d, out in sources(only):
        w = json.loads((out / "whisper.json").read_text(encoding="utf8"))
        q = json.loads((out / "qwen.json").read_text(encoding="utf8"))
        sp = json.loads((out / "diarization.json").read_text(encoding="utf8"))
        windows = []
        for i, r in enumerate(q["results"]):
            words = [
                word
                for s in w["segments"]
                for word in s["words"]
                if r["start"] <= ((word["start"] + word["end"]) / 2) < r["end"]
            ]
            wt = "".join(x["word"] for x in words).strip()
            ratio = SequenceMatcher(None, norm(wt), norm(r["text"])).ratio()
            windows.append(
                dict(
                    unit_id=f"{d['code']}-U{i + 1:03}",
                    start=r["start"],
                    end=r["end"],
                    qwen=r["text"],
                    whisper=wt,
                    similarity=round(ratio, 4),
                    needs_review=(
                        ratio < 0.70 or (len(norm(r["text"])) > 15 and len(norm(wt)) < len(norm(r["text"])) * 0.55)
                    ),
                )
            )
        for s in w["segments"]:
            s["speaker"] = standard.Pipeline.speaker_for(s["start"], s["end"], sp["segments"])
        save(
            out / "alignment_review.json",
            dict(status="needs_editorial_review", source_sha256=d["sha256"], units=windows, segments=w["segments"]),
        )
        text = [
            "# " + d["title"] + " 原话双路对照工作稿",
            "",
            f"来源：{d['url']}",
            "",
            "此文件为校对底稿，尚非最终原话稿。",
            "",
        ]
        for r in windows:
            text.extend(
                [
                    f"## {r['unit_id']} {standard.hms(r['start'])}至{standard.hms(r['end'])}",
                    "",
                    "Qwen：" + r["qwen"],
                    "",
                    "Whisper：" + r["whisper"],
                    "",
                ]
            )
        standard.atomic_text(out / "双路对照工作稿.md", "\n".join(text))
        emit("alignment_done", d["code"], units=len(windows), review_units=sum(r["needs_review"] for r in windows))


# Reference helper: main; see recipe prerequisites.
# 参考辅助函数：main；执行前查看参考脚本依赖。
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", choices=["qwen", "whisper", "diar", "fuse", "all"], default="all")
    p.add_argument("--only", nargs="*")
    a = p.parse_args()
    stages = ["qwen", "whisper", "diar", "fuse"] if a.stage == "all" else [a.stage]
    try:
        for s in stages:
            globals()[s](a.only)
        emit("asr_stages_complete", "ALL", stages=stages)
    except Exception as e:
        emit("failed", "ALL", error=str(e), traceback=traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
