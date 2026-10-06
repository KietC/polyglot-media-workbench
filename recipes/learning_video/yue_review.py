# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
import os, sys, gc

os.environ.update(PYTHONUTF8="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", OMP_NUM_THREADS="8")
from common import *
import importlib.util, soundfile as sf

spec = importlib.util.spec_from_file_location(
    "std", str(Path(__file__).resolve().parents[1] / "legacy/shared_pipeline.py")
)
std = importlib.util.module_from_spec(spec)
spec.loader.exec_module(std)
from faster_whisper import WhisperModel, BatchedInferencePipeline

model = WhisperModel(
    str(ASR_BASE / "models/ct2/awong-whisper-large-v3-yue-test1-baseline-float16"),
    device="cuda",
    compute_type="float16",
    cpu_threads=8,
)
pipe = BatchedInferencePipeline(model=model)
for code in sys.argv[1] if len(sys.argv) > 1 else "A":
    d = SOURCES[code]
    audio, sr = sf.read(d["old"] / "work/audio.wav", dtype="float32")
    q = read(d["old"] / "work/asr/qwen.json")["results"]
    dest = ROOT / "work" / code
    rows = [x for x in q if x.get("language") in ("Cantonese", "Chinese")]
    if "--sample" in sys.argv:
        rows = rows[:10]
    out = dest / ("yue_sample.json" if "--sample" in sys.argv else "yue_review.json")
    results = read(out)["rows"] if out.exists() else []
    for k, r in enumerate(rows):
        if any(x["start"] == r["start"] for x in results):
            continue
        s, e = r["start"], r["end"]
        segment = audio[int(s * sr) : int(e * sr)]
        segs, _ = pipe.transcribe(
            segment,
            language="zh",
            task="transcribe",
            beam_size=5,
            condition_on_previous_text=False,
            initial_prompt=None,
            word_timestamps=True,
            vad_filter=False,
            clip_timestamps=[dict(start=0, end=len(segment) / sr)],
            batch_size=1,
        )
        segs = list(segs)
        item = dict(
            start=s,
            end=e,
            text="".join(x.text for x in segs).strip(),
            qwen=r["text"],
            segments=[
                dict(
                    start=x.start + s,
                    end=x.end + s,
                    text=x.text,
                    avg_logprob=x.avg_logprob,
                    no_speech_prob=x.no_speech_prob,
                    words=[
                        dict(start=w.start + s, end=w.end + s, word=w.word, probability=w.probability)
                        for w in x.words or []
                    ],
                )
                for x in segs
            ],
        )
        results.append(item)
        save(
            out,
            dict(
                status="complete" if len(results) == len(rows) else "running",
                engine="awong-whisper-large-v3-yue-test1-baseline",
                rows=results,
            ),
        )
        log("yue_progress", code=code, done=len(results), total=len(rows))
        if "--sample" in sys.argv:
            print(s, item["text"], flush=True)
