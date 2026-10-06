"""Original-size frame extraction, OCR and local visual interpretation.
原尺寸抽帧、OCR及本地画面理解。
"""

from __future__ import annotations
from pathlib import Path
import math

from .core import cached, command, fingerprint, offline_environment, probe, read_json, save_json, sha256


def frames(source, output, config, interval=1.0, ocr=False):
    """Decode every frame, keep scene/interval candidates, and optionally OCR each kept PNG.
    逐帧解码，保留场景与间隔候选，可对保留的PNG执行OCR。
    """
    import cv2
    import numpy as np
    from PIL import Image

    if interval <= 0:
        raise ValueError("interval must be positive")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = Path(source).resolve()
    key = fingerprint(sha256(source), "frames", dict(config, interval=interval, ocr=ocr))
    previous = cached(output / "frames.json", key)
    if previous and all(
        (output / r["file"]).exists() and sha256(output / r["file"]) == r["sha256"] for r in previous["frames"]
    ):
        return previous
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError("Cannot open video / 无法打开视频")
    engine = None
    if ocr:
        from rapidocr_onnxruntime import RapidOCR

        engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1, text_score=0.45)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not math.isfinite(fps) or fps <= 0:
        cap.release()
        raise RuntimeError("Invalid frame rate / 帧率无效")
    rows = []
    last_small = None
    last_keep = -interval
    prev_small = None
    index = 0
    try:
        while True:
            ok, image = cap.read()
            if not ok:
                break
            t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            if not math.isfinite(t) or (index > 0 and t <= 0):
                t = index / fps
            small = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (320, 180))
            delta = (
                float(np.abs(small.astype(np.int16) - prev_small.astype(np.int16)).mean())
                if prev_small is not None
                else 255
            )
            scene = delta > 20.4
            # Small menu/text changes matter even when most of the screen stays unchanged.
            # 菜单或文字的局部变化同样重要，不能因大部分画面相同而丢掉。
            difference = None if last_small is None else np.abs(small.astype(np.int16) - last_small.astype(np.int16))
            different = (
                difference is None or float(difference.mean()) >= 3.5 or float((difference > 12).mean()) >= 0.003
            )
            if index == 0 or scene or (t - last_keep >= interval and different) or t - last_keep >= 10:
                # PNG avoids adding JPEG artifacts to screen text.
                # PNG避免给屏幕文字增加JPEG压缩伪影。
                name = f"frame_{len(rows):06}_{t:010.3f}.png"
                path = output / name
                Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).save(path)
                row = dict(
                    id=f"F{len(rows) + 1:05}",
                    timestamp=round(t, 3),
                    file=name,
                    width=image.shape[1],
                    height=image.shape[0],
                    sha256=sha256(path),
                )
                if engine:
                    boxes, _ = engine(str(path))
                    row["ocr"] = [dict(box=box, text=text, confidence=float(score)) for box, text, score in boxes or []]
                rows.append(row)
                last_small = small.copy()
                last_keep = t
            prev_small = small
            index += 1
    finally:
        cap.release()
    if not rows:
        raise RuntimeError("Video decoded zero frames / 视频未解码出画面")
    result = dict(
        status="complete",
        fingerprint=key,
        frames=rows,
        decoded_frames=index,
        source_sha256=sha256(source),
        review_status="machine_text_requires_review",
        sampling="all-frame scene changes + interval candidates; near-duplicate suppression",
    )
    save_json(output / "frames.json", result)
    return result


def tiles(image, image_size=448, max_tiles=4):
    """Approximate the original aspect ratio with bounded tiles and a context thumbnail.
    以有界切片及全局缩略图近似保留原图宽高关系。
    """
    ratios = {(i, j) for i in range(1, max_tiles + 1) for j in range(1, max_tiles + 1) if i * j <= max_tiles}
    target = min(sorted(ratios), key=lambda r: abs(image.width / image.height - r[0] / r[1]))
    resized = image.resize((target[0] * image_size, target[1] * image_size))
    result = [
        resized.crop((x * image_size, y * image_size, (x + 1) * image_size, (y + 1) * image_size))
        for y in range(target[1])
        for x in range(target[0])
    ]
    if len(result) > 1:
        result.append(image.resize((image_size, image_size)))
    return result


def understand(manifest, config):
    """Describe visible evidence with a local model; unseen actions remain unknown.
    用本地模型描述可见画面，不猜未展示的操作。
    """
    import torch
    import torchvision.transforms as T
    from PIL import Image
    from transformers import AutoModel, AutoTokenizer

    offline_environment(config)
    manifest = Path(manifest).resolve()
    data = read_json(manifest)
    key = fingerprint(sha256(manifest), "vision", config)
    dest = manifest.parent / "vision.json"
    previous = cached(dest, key)
    if previous:
        return previous
    path = config["models"]["vision"]
    # Custom local model code must be inspected before enabling trust_remote_code.
    # 启用trust_remote_code前须检查本地模型的自定义代码。
    tokenizer = AutoTokenizer.from_pretrained(path, trust_remote_code=True, local_files_only=True, use_fast=False)
    model = (
        AutoModel.from_pretrained(
            path, trust_remote_code=True, local_files_only=True, torch_dtype=torch.bfloat16, use_flash_attn=False
        )
        .to(config["device"])
        .eval()
    )
    transform = T.Compose(
        [T.Resize((448, 448)), T.ToTensor(), T.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225))]
    )
    prompt = "Describe visible application, controls, fields, state and errors. Do not infer unseen clicks, credentials or next pages. Mark uncertainty."
    rows = []
    for r in data["frames"]:
        with Image.open(manifest.parent / r["file"]) as im:
            pixels = torch.stack([transform(t) for t in tiles(im.convert("RGB"))]).to(
                device=config["device"], dtype=torch.bfloat16
            )
        with torch.inference_mode():
            answer = model.chat(tokenizer, pixels, prompt, {"max_new_tokens": 256, "do_sample": False})
        rows.append(dict(id=r["id"], timestamp=r["timestamp"], description=answer, review_status="pending"))
    result = dict(status="complete", fingerprint=key, frames=rows)
    save_json(dest, result)
    return result
