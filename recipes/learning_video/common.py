# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
# REVIEW SNAPSHOT: redacted task data; see source provenance and audit.
from pathlib import Path
import json, os, hashlib, subprocess, time, uuid

ROOT = Path(os.environ.get("WORKBENCH_TASK_ROOT", "work")).resolve()
DATA_ROOT = ROOT.parent
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")
ASR_BASE = Path(os.environ.get("WORKBENCH_MODEL_ROOT", "models")).resolve()
FULL_WHISPER = ASR_BASE / "whisper-full"
SOURCES = {
    "A": dict(name="source_a", file=DATA_ROOT / "source_a.m4a", old=DATA_ROOT / "source_a_asr"),
    "B": dict(name="source_b", file=DATA_ROOT / "source_b.mp3", old=DATA_ROOT / "source_b_asr"),
    "C": dict(name="source_c", file=DATA_ROOT / "source_c.mp3", old=DATA_ROOT / "source_c_asr"),
}


# Reference helper: read; see recipe prerequisites.
# 参考辅助函数：read；执行前查看参考脚本依赖。
def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


# Reference helper: save; see recipe prerequisites.
# 参考辅助函数：save；执行前查看参考脚本依赖。
def save(p, x):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_suffix(p.suffix + "." + uuid.uuid4().hex + ".tmp")
    t.write_text(json.dumps(x, ensure_ascii=False, indent=2), encoding="utf8")
    for attempt in range(20):
        try:
            t.replace(p)
            break
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.02)


# Reference helper: log; see recipe prerequisites.
# 参考辅助函数：log；执行前查看参考脚本依赖。
def log(stage, **kw):
    x = dict(stage=stage, time=time.time(), pid=os.getpid(), **kw)
    save(ROOT / "work" / f"state_{stage.split('_')[0]}.json", x)
    print(json.dumps(x, ensure_ascii=False), flush=True)


# Reference helper: sha; see recipe prerequisites.
# 参考辅助函数：sha；执行前查看参考脚本依赖。
def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


# Reference helper: probe; see recipe prerequisites.
# 参考辅助函数：probe；执行前查看参考脚本依赖。
def probe(p):
    return json.loads(
        subprocess.check_output(
            [FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(p)], encoding="utf8"
        )
    )


# Reference helper: tc; see recipe prerequisites.
# 参考辅助函数：tc；执行前查看参考脚本依赖。
def tc(s):
    return f"{int(s) // 3600:02}:{int(s) % 3600 // 60:02}:{int(s) % 60:02}"


# Reference helper: video path; see recipe prerequisites.
# 参考辅助函数：video path；执行前查看参考脚本依赖。
def video_path(code):
    return ROOT / "视频" / f"{code}_{SOURCES[code]['name']}_4K原声学习.{'mp4' if code == 'A' else 'mkv'}"


# Reference helper: inventory; see recipe prerequisites.
# 参考辅助函数：inventory；执行前查看参考脚本依赖。
def inventory():
    result = []
    for code, d in SOURCES.items():
        pr = probe(d["file"])
        asr = d["old"] / "work/asr"
        q = read(asr / "qwen.json")
        w = read(asr / "whisper.json")
        di = read(asr / "diarization.json")
        item = dict(
            code=code,
            name=d["name"],
            path=str(d["file"]),
            sha256=sha(d["file"]),
            probe=pr,
            wav=str(d["old"] / "work/audio.wav"),
            qwen_count=len(q["results"]),
            qwen_chars=sum(len(x["text"]) for x in q["results"]),
            whisper_segments=len(w["segments"]),
            whisper_words=sum(len(x.get("words", [])) for x in w["segments"]),
            diar_segments=len(di["segments"]),
            speakers=di["speaker_count"],
        )
        result.append(item)
        print(json.dumps({k: v for k, v in item.items() if k not in ("probe",)}, ensure_ascii=False))
    save(ROOT / "核验/source_inventory.json", result)


if __name__ == "__main__":
    inventory()
