"""Command-line entry points with optional dependencies loaded per stage.
按阶段加载可选依赖的命令行入口。
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from .core import doctor, load_config


def parser():
    p = argparse.ArgumentParser(
        prog="media-workbench", description="Local multilingual media processing / 本地多语种媒体处理"
    )
    p.add_argument("--config", type=Path, help="JSON configuration / JSON配置文件")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Inspect dependencies and local models / 检查依赖与本地模型")
    run = commands.add_parser("run", help="Dual ASR + diarization + comparison / 双路识别与说话人对照")
    run.add_argument("--input", required=True, type=Path)
    run.add_argument("--output", required=True, type=Path)
    run.add_argument(
        "--stages",
        nargs="+",
        choices=["whisper", "qwen", "diar", "fuse", "align", "export"],
        default=["whisper", "qwen", "diar", "fuse", "export"],
    )
    frames = commands.add_parser("frames", help="Extract frames and optional OCR / 抽帧及可选OCR")
    frames.add_argument("--input", required=True, type=Path)
    frames.add_argument("--output", required=True, type=Path)
    frames.add_argument("--interval", type=float, default=1)
    frames.add_argument("--ocr", action="store_true")
    vision = commands.add_parser("vision", help="Interpret local frames / 本地识图")
    vision.add_argument("--frames", required=True, type=Path)
    tr = commands.add_parser("translate", help="Translate via loopback model server / 本机模型翻译")
    tr.add_argument("--input", required=True, type=Path)
    tr.add_argument("--output", required=True, type=Path)
    study = commands.add_parser("study-video", help="4K original-audio study video / 4K原声学习视频")
    study.add_argument("--input", required=True, type=Path)
    study.add_argument("--cues", required=True, type=Path)
    study.add_argument("--output", required=True, type=Path)
    study.add_argument("--font", required=True, type=Path)
    study.add_argument("--assets", type=Path)
    study.add_argument("--codec", choices=["libx264", "h264_nvenc"], default="libx264")
    docs = commands.add_parser("documents", help="Create Word/PPT/Markdown / 生成Word、PPT与MD")
    docs.add_argument("--content", required=True, type=Path)
    docs.add_argument("--output", required=True, type=Path)
    down = commands.add_parser("download", help="Best available video + audio / 最高可用视频及音频")
    down.add_argument("url")
    down.add_argument("--output", required=True, type=Path)
    return p


def main(argv=None):
    # UTF-8 output keeps bilingual text intact when piped on Windows.
    # UTF-8输出使Windows管道中的中英文字保持完整。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf8")
    args = parser().parse_args(argv)
    config = load_config(args.config)
    try:
        if args.command == "doctor":
            result = doctor(config)
        elif args.command == "run":
            from .asr import run

            result = run(args.input, args.output, config, args.stages)
        elif args.command == "frames":
            from .vision import frames

            result = frames(args.input, args.output, config, args.interval, args.ocr)
        elif args.command == "vision":
            from .vision import understand

            result = understand(args.frames, config)
        elif args.command == "translate":
            from .translation import translate

            result = translate(args.input, args.output, config)
        elif args.command == "study-video":
            from .learning_video import render

            result = render(args.input, args.cues, args.output, args.font, config, args.assets, args.codec)
        elif args.command == "documents":
            from .documents import build

            result = build(args.content, args.output)
        elif args.command == "download":
            import yt_dlp

            args.output.mkdir(parents=True, exist_ok=True)
            # Merge best streams without re-encoding; never import browser cookies.
            # 合并最高质量流而不重编码，不自动导入浏览器cookie。
            with yt_dlp.YoutubeDL(
                dict(
                    format="bestvideo+bestaudio/best",
                    merge_output_format="mkv",
                    noplaylist=True,
                    retries=2,
                    fragment_retries=2,
                    outtmpl=str(args.output / "%(id)s.%(ext)s"),
                    ffmpeg_location=config["ffmpeg"] if config["ffmpeg"] != "ffmpeg" else None,
                )
            ) as ydl:
                ydl.download([args.url])
            result = {"download": "complete", "quality": "best available streams"}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
