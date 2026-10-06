# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
import os

os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", OMP_NUM_THREADS="8", TOKENIZERS_PARALLELISM="false")
from common import *
from recover_german import candidates
import gc, importlib.util, soundfile as sf, torch
from faster_whisper import WhisperModel

torch.set_num_threads(8)
spec = importlib.util.spec_from_file_location(
    "std", str(Path(__file__).resolve().parents[1] / "legacy/shared_pipeline.py")
)
std = importlib.util.module_from_spec(spec)
spec.loader.exec_module(std)


# Reference helper: main; see recipe prerequisites.
# 参考辅助函数：main；执行前查看参考脚本依赖。
def main():
    rows = []
    for code in "ABC":
        merged = []
        for r in sorted(candidates(code), key=lambda x: x["start"]):
            if (
                merged
                and r["start"] <= merged[-1]["end"]
                and max(r["end"], merged[-1]["end"]) - merged[-1]["start"] <= 32
            ):
                merged[-1]["end"] = max(r["end"], merged[-1]["end"])
                merged[-1]["prior"].append(r)
            else:
                merged.append(dict(code=code, start=r["start"], end=r["end"], prior=[r]))
        rows.extend(merged)
    audios = {c: sf.read(SOURCES[c]["old"] / "work/audio.wav", dtype="float32") for c in "ABC"}
    model = WhisperModel(str(FULL_WHISPER), device="cuda", compute_type="float16", cpu_threads=8)
    for i, r in enumerate(rows):
        a, sr = audios[r["code"]]
        clip = a[int(r["start"] * sr) : int(r["end"] * sr)]
        segs, info = model.transcribe(
            clip,
            language=None,
            task="transcribe",
            initial_prompt=None,
            condition_on_previous_text=False,
            word_timestamps=True,
            beam_size=5,
            vad_filter=False,
        )
        r["whisper_language"] = info.language
        r["whisper_probability"] = info.language_probability
        r["whisper_segments"] = [
            dict(
                start=s.start + r["start"],
                end=s.end + r["start"],
                text=s.text,
                avg_logprob=s.avg_logprob,
                words=[
                    dict(word=w.word, start=w.start + r["start"], end=w.end + r["start"], probability=w.probability)
                    for w in s.words or []
                ],
            )
            for s in segs
        ]
        r["whisper"] = " ".join(s["text"] for s in r["whisper_segments"])
        log("german_whisper", done=i + 1, total=len(rows))
    del model
    gc.collect()
    torch.cuda.empty_cache()
    from qwen_asr import Qwen3ASRModel

    model = Qwen3ASRModel.from_pretrained(
        str(std.QWEN_MODEL), dtype=torch.bfloat16, device_map="cuda:0", max_inference_batch_size=4, max_new_tokens=512
    )
    for i in range(0, len(rows), 4):
        batch = rows[i : i + 4]
        clips = []
        for r in batch:
            a, sr = audios[r["code"]]
            clips.append((a[int(r["start"] * sr) : int(r["end"] * sr)], sr))
        results = model.transcribe(audio=clips, language=[None] * len(batch))
        for r, res in zip(batch, results):
            r["qwen"] = res.text
            r["qwen_language"] = res.language
        save(
            ROOT / "核验/德语短句重新听辨.json", dict(rows=rows, status="complete" if i + 4 >= len(rows) else "running")
        )
        log("german_qwen", done=min(i + 4, len(rows)), total=len(rows))


if __name__ == "__main__":
    main()
