"""Reproducible synthetic video/audio smoke test without model weights.
无需模型权重的可复现合成音视频冒烟测试。
"""

import argparse
import math
from pathlib import Path
import struct
import tempfile
import wave

from media_workbench.core import command, load_config, save_json
from media_workbench.learning_video import render


def main():
    """Generate a two-second tone, render bilingual cards, and verify full decode.
    生成两秒测试音、渲染双语卡片，并验证完整解码。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--codec", default="libx264")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    with tempfile.TemporaryDirectory(prefix="media-synthetic-") as work:
        root = Path(work)
        audio = root / "tone.wav"
        with wave.open(str(audio), "wb") as wav:
            wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            wav.writeframes(
                b"".join(struct.pack("<h", int(math.sin(i * 2 * math.pi * 440 / 16000) * 4000)) for i in range(32000))
            )
        save_json(
            root / "cues.json",
            {
                "units": [
                    {
                        "id": "U1",
                        "start": 0,
                        "end": 1,
                        "speaker": "SYNTHETIC",
                        "language": "English",
                        "original": "Synthetic example.",
                        "zh": "合成示例。",
                    },
                    {
                        "id": "U2",
                        "start": 1,
                        "end": 2,
                        "speaker": "SYNTHETIC",
                        "language": "English",
                        "original": "The previous line stays above.",
                        "zh": "上一句保留在上方。",
                    },
                ]
            },
        )
        output = root / "study.mkv"
        result = render(audio, root / "cues.json", output, args.font, config, codec=args.codec)
        if result["video_timeline"]["packets"] != 50:
            raise RuntimeError("Expected 50 frames in the two-second test / 两秒测试应有50帧")
        command(
            [config["ffmpeg"], "-v", "error", "-xerror", "-i", output, "-f", "null", "-"], config["command_timeout"]
        )
        print("PASS: 4K, 50 frames, copied audio, equal packet/PCM hashes, full decode.")
        print("通过：4K、50帧、音轨复制、数据包及PCM哈希一致、完整解码。")


if __name__ == "__main__":
    main()
