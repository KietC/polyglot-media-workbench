"""4K rolling conversation cards with copied original audio.
复制原声音轨的4K滚动对话卡片。
"""

from __future__ import annotations
from collections import deque
from pathlib import Path
import hashlib
import json
import math
import shutil
import tempfile

from .core import command, probe, read_json, save_json, sha256, timestamp


def wrap(text, font, width):
    """Wrap by measured glyph width so Latin and CJK text share the same layout rules.
    按实际字形宽度换行，使拉丁文字和中文采用同一排版规则。
    """
    lines = []
    line = ""
    for ch in text:
        if ch == "\n":
            lines.append(line)
            line = ""
        elif line and font.getlength(line + ch) > width:
            lines.append(line)
            line = ch
        else:
            line += ch
    if line:
        lines.append(line)
    return lines


def render(source, cues_file, output, font_path, config, assets=None, codec="libx264"):
    """Render rolling caption cards; copy audio and verify packets, PCM and video span.
    渲染滚动对话卡片；复制音轨并校验数据包、PCM及视频覆盖时长。
    """
    from PIL import Image, ImageDraw, ImageFont

    source = Path(source).resolve()
    output = Path(output).resolve()
    if output == source or output.exists():
        raise FileExistsError("Choose a new output video / 请选用新的输出文件")
    if output.suffix.lower() not in (".mp4", ".mkv"):
        raise ValueError("Use .mp4 or .mkv")
    cues = read_json(cues_file)["units"]
    duration = float(probe(source, config)["format"]["duration"])
    if not cues:
        raise ValueError("No cues / 字幕为空")
    if any(not math.isfinite(float(u[k])) for u in cues for k in ("start", "end")):
        raise ValueError("Non-finite cue timestamp")
    if any(u["start"] < 0 or u["end"] < u["start"] or u["start"] >= duration for u in cues):
        raise ValueError("Cue time outside source duration / 字幕时间超出音源")
    cues = sorted(cues, key=lambda u: u["start"])
    original_hash = sha256(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    settings = read_json(assets) if assets else {"terms": [], "images": []}
    asset_base = Path(assets).resolve().parent if assets else Path.cwd()
    normal = ImageFont.truetype(str(font_path), 66)
    small = ImageFont.truetype(str(font_path), 48)
    history = deque()
    asset_times = [float(r[k]) for r in settings.get("images", []) for k in ("start", "end")]
    times = sorted(
        set([0.0, duration] + [float(u["start"]) for u in cues] + [t for t in asset_times if 0 < t < duration])
    )
    # Render one card per change; FFmpeg holds it until the next event.
    # 每次变化只渲染一张卡片，FFmpeg保持该画面直到下一事件。
    with tempfile.TemporaryDirectory(prefix="media-study-") as temp:
        temp = Path(temp)
        concat = []
        position = 0
        for i, t in enumerate(times[:-1]):
            while position < len(cues) and cues[position]["start"] <= t:
                u = cues[position]
                history.append(u)
                position += 1
            cards = []
            for u in history:
                text = u["original"]
                if u["language"] in ("English", "German") and u.get("zh"):
                    text += "\n" + u["zh"]
                elif u["language"] in ("Cantonese", "Chinese") and u.get("zh"):
                    text = u["zh"]
                cards.append((u, wrap(text, normal, 2550)))
            while len(cards) > 1 and sum(95 + len(lines) * 84 for _, lines in cards) > 1780:
                history.popleft()
                cards.pop(0)
            if any(95 + len(lines) * 84 > 1780 for _, lines in cards):
                raise ValueError(
                    "A cue is too long; split at sentence/word timestamps / 单段过长，请按句子或词时间拆分"
                )
            image = Image.new("RGB", (3840, 2160), "black")
            draw = ImageDraw.Draw(image)
            draw.text((80, 35), f"Original-audio study / 原声学习 · {timestamp(t)}", font=small, fill="#AAAAAA")
            y = 2050 - sum(95 + len(lines) * 84 for _, lines in cards)
            for j, (u, lines) in enumerate(cards):
                color = "white" if j == len(cards) - 1 else "#BBBBBB"
                draw.text(
                    (80, y),
                    f"{u.get('speaker', 'SPEAKER_UNKNOWN')} · {timestamp(u['start'])}",
                    font=small,
                    fill="#7CD6FF",
                )
                y += 68
                for line in lines:
                    draw.text((80, y), line, font=normal, fill=color)
                    y += 84
                y += 27
            if cards:
                current = cards[-1][0]
                sidebar_y = 210
                for term in settings.get("terms", []):
                    if term["term"].casefold() in current["original"].casefold():
                        for line in wrap(term["term"] + ": " + term["explanation"], small, 940):
                            if sidebar_y + 62 > 2050:
                                raise ValueError("Sidebar term overflow / 术语旁栏溢出")
                            draw.text((2810, sidebar_y), line, font=small, fill="#FFE5A3")
                            sidebar_y += 62
                        sidebar_y += 30
                ref = next((r for r in settings.get("images", []) if r["start"] <= t < r["end"]), None)
                if ref:
                    picture = Image.open(asset_base / ref["file"]).convert("RGB")
                    picture.thumbnail((940, 900))
                    if sidebar_y + picture.height > 2050:
                        raise ValueError("Sidebar image overflow / 配图旁栏溢出")
                    image.paste(picture, (2810, sidebar_y))
            path = temp / f"card_{i:06}.png"
            image.save(path)
            concat += [f"file '{path.as_posix()}'", f"duration {times[i + 1] - t:.6f}"]
        concat += [f"file '{path.as_posix()}'"]
        (temp / "cards.txt").write_text("\n".join(concat) + "\n", encoding="utf8")
        partial = output.with_name(output.stem + ".partial" + output.suffix)
        args = [
            config["ffmpeg"],
            "-v",
            "error",
            "-nostdin",
            "-n",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            temp / "cards.txt",
            "-i",
            source,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            # Resample still-image timestamps and hold the final card through the audio tail.
            # 重采样静态图片时间轴，并将最后一张卡片保持到音频结尾。
            "-vf",
            "fps=25,tpad=stop_mode=clone:stop_duration=1",
            "-fps_mode",
            "cfr",
            "-c:v",
            codec,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-t",
            str(duration),
            "-map_metadata",
            "-1",
        ]
        if output.suffix.lower() == ".mp4":
            args += ["-movflags", "+faststart"]
        args += [partial]
        command(args, config["command_timeout"])
        partial.rename(output)
    # Compare both compressed audio packets and decoded PCM after muxing.
    # 封装完成后同时对照压缩音频包与解码PCM。
    report = verify_audio(source, output, config)
    report["source_unchanged"] = sha256(source) == original_hash
    video = next(s for s in probe(output, config)["streams"] if s["codec_type"] == "video")
    report["dimensions"] = [video["width"], video["height"]]
    report["video_timeline"] = video_timeline(output, config)
    report["expected_duration"] = duration
    report["video_covers_audio"] = abs(report["video_timeline"]["end"] - duration) <= 0.081
    report["passed"] = (
        report["passed"]
        and report["source_unchanged"]
        and report["dimensions"] == [3840, 2160]
        and report["video_covers_audio"]
        and abs(report["video_timeline"]["start"]) <= 0.041
    )
    save_json(output.with_suffix(output.suffix + ".qa.json"), report)
    if not report["passed"]:
        raise RuntimeError(
            "Media check failed; inspect audio priming and video duration / 媒体校验失败，请检查音频预卷和视频时长"
        )
    return report


def video_timeline(path, config):
    """Check the real video packet span, not merely the container duration.
    检查实际视频包覆盖范围，而不仅检查容器总时长。
    """
    rows = json.loads(
        command(
            [
                config["ffprobe"],
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_packets",
                "-show_entries",
                "packet=pts_time,duration_time",
                "-of",
                "json",
                path,
            ],
            config["command_timeout"],
        )
    )["packets"]
    if not rows:
        raise RuntimeError("Video contains no packets / 视频没有数据包")
    start = min(float(r["pts_time"]) for r in rows)
    end = max(float(r["pts_time"]) + float(r.get("duration_time", 0)) for r in rows)
    return dict(start=start, end=end, packets=len(rows))


def audio_signature(path, config):
    """Fingerprint both compressed packets and decoded samples to catch muxing changes.
    同时记录压缩数据包和解码采样指纹，检查封装造成的变化。
    """
    packets = json.loads(
        command(
            [
                config["ffprobe"],
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_packets",
                "-show_data_hash",
                "sha256",
                "-show_entries",
                "packet=size,data_hash",
                "-of",
                "json",
                path,
            ],
            config["command_timeout"],
        )
    )["packets"]
    hashes = [p["data_hash"] for p in packets if "data_hash" in p]
    pcm = command(
        [
            config["ffmpeg"],
            "-v",
            "error",
            "-nostdin",
            "-i",
            path,
            "-map",
            "0:a:0",
            "-c:a",
            "pcm_f32le",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ],
        config["command_timeout"],
    ).strip()
    return dict(packets=len(hashes), packet_hash=hashlib.sha256("\n".join(hashes).encode()).hexdigest(), pcm=pcm)


def verify_audio(source, output, config):
    """Require equal packet count, packet content and decoded audio samples.
    要求数据包数量、数据包内容与解码音频采样均相同。
    """
    a, b = audio_signature(source, config), audio_signature(output, config)
    return dict(original_audio=a, output_audio=b, passed=a == b)
