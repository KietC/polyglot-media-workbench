# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
from __future__ import annotations
import argparse, concurrent.futures, hashlib, json, os, time, traceback
from pathlib import Path

ROOT = Path(os.environ.get("WORKBENCH_TASK_ROOT", "work")).resolve()


# Reference helper: save; see recipe prerequisites.
# 参考辅助函数：save；执行前查看参考脚本依赖。
def save(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf8")
    tmp.replace(p)


# Reference helper: digest; see recipe prerequisites.
# 参考辅助函数：digest；执行前查看参考脚本依赖。
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


# Reference helper: extract; see recipe prerequisites.
# 参考辅助函数：extract；执行前查看参考脚本依赖。
def extract(d):
    import av, cv2, numpy as np

    cv2.setNumThreads(1)
    code = d["code"]
    out = ROOT / "_work/frames" / code
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / "frames.json"
    if manifest.exists():
        old = json.loads(manifest.read_text(encoding="utf8"))
        if (
            old.get("status") == "complete"
            and old.get("source_sha256") == d["sha256"]
            and all(Path(r["path"]).exists() for r in old["frames"])
        ):
            return old
    started = time.time()
    rows = []
    candidates = []
    prev = None
    kept = None
    last_t = -1.0
    last_scene = -1.0
    last_period = -1.0
    frames = 0

    # Reference helper: dhash; see recipe prerequisites.
    # 参考辅助函数：dhash；执行前查看参考脚本依赖。
    def dhash(im):
        sm = cv2.resize(im, (9, 8))
        bits = (sm[:, 1:] > sm[:, :-1]).flatten()
        return sum(int(x) << i for i, x in enumerate(bits))

    with av.open(d["video_path"]) as container:
        stream = container.streams.video[0]
        stream.codec_context.thread_count = 4
        stream.codec_context.thread_type = "AUTO"
        for idx, frame in enumerate(container.decode(stream)):
            frames += 1
            t = float(frame.time or 0)
            small = frame.reformat(
                width=320, height=max(2, round(frame.height / frame.width * 320)), format="gray"
            ).to_ndarray()
            score = (
                float(np.abs(small.astype(np.int16) - prev.astype(np.int16)).mean() / 255) if prev is not None else 1.0
            )
            scene = score > 0.08 and t - last_scene > 0.1
            period = t - last_period >= 0.999
            prev = small
            if not (scene or period or idx == 0):
                continue
            if scene:
                last_scene = t
            if period:
                last_period = t
            h = dhash(small)
            delta = float(np.abs(small.astype(np.int16) - kept.astype(np.int16)).mean()) if kept is not None else 255.0
            distance = (h ^ rows[-1]["dhash"]).bit_count() if rows else 64
            retain = not rows or scene or delta >= 3.5 or distance >= 4 or t - last_t >= 10
            if retain:
                path = out / f"f{idx:07d}_t{t:010.3f}.jpg"
                frame.to_image().save(path, quality=95, subsampling=0)
                row = dict(
                    frame_id=f"{code}-F{len(rows) + 1:04d}",
                    index=idx,
                    timestamp=round(t, 4),
                    path=str(path),
                    width=frame.width,
                    height=frame.height,
                    scene_score=round(score, 5),
                    dhash=h,
                    delta=round(delta, 3),
                    reasons=[x for x, v in [("start", idx == 0), ("scene", scene), ("periodic", period)] if v],
                    sha256=digest(path),
                )
                rows.append(row)
                kept = small.copy()
                last_t = t
            candidates.append(
                dict(timestamp=round(t, 4), index=idx, retained=retain, frame_id=rows[-1]["frame_id"], scene=scene)
            )
            if len(candidates) % 100 == 0:
                save(
                    out / "progress.json",
                    dict(
                        status="running",
                        pid=os.getpid(),
                        seconds=t,
                        duration=d["duration"],
                        retained=len(rows),
                        candidates=len(candidates),
                    ),
                )
        # Keep an exact end frame so the tail is represented even when visually unchanged.
        if t - last_t > 0.05:
            path = out / f"f{idx:07d}_t{t:010.3f}.jpg"
            frame.to_image().save(path, quality=95, subsampling=0)
            rows.append(
                dict(
                    frame_id=f"{code}-F{len(rows) + 1:04d}",
                    index=idx,
                    timestamp=round(t, 4),
                    path=str(path),
                    width=frame.width,
                    height=frame.height,
                    reasons=["end"],
                    sha256=digest(path),
                )
            )
    result = dict(
        status="complete",
        code=code,
        source_sha256=d["sha256"],
        source_path=d["video_path"],
        decoded_frames=frames,
        duration=d["duration"],
        last_frame_time=t,
        candidate_count=len(candidates),
        retained_count=len(rows),
        algorithm="all-frame scene delta plus one-second candidates, conservative dedup, original resolution JPEG95",
        elapsed=time.time() - started,
        frames=rows,
        candidates=candidates,
    )
    save(manifest, result)
    print(
        json.dumps({k: v for k, v in result.items() if k not in ("frames", "candidates")}, ensure_ascii=False),
        flush=True,
    )
    return result


OCR = None


# Reference helper: ocr init; see recipe prerequisites.
# 参考辅助函数：ocr init；执行前查看参考脚本依赖。
def ocr_init():
    global OCR
    from rapidocr_onnxruntime import RapidOCR

    OCR = RapidOCR(
        intra_op_num_threads=2,
        inter_op_num_threads=1,
        det_limit_side_len=1920,
        det_limit_type="max",
        text_score=0.45,
        rec_batch_num=16,
    )


# Reference helper: ocr one; see recipe prerequisites.
# 参考辅助函数：ocr one；执行前查看参考脚本依赖。
def ocr_one(item):
    frame, code = item
    p = ROOT / "_work/ocr" / code / f"{frame['frame_id']}.json"
    if p.exists():
        old = json.loads(p.read_text(encoding="utf8"))
        if old.get("status") == "complete" and old.get("frame_sha256") == frame["sha256"]:
            return old
    started = time.time()
    try:
        result, elapse = OCR(frame["path"])
        result = result or []
        row = dict(
            status="complete",
            frame_id=frame["frame_id"],
            code=code,
            timestamp=frame["timestamp"],
            frame_path=frame["path"],
            frame_sha256=frame["sha256"],
            engine="RapidOCR PP-OCR ONNX",
            elapsed=time.time() - started,
            text="\n".join(str(r[1]) for r in result),
            boxes=[dict(points=r[0], text=r[1], confidence=float(r[2])) for r in result],
        )
    except Exception as e:
        row = dict(status="failed", frame_id=frame["frame_id"], code=code, error=str(e))
    save(p, row)
    return row


# Reference helper: main; see recipe prerequisites.
# 参考辅助函数：main；执行前查看参考脚本依赖。
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", choices=["frames", "ocr", "all"], default="all")
    p.add_argument("--only", nargs="*")
    p.add_argument("--workers", type=int, default=8)
    a = p.parse_args()
    src = json.loads((ROOT / "06_核验材料/download_summary.json").read_text(encoding="utf8"))["results"]
    src = [d for d in src if d["status"] == "complete" and (not a.only or d["code"] in a.only)]
    if a.stage in ("frames", "all"):
        with concurrent.futures.ProcessPoolExecutor(max_workers=a.workers) as pool:
            list(pool.map(extract, src))
    if a.stage in ("ocr", "all"):
        items = []
        for d in src:
            f = json.loads((ROOT / "_work/frames" / d["code"] / "frames.json").read_text(encoding="utf8"))
            items.extend((r, d["code"]) for r in f["frames"])
        rows = []
        with concurrent.futures.ProcessPoolExecutor(max_workers=a.workers, initializer=ocr_init) as pool:
            for i, r in enumerate(pool.map(ocr_one, items), 1):
                rows.append(r)
                if i % 25 == 0:
                    progress = dict(status="running", done=i, total=len(items), pid=os.getpid())
                    save(ROOT / "_work/state/ocr_progress.json", progress)
                    print(json.dumps(progress), flush=True)
        counts = {d["code"]: sum(r["code"] == d["code"] and r["status"] == "complete" for r in rows) for d in src}
        failures = [r for r in rows if r["status"] != "complete"]
        save(
            ROOT / "06_核验材料/ocr_summary.json",
            dict(
                status="complete" if not failures else "incomplete", total=len(rows), counts=counts, failures=failures
            ),
        )
        print(json.dumps(dict(stage="ocr_done", total=len(rows), failures=len(failures))), flush=True)


if __name__ == "__main__":
    main()
