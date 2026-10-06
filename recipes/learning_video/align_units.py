# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
import os, sys, gc, re, time, math

os.environ.update(
    PYTHONUTF8="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", OMP_NUM_THREADS="8", TOKENIZERS_PARALLELISM="false"
)
from common import *
import torch, soundfile as sf

torch.set_num_threads(8)
from qwen_asr import Qwen3ForcedAligner


# Reference helper: run; see recipe prerequisites.
# 参考辅助函数：run；执行前查看参考脚本依赖。
def run(code, model):
    d = SOURCES[code]
    folder = ROOT / "work" / code
    while not (folder / "working_units.json").exists():
        time.sleep(2)
    units = read(folder / "working_units.json")["units"]
    audio, sr = sf.read(d["old"] / "work/audio.wav", dtype="float32")
    target = folder / "aligned_units.json"
    done = read(target)["units"] if target.exists() else []
    todo = [x for x in units if x["id"] not in {r["id"] for r in done}]
    batch = 8
    for j in range(0, len(todo), batch):
        rows = todo[j : j + batch]
        valid = [u for u in rows if u["original"]]
        audios = [(audio[int(u["start"] * sr) : int(u["end"] * sr)], sr) for u in valid]
        try:
            results = (
                model.align(audio=audios, text=[u["original"] for u in valid], language=[u["language"] for u in valid])
                if valid
                else []
            )
        except Exception:
            torch.cuda.empty_cache()
            results = []
            for a, u in zip(audios, valid):
                results.extend(model.align(audio=[a], text=[u["original"]], language=[u["language"]]))
        keyed = {u["id"]: r for u, r in zip(valid, results)}
        for u in rows:
            r = keyed.get(u["id"])
            words = []
            if r:
                for w in r:
                    start = float(w.start_time) + u["start"]
                    end = float(w.end_time) + u["start"]
                    assert math.isfinite(start) and math.isfinite(end)
                    words.append(
                        dict(
                            word=w.text,
                            start=round(max(u["start"], min(start, u["end"])), 3),
                            end=round(max(u["start"], min(end, u["end"])), 3),
                        )
                    )
            done.append(dict(**u, words=words, alignment="Qwen3-ForcedAligner-0.6B"))
        done.sort(key=lambda r: r["start"])
        save(target, dict(status="complete" if len(done) == len(units) else "running", units=done))
        log("align_progress", code=code, done=len(done), total=len(units))


if __name__ == "__main__":
    mp = ROOT / "work/models/Qwen3-ForcedAligner-0.6B"
    while not (mp / "download_manifest.json").exists():
        time.sleep(3)
    model = Qwen3ForcedAligner.from_pretrained(
        str(mp), dtype=torch.bfloat16, device_map="cuda:0", attn_implementation="sdpa"
    )
    for code in sys.argv[1] if len(sys.argv) > 1 else "ABC":
        run(code, model)
