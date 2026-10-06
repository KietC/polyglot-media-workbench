# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
from common import *
from difflib import SequenceMatcher
from collections import Counter
import re, sys, math


# Reference helper: n; see recipe prerequisites.
# 参考辅助函数：n；执行前查看参考脚本依赖。
def n(t):
    return "".join(c.lower() for c in t if c.isalnum())


# Reference helper: choose speaker; see recipe prerequisites.
# 参考辅助函数：choose speaker；执行前查看参考脚本依赖。
def choose_speaker(s, e, diar, code):
    score = Counter()
    for d in diar:
        overlap = min(e, d["end"]) - max(s, d["start"])
        if overlap > 0:
            score[d["speaker"]] += overlap
    if not score:
        return code + "-S?"
    name, top = score.most_common(1)[0]
    return code + "-" + name.replace("SPEAKER_", "S")


# Reference helper: attach punctuation; see recipe prerequisites.
# 参考辅助函数：attach punctuation；执行前查看参考脚本依赖。
def attach_punctuation(text, words):
    chars = []
    indices = []
    for i, c in enumerate(text):
        if c.isalnum():
            chars.append(c.lower())
            indices.append(i)
    normalized = "".join(chars)
    pos = 0
    bounds = []
    for w in words:
        target = n(w["word"])
        k = normalized.find(target, pos)
        if k < 0 or not target:
            bounds.append(None)
            continue
        bounds.append((indices[k], indices[k + len(target) - 1] + 1))
        pos = k + len(target)
    for i, w in enumerate(words):
        b = bounds[i]
        if b:
            nxt = next((z[0] for z in bounds[i + 1 :] if z is not None), len(text))
            w["display"] = text[b[0] : nxt]
        else:
            w["display"] = w["word"] + (" " if not re.search(r"[\u4e00-\u9fff]", w["word"]) else "")
    return words


# Reference helper: timing; see recipe prerequisites.
# 参考辅助函数：timing；执行前查看参考脚本依赖。
def timing(unit, full):
    words = [dict(w) for w in unit["words"]]
    if not words:
        return words
    fw = [
        w
        for seg in full
        for w in seg.get("words", [])
        if unit["start"] <= (w["start"] + w["end"]) / 2 < unit["end"] and n(w["word"])
    ]
    anchors = {}
    for block in SequenceMatcher(
        None, [n(w["word"]) for w in words], [n(w["word"]) for w in fw], autojunk=False
    ).get_matching_blocks():
        for k in range(block.size):
            index = block.a + k
            candidate = fw[block.b + k]
            if candidate.get("probability", 0) >= 0.5:
                anchors[index] = candidate
    # Reliable common words are time anchors; this particularly repairs zero-time runs.
    for i, w in enumerate(words):
        if i in anchors:
            a = anchors[i]
            w["start"] = max(unit["start"], a["start"])
            w["end"] = min(unit["end"], a["end"])
            w["timing_method"] = "two_model_common_word"
        else:
            w["timing_method"] = "forced_alignment"
    # Make unmatched spans stay between adjacent confirmed anchors. No audio is changed.
    previous = unit["start"]
    for i, w in enumerate(words):
        future = [anchors[j]["start"] for j in anchors if j > i]
        upper = min(unit["end"], min(future) if future else unit["end"])
        w["start"] = max(previous, min(w["start"], upper))
        w["end"] = max(w["start"], min(w["end"], upper))
        previous = w["end"]
    return attach_punctuation(unit["original"], words)


# Reference helper: create; see recipe prerequisites.
# 参考辅助函数：create；执行前查看参考脚本依赖。
def create(code):
    folder = ROOT / "work" / code
    u = read(folder / "aligned_units.json")
    assert u["status"] == "complete"
    diar = read(SOURCES[code]["old"] / "work/asr/diarization.json")["segments"]
    full = read(folder / "full_whisper.json")["segments"]
    cues = []
    audit = []
    for unit in u["units"]:
        words = timing(unit, full)
        groups = []
        group = []
        if (
            words
            and len(n(unit["original"])) > 15
            and max(w["end"] for w in words) - min(w["start"] for w in words) < 0.6
        ):
            cues.append(
                dict(
                    id=f"{code}-{len(cues) + 1:05}",
                    unit=unit["id"],
                    source=code,
                    start=unit["start"],
                    end=unit["end"],
                    speaker=choose_speaker(unit["start"], unit["end"], diar, code),
                    language=unit["language"],
                    original="[低声或重叠，无法可靠辨认]",
                    original_candidate=unit["original"],
                    review_note="时间对齐未通过，未将候选文字当作确定台词。",
                    agreement=unit["agreement"],
                    words=[],
                    unresolved=True,
                )
            )
            audit.append(
                dict(
                    unit=unit["id"],
                    word_count=len(words),
                    zero_spans=sum(w["end"] <= w["start"] for w in words),
                    groups=0,
                    unresolved=True,
                    source_original=unit["original"],
                )
            )
            continue
        for i, w in enumerate(words):
            w["speaker"] = choose_speaker(w["start"], max(w["end"], w["start"] + 0.12), diar, code)
            if group:
                text = "".join(g["display"] for g in group)
                han = len(re.findall(r"[\u4e00-\u9fff]", text))
                limit = 70 if han > len(text) * 0.2 else 190
                elapsed = w["end"] - group[0]["start"]
                stable_change = (
                    w["speaker"] != group[-1]["speaker"]
                    and w["speaker"] != code + "-S?"
                    and i + 1 < len(words)
                    and choose_speaker(
                        words[i + 1]["start"], max(words[i + 1]["end"], words[i + 1]["start"] + 0.12), diar, code
                    )
                    == w["speaker"]
                )
                clause_end = bool(re.search(r'[.!?。！？;；][\s”"\']*$', group[-1]["display"]))
                if (
                    len(text) + len(w["display"]) > limit
                    or (elapsed > 10 and len(text) > 24)
                    or (clause_end and len(text) > 38)
                    or (stable_change and len(text) > 18 and w["start"] - group[0]["start"] > 1.5)
                ):
                    groups.append(group)
                    group = []
            group.append(w)
        if group:
            groups.append(group)
        for g in groups:
            text = "".join(w["display"] for w in g).strip()
            if not text:
                continue
            start = g[0]["start"]
            end = max(g[-1]["end"], start + 0.12)
            end = min(end, unit["end"])
            speaker = choose_speaker(start, end, diar, code)
            note = unit["review_note"]
            if any(k in unit["old_note"] for k in ("待核", "分歧", "不清")):
                note = note or "个别原词仍有听辨分歧。"
            cues.append(
                dict(
                    id=f"{code}-{len(cues) + 1:05}",
                    unit=unit["id"],
                    source=code,
                    start=round(start, 3),
                    end=round(end, 3),
                    speaker=speaker,
                    language=unit["language"],
                    original=text,
                    review_note=note,
                    agreement=unit["agreement"],
                    words=g,
                )
            )
        audit.append(
            dict(
                unit=unit["id"],
                word_count=len(words),
                zero_spans=sum(w["end"] <= w["start"] for w in words),
                groups=len(groups),
                source_original=unit["original"],
            )
        )
    # Consolidate degenerate adjacent timestamps rather than flashing zero-duration captions.
    merged = []
    for c in cues:
        if (
            merged
            and c["start"] <= merged[-1]["start"] + 0.08
            and len(merged[-1]["original"]) + len(c["original"]) < 230
        ):
            merged[-1]["original"] += " " + c["original"]
            merged[-1]["end"] = max(merged[-1]["end"], c["end"])
            merged[-1]["words"] += c["words"]
        else:
            merged.append(c)
    for i, c in enumerate(merged):
        c["id"] = f"{code}-{i + 1:05}"
        if i + 1 < len(merged):
            c["end"] = min(c["end"], merged[i + 1]["start"])
        if c["end"] <= c["start"]:
            c["end"] = c["start"] + 0.04
    save(folder / "cues_original.json", dict(status="ready_for_translation", cues=merged))
    save(
        ROOT / "核验" / f"{code}_对齐审查.json",
        dict(units=audit, cues=len(merged), speaker_counts=dict(Counter(c["speaker"] for c in merged))),
    )
    print(code, len(merged), "cues", sum(len(c["original"]) for c in merged), "chars")
    for c in merged[:12]:
        print(c["id"], c["start"], c["end"], c["speaker"], c["original"])


if __name__ == "__main__":
    for code in sys.argv[1] if len(sys.argv) > 1 else "ABC":
        create(code)
