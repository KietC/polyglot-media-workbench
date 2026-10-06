# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
from common import *
from learning_assets import ASSETS, selected_terms, selected_image
from PIL import Image, ImageFont, ImageDraw, ImageOps
from concurrent.futures import ProcessPoolExecutor
import re, sys, math, argparse, shutil

W, H = 3840, 2160
FONTS = {}


# Reference helper: font; see recipe prerequisites.
# 参考辅助函数：font；执行前查看参考脚本依赖。
def font(size, bold=False):
    key = (size, bold)
    if key not in FONTS:
        FONTS[key] = ImageFont.truetype(os.environ["WORKBENCH_FONT"], size)
    return FONTS[key]


# Reference helper: wrap; see recipe prerequisites.
# 参考辅助函数：wrap；执行前查看参考脚本依赖。
def wrap(text, size, width, bold=False):
    f = font(size, bold)
    tokens = re.findall(r"[A-Za-z0-9À-ž]+(?:[\-’\'][A-Za-z0-9À-ž]+)*|\s+|.", text)
    lines = []
    line = ""
    for t in tokens:
        if "\n" in t:
            lines.append(line.strip())
            line = ""
            continue
        if f.getlength(line + t) > width and line.strip():
            if re.match(r"^[，。！？；：、,.!?;:]$", t):
                match = re.search(r"([A-Za-z0-9À-ž]+|.)$", line.rstrip())
                tail = match.group(0)
                lines.append(line.rstrip()[: -len(tail)].rstrip())
                line = tail + t
            else:
                lines.append(line.rstrip())
                line = t.lstrip()
        else:
            line += t
    if line.strip():
        lines.append(line.rstrip())
    return lines or [""]


# Reference helper: block; see recipe prerequisites.
# 参考辅助函数：block；执行前查看参考脚本依赖。
def block(c):
    foreign = c["language"] in ("English", "German") and not c.get("unresolved")
    original = wrap(c["original"], 64, 2440) if foreign else []
    zh = wrap(c["zh"], 60, 2440)
    if c.get("unresolved"):
        original = []
    height = 58 + len(original) * 82 + (14 if original else 0) + len(zh) * 80 + 34
    return dict(cue=c, original_lines=original, zh_lines=zh, height=height)


LANG = {"English": "英语原声", "German": "德语原声", "Cantonese": "粤语原声 · 普通话字幕", "Chinese": "普通话／混合语"}


# Reference helper: draw lines; see recipe prerequisites.
# 参考辅助函数：draw lines；执行前查看参考脚本依赖。
def draw_lines(draw, lines, x, y, size, fill, line_height, bold=False):
    for line in lines:
        draw.text((x, y), line, font=font(size, bold), fill=fill)
        y += line_height
    return y


# Reference helper: render one; see recipe prerequisites.
# 参考辅助函数：render one；执行前查看参考脚本依赖。
def render_one(job):
    path = Path(job["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return dict(path=str(path), cached=True, blocks=len(job["blocks"]))
    im = Image.new("RGB", (W, H), "black")
    draw = ImageDraw.Draw(im)
    title = f"{job['code']}  |  {job['name']}  ·  原声学习"
    draw.text((144, 70), title, font=font(67, True), fill="white")
    draw.text((2840, 84), "4K  ·  原音轨保留", font=font(44), fill="#dddddd")
    draw.line((145, 185, 3695, 185), fill="#555555", width=2)
    y = 260
    boxes = []
    if not job["blocks"]:
        draw_lines(draw, ["原录音播放中", "此处尚无可靠文字，保留原声供回听。"], 180, 430, 64, "white", 108)
        draw_lines(
            draw,
            ["新对话在下方出现，之前的对话向上保留。", "英语／德语配中文，粤语只转换字幕。"],
            180,
            850,
            54,
            "#dddddd",
            88,
        )
    for i, b in enumerate(job["blocks"]):
        c = b["cue"]
        active = i == len(job["blocks"]) - 1 and not job.get("idle")
        textfill = "#ffffff" if active else "#dedede"
        if active:
            draw.rectangle((145, y - 18, 2710, y + b["height"] - 8), outline="#f1f1f1", width=3)
            draw.rectangle((146, y - 18, 156, y + b["height"] - 8), fill="white")
        speaker = c["speaker"].replace("-S?", "-声音待分组")
        label = f"{tc(c['start'])}   {speaker}   {LANG.get(c['language'], c['language'])}"
        if c.get("review_note"):
            label += "   词句待核"
        if active:
            label += "   当前"
        draw.text((185, y), label, font=font(40, active), fill=textfill)
        y += 58
        if b["original_lines"]:
            y = draw_lines(draw, b["original_lines"], 185, y, 64, textfill, 82)
            y += 14
        y = draw_lines(draw, b["zh_lines"], 185, y, 60, textfill, 80)
        boxes.append(dict(cue=c["id"], bottom=y, lines=len(b["original_lines"]) + len(b["zh_lines"])))
        y += 34
    assert y < 2010, (job["time"], y)
    draw.line((2780, 258, 2780, 1970), fill="#3b3b3b", width=2)
    sx = 2840
    sy = 270
    sw = 840
    image_ref = job.get("image")
    if image_ref:
        source = Image.open(ASSETS / image_ref["file"]).convert("RGB")
        # A tall source table is shown as a clearly labelled top detail, not unreadable full-page miniature.
        cropped = False
        if source.height > source.width * 1.25:
            source = source.crop((0, 0, source.width, min(source.height, int(source.width * 0.95))))
            cropped = True
        source.thumbnail((sw, 700), Image.Resampling.LANCZOS)
        im.paste(source, (sx + (sw - source.width) // 2, sy))
        sy += source.height + 22
        caption = image_ref["caption"] + ("（局部）" if cropped else "")
        sy = draw_lines(draw, wrap(caption, 38, sw), sx, sy, 38, "#e4e4e4", 54) + 42
    if job.get("terms"):
        draw.text((sx, sy), "术语解释", font=font(45, True), fill="white")
        sy += 72
        for t in job["terms"][: 2 if image_ref else 3]:
            lines = wrap(t["term"], 43, sw, True)
            body = wrap(t["explanation"], 42, sw)
            required = len(lines) * 58 + len(body) * 59 + 36
            if sy + required > 1740:
                break
            sy = draw_lines(draw, lines, sx, sy, 43, "white", 58, True)
            sy = draw_lines(draw, body, sx, sy + 6, 42, "#eeeeee", 59) + 36
    if job.get("note"):
        sy = max(sy + 12, 1750)
        draw_lines(draw, wrap("听辨提示：" + job["note"], 36, sw)[:4], sx, sy, 36, "#dddddd", 49)
    draw.line((145, 2018, 3695, 2018), fill="#444444", width=2)
    footer = f"音源 {job['code']}  ·  对话位置 {tc(job['time'])}   |   原声不剪切、不变速、不降噪"
    if job.get("idle"):
        footer += "   |   原声继续，历史对话保留"
    draw.text((145, 2053), footer, font=font(39), fill="#d8d8d8")
    im.save(path, compress_level=1)
    return dict(path=str(path), blocks=len(job["blocks"]), boxes=boxes, sidebar_bottom=sy)


# Reference helper: build jobs; see recipe prerequisites.
# 参考辅助函数：build jobs；执行前查看参考脚本依赖。
def build_jobs(code, cues, duration, out, begin=0, end=None):
    end = min(end or duration, duration)
    jobs = []
    history = []
    units = {u["id"]: u for u in read(ROOT / "work" / code / "working_units.json")["units"]}
    events = [(begin, None, False)]
    for i, c in enumerate(cues):
        if c["start"] < begin:
            continue
        if c["start"] >= end:
            break
        events.append((c["start"], c, False))
        nxt = cues[i + 1]["start"] if i + 1 < len(cues) else end
        if nxt - c["end"] > 9 and c["end"] + 3 < end:
            events.append((c["end"] + 3, None, True))
    if end - begin > 0.1:
        events.append((math.floor((end - 0.04) * 25) / 25, None, True))
    events.sort(key=lambda x: x[0])
    for t, c, idle in events:
        if c:
            b = block(c)
            if b["height"] > 1690:
                raise RuntimeError(f"Overlong cue {c['id']}: {b['height']}")
            history.append(b)
            while sum(x["height"] for x in history) > 1700:
                history.pop(0)
        context = (
            units[c["unit"]]["original"] if c else (units[history[-1]["cue"]["unit"]]["original"] if history else "")
        )
        terms = selected_terms(context)
        picture = selected_image(code, t, context)
        active = history[-1]["cue"] if history else None
        job = dict(
            code=code,
            name=SOURCES[code]["name"],
            time=t - begin,
            source_time=t,
            blocks=list(history),
            idle=idle,
            image=picture,
            terms=terms,
            note=active.get("review_note", "") if active else "",
            path=str(out / f"{len(jobs):06}.png"),
        )
        if jobs and abs(t - begin - jobs[-1]["time"]) < 0.03:
            jobs[-1] = job
            job["path"] = str(out / f"{len(jobs) - 1:06}.png")
        else:
            jobs.append(job)
    for i, j in enumerate(jobs):
        j["duration"] = round((jobs[i + 1]["time"] if i + 1 < len(jobs) else end - begin) - j["time"], 3)
    return jobs


# Reference helper: build; see recipe prerequisites.
# 参考辅助函数：build；执行前查看参考脚本依赖。
def build(code, sample=False):
    d = SOURCES[code]
    folder = ROOT / "work" / code
    data = read(folder / ("cues_sample_reviewed.json" if sample else "cues_reviewed.json"))
    cues = data["cues"]
    duration = float(probe(d["file"])["format"]["duration"])
    end = 180 if sample else duration
    revision = hashlib.sha256(("renderer-v3" + json.dumps(cues, ensure_ascii=False)).encode()).hexdigest()[:8]
    out = folder / (("frames_sample_" if sample else "frames_") + revision)
    out.mkdir(exist_ok=True)
    jobs = build_jobs(code, cues, duration, out, end=end)
    save(folder / ("layout_sample.json" if sample else "layout.json"), jobs)
    with ProcessPoolExecutor(max_workers=8) as pool:
        checks = list(pool.map(render_one, jobs, chunksize=6))
    save(
        ROOT / "核验" / f"{code}_{'样片' if sample else '全片'}_画面布局.json",
        dict(frames=len(jobs), checks=checks, passed=True),
    )
    concat = ["ffconcat version 1.0"]
    encoded_frames = 0
    for j in jobs:
        # Refresh unchanged images at least once per second for responsive seeking.
        remaining = j["duration"]
        while remaining > 0.001:
            hold = min(1.0, remaining)
            concat.extend(
                [
                    "file '" + Path(j["path"]).as_posix().replace("'", "'\\''") + "'",
                    "option framerate 25",
                    f"duration {hold:.3f}",
                ]
            )
            remaining -= hold
            encoded_frames += 1
    concat.extend(["file '" + Path(jobs[-1]["path"]).as_posix() + "'", "option framerate 25"])
    listing = folder / ("sample.ffconcat" if sample else "full.ffconcat")
    listing.write_text("\n".join(concat) + "\n", encoding="utf8")
    output = ROOT / ("样片" if sample else "视频") / f"{code}_{d['name']}_4K原声学习{'_样片' if sample else ''}.mkv"
    output.parent.mkdir(exist_ok=True)
    assert not output.exists(), f"Preserving existing video: {output}"
    if not sample:
        assert not video_path(code).exists(), f"Preserving final video: {video_path(code)}"
    video = folder / (("sample_silent_" if sample else "full_silent_") + revision + ".mkv")
    if video.exists() and video.stat().st_size < 1024:
        video.rename(video.with_suffix(".failed_" + str(int(time.time())) + ".mkv"))
    if not video.exists():
        cmd = [
            FFMPEG,
            "-hide_banner",
            "-v",
            "warning",
            "-nostdin",
            "-n",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-an",
            "-fps_mode",
            "vfr",
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p5",
            "-tune",
            "hq",
            "-rc",
            "vbr",
            "-cq",
            "18",
            "-b:v",
            "0",
            "-g",
            "60",
            "-bf",
            "0",
            "-force_key_frames",
            "expr:gte(t,n_forced*2)",
            "-forced-idr",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-t",
            str(end),
            str(video),
        ]
        with (folder / ("sample_encode.log" if sample else "encode.log")).open("w", encoding="utf8") as lf:
            subprocess.run(cmd, stdout=lf, stderr=lf, check=True)
    cmd = [
        FFMPEG,
        "-hide_banner",
        "-v",
        "warning",
        "-nostdin",
        "-n",
        "-i",
        str(video),
        "-i",
        str(d["file"]),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c",
        "copy",
        "-map_metadata",
        "-1",
        "-metadata",
        "title=" + f"{code} {d['name']} 原声学习",
        "-metadata:s:a:0",
        "title=原始录音（流复制）",
    ]
    if sample:
        cmd += ["-t", str(end)]
    cmd += [str(output)]
    subprocess.run(cmd, check=True)
    save(
        ROOT / "核验" / f"{code}_{'样片' if sample else '全片'}_封装.json",
        dict(
            output=str(output),
            audio_codec="copy",
            cue_sha256=sha(folder / ("cues_sample_reviewed.json" if sample else "cues_reviewed.json")),
            renderer="v3",
            revision=revision,
            frames=len(jobs),
            duration=end,
            probe=probe(output),
        ),
    )
    log("render_complete", code=code, sample=sample, path=str(output), frames=len(jobs))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("code")
    p.add_argument("--sample", action="store_true")
    a = p.parse_args()
    build(a.code, a.sample)
