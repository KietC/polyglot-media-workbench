# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
# REVIEW SNAPSHOT: redacted task data; see source provenance and audit.
from common import *
import re
from PIL import Image, ImageDraw, ImageFont, ImageOps

ASSETS = ROOT / "assets"
TERMS = []
IMAGES = []


# Reference helper: selected terms; see recipe prerequisites.
# 参考辅助函数：selected terms；执行前查看参考脚本依赖。
def selected_terms(text):
    return [dict(term=k, explanation=v) for k, p, v in TERMS if re.search(p, text, re.I)][:3]


# Reference helper: selected image; see recipe prerequisites.
# 参考辅助函数：selected image；执行前查看参考脚本依赖。
def selected_image(code, start, text):
    for r in IMAGES:
        if r["source"] not in (None, code) or not r["start"] <= start < r["end"]:
            continue
        if r["pattern"] is None or re.search(r["pattern"], text, re.I):
            return r
    return None


# Reference helper: prepare; see recipe prerequisites.
# 参考辅助函数：prepare；执行前查看参考脚本依赖。
def prepare():
    if not IMAGES:
        raise RuntimeError("Configure local image mappings before preparing assets.")
    target = ROOT / "资料"
    target.mkdir(exist_ok=True)
    save(
        target / "术语与配图索引.json",
        dict(terms=[dict(term=k, pattern=p, explanation=v) for k, p, v in TERMS], images=IMAGES),
    )
    text = ["# 学习术语表", "", "以下是理解录音的旁注，不是新增会议原话。", ""]
    for k, p, v in TERMS:
        text.extend([f"## {k}", v, ""])
    (target / "术语表.md").write_text("\n".join(text), encoding="utf8")
    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 24)
    sheet = Image.new("RGB", (1500, math.ceil(len(IMAGES) / 3) * 420), "#202020")
    draw = ImageDraw.Draw(sheet)
    for i, r in enumerate(IMAGES):
        im = Image.open(ASSETS / r["file"]).convert("RGB")
        im.thumbnail((470, 345))
        x = (i % 3) * 500 + (500 - im.width) // 2
        y = (i // 3) * 420
        sheet.paste(im, (x, y))
        draw.text(((i % 3) * 500 + 15, y + 352), r["file"], font=font, fill="white")
    sheet.save(ROOT / "核验/资料配图总览.jpg", quality=88)


if __name__ == "__main__":
    import math

    prepare()
