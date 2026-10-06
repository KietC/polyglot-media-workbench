# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
"""Preserve source ASR, select a conservative original-language working text.

No summary translations are used as sentence translations. Alternatives and
uncertainty remain in an audit JSON instead of being silently discarded.
"""

from common import *
from difflib import SequenceMatcher
from collections import Counter
import re, sys


# Reference helper: norm; see recipe prerequisites.
# 参考辅助函数：norm；执行前查看参考脚本依赖。
def norm(t):
    return re.sub(r"[^\w\u3400-\u9fff]", "", t).lower()


# Reference helper: agreement; see recipe prerequisites.
# 参考辅助函数：agreement；执行前查看参考脚本依赖。
def agreement(a, b):
    return SequenceMatcher(None, norm(a), norm(b), autojunk=False).ratio()


# Reference helper: language; see recipe prerequisites.
# 参考辅助函数：language；执行前查看参考脚本依赖。
def language(text, fallback):
    if re.search(r"[\u4e00-\u9fff]", text):
        return "Cantonese" if fallback == "Cantonese" else "Chinese"
    if fallback in ("English", "German"):
        return fallback
    if re.search(r"\b(und|nicht|ich|wir|ist|das|mit|auch|haben|für|eine|ein|aber)\b", text, re.I):
        return "German"
    return "English"


# Reference helper: clean; see recipe prerequisites.
# 参考辅助函数：clean；执行前查看参考脚本依赖。
def clean(text):
    return re.sub(r"\s+", " ", text.replace("<|endoftext|>", "")).strip()


# Reference helper: create; see recipe prerequisites.
# 参考辅助函数：create；执行前查看参考脚本依赖。
def create(code):
    d = SOURCES[code]
    folder = ROOT / "work" / code
    q = read(d["old"] / "work/asr/qwen.json")["results"]
    turbo = read(d["old"] / "work/asr/whisper.json")["segments"]
    full = read(folder / "full_whisper.json")["segments"]
    prior = {}
    p = d["old"] / ("核验/逐段编校与对齐_B.json" if code == "B" else "核验/逐段编校与对齐.json")
    if p.exists():
        prior = {int(x["start"]): x for x in read(p)["units"]}
    units = []
    for i, row in enumerate(q):
        s, e = row["start"], row["end"]
        lang = row.get("language", "")

        # Reference helper: in window; see recipe prerequisites.
        # 参考辅助函数：in window；执行前查看参考脚本依赖。
        def in_window(x):
            return s <= (x["start"] + min(x["end"], x["start"] + 4)) / 2 < e

        fs = [x for x in full if in_window(x)]
        ts = [x for x in turbo if in_window(x)]
        ftext = clean(" ".join(x["text"] for x in fs))
        ttext = clean(" ".join(x["text"] for x in ts))
        qt = clean(row["text"])
        score = max(agreement(qt, ftext), agreement(qt, ttext))
        selected = qt
        method = "qwen"
        note = ""
        old = prior.get(int(s), {})
        # Documented edits are only accepted where they preserve the recognized words.
        oldtext = old.get("original", "")
        if oldtext and agreement(qt, oldtext) > 0.93 and not re.search(r"\[|［|〔|候选|待核", oldtext):
            selected = clean(oldtext)
            method = "qwen_documented_minor_edits"
        if oldtext and len(norm(qt)) < 8 and len(norm(oldtext)) > len(norm(qt)) * 3 and "[随后" in oldtext:
            selected = clean(re.sub(r"\[[^\]]*\]|［[^］]*］", "", oldtext))
            method = "prior_short_clip_verified_recovery"
            lang = language(selected, "English")
        if not norm(qt):
            stable = [
                x
                for x in fs
                if x.get("avg_logprob", -5) > -0.8
                and x.get("no_speech_prob", 1) < 0.6
                and x.get("compression_ratio", 9) < 2.4
            ]
            selected = clean(" ".join(x["text"] for x in stable))
            method = "full_whisper_gap_recovery"
            if selected:
                note = "主识别空白，依据另一识别结果补回，需结合原声。"
        if selected and score < 0.30:
            note = "低声、重叠或识别分歧；字幕有待核词句，以原声为准。"
        if len(norm(selected)) < 2:
            selected = ""
        if (
            re.search(
                r"(字幕由|字幕提供|Amara.org|请不吝|点赞订阅|Thank you for watching|Thanks for watching)",
                selected,
                re.I,
            )
            and score < 0.3
        ):
            note = "疑似背景幻听，未作为确定台词。"
            selected = ""
        units.append(
            dict(
                id=f"{code}-U{i + 1:04}",
                source=code,
                start=s,
                end=e,
                language=language(selected, lang),
                original=selected,
                method=method,
                agreement=round(score, 3),
                review_note=note,
                old_note=old.get("note", ""),
                qwen=qt,
                full_whisper=ftext,
                turbo=ttext,
            )
        )
    save(folder / "working_units.json", dict(status="working_text_not_human_verbatim_certified", units=units))
    save(ROOT / "核验" / f"{code}_识别选择与分歧.json", dict(units=units))
    for x in units[:8]:
        print(code, x["id"], x["language"], x["agreement"], x["original"])
    print(
        code,
        "units",
        len(units),
        "uncertain",
        sum(bool(x["review_note"]) for x in units),
        "chars",
        sum(len(x["original"]) for x in units),
    )


if __name__ == "__main__":
    for code in sys.argv[1] if len(sys.argv) > 1 else "ABC":
        create(code)
