"""Explicit ModelScope download; inference does not call this script.
明确的ModelScope模型下载；推理不会调用此脚本。
"""

import argparse
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cache", type=Path, required=True)
    args = p.parse_args()
    from modelscope.hub.snapshot_download import snapshot_download

    models = [
        ("iic/speech_campplus_sv_zh_en_16k-common_advanced", "v1.0.0"),
        ("iic/speech_fsmn_vad_zh-cn-16k-common-pytorch", "v2.0.4"),
    ]
    rows = []
    for model, revision in models:
        dest = Path(snapshot_download(model, revision=revision, cache_dir=str(args.cache.resolve())))
        if not (dest / "configuration.json").is_file():
            raise RuntimeError("Downloaded speaker model has no configuration.json")
        rows.append(
            dict(
                model=model,
                revision=revision,
                configuration_sha256=hashlib.sha256((dest / "configuration.json").read_bytes()).hexdigest(),
            )
        )
    args.cache.mkdir(parents=True, exist_ok=True)
    (args.cache / "download_inventory.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf8")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
