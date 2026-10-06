# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
import os, sys, time, math, gc

os.environ.update(
    PYTHONUTF8="1",
    HF_HUB_OFFLINE="1",
    TRANSFORMERS_OFFLINE="1",
    OMP_NUM_THREADS="8",
    MKL_NUM_THREADS="8",
    TOKENIZERS_PARALLELISM="false",
)
from common import *
import importlib.util

spec = importlib.util.spec_from_file_location(
    "std", str(Path(__file__).resolve().parents[1] / "legacy/shared_pipeline.py")
)
std = importlib.util.module_from_spec(spec)
spec.loader.exec_module(std)
import soundfile as sf
from faster_whisper import WhisperModel, BatchedInferencePipeline


# Reference helper: run; see recipe prerequisites.
# 参考辅助函数：run；执行前查看参考脚本依赖。
def run(code, sample=False):
    d = SOURCES[code]
    dest = ROOT / "work" / code
    dest.mkdir(exist_ok=True)
    oldq = read(d["old"] / "work/asr/qwen.json")["results"]
    audio, sr = sf.read(d["old"] / "work/audio.wav", dtype="float32")
    duration = len(audio) / sr
    model = WhisperModel(str(FULL_WHISPER), device="cuda", compute_type="float16", cpu_threads=8, num_workers=1)
    pipeline = BatchedInferencePipeline(model=model)
    for begin in range(0, math.ceil(duration), 600):
        if sample and begin > 0:
            break
        end = min(duration, begin + (180 if sample else 600))
        out = dest / (f"full_{begin:06}.json" if not sample else "sample_full.json")
        if out.exists() and read(out).get("status") == "complete":
            continue
        clips = [dict(start=s, end=min(s + 30, end - begin)) for s in range(0, math.ceil(end - begin), 30)]
        batch = 8
        starttime = time.time()
        while True:
            try:
                segs, info = pipeline.transcribe(
                    audio[int(begin * sr) : int(end * sr)],
                    language=None,
                    multilingual=True,
                    task="transcribe",
                    beam_size=5,
                    condition_on_previous_text=False,
                    initial_prompt=None,
                    word_timestamps=True,
                    without_timestamps=False,
                    vad_filter=False,
                    clip_timestamps=clips,
                    batch_size=batch,
                    repetition_penalty=1.05,
                    no_repeat_ngram_size=3,
                )
                rows = []
                for s in segs:
                    rows.append(
                        dict(
                            start=round(s.start + begin, 3),
                            end=round(s.end + begin, 3),
                            text=s.text.strip(),
                            avg_logprob=s.avg_logprob,
                            no_speech_prob=s.no_speech_prob,
                            compression_ratio=s.compression_ratio,
                            words=[
                                dict(
                                    start=round(w.start + begin, 3),
                                    end=round(w.end + begin, 3),
                                    word=w.word,
                                    probability=w.probability,
                                )
                                for w in s.words or []
                            ],
                        )
                    )
                break
            except Exception as exc:
                if batch == 1 or not any(k in str(exc).lower() for k in ("memory", "cuda")):
                    raise
                batch = max(1, batch // 2)
                log("asr_retry", code=code, batch=batch, error=str(exc))
        save(
            out,
            dict(
                status="complete",
                engine="faster-whisper-large-v3",
                start=begin,
                end=end,
                elapsed=time.time() - starttime,
                segments=rows,
            ),
        )
        log(
            "asr_progress",
            code=code,
            seconds=end,
            total=duration,
            elapsed=time.time() - starttime,
            segments=len(rows),
            batch=batch,
        )
    del model, pipeline
    gc.collect()
    if not sample:
        rows = []
        for p in sorted(dest.glob("full_*.json")):
            rows.extend(read(p)["segments"])
        save(
            dest / "full_whisper.json",
            dict(status="complete", engine="faster-whisper-large-v3", segments=rows, duration=duration),
        )


if __name__ == "__main__":
    for c in sys.argv[1] if len(sys.argv) > 1 else "ABC":
        run(c, "--sample" in sys.argv)
