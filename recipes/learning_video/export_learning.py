# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
from common import *
from collections import Counter
import sys, re


# Reference helper: srtt; see recipe prerequisites.
# 参考辅助函数：srtt；执行前查看参考脚本依赖。
def srtt(s):
    ms = round(s * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


# Reference helper: asst; see recipe prerequisites.
# 参考辅助函数：asst；执行前查看参考脚本依赖。
def asst(s):
    cs = round(s * 100)
    return f"{cs // 360000:01}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"


# Reference helper: export; see recipe prerequisites.
# 参考辅助函数：export；执行前查看参考脚本依赖。
def export(code):
    folder = ROOT / "work" / code
    cues = read(folder / "cues_reviewed.json")["cues"]
    d = SOURCES[code]
    out = ROOT / "字幕与原话"
    out.mkdir(exist_ok=True)
    srt = []
    md = [
        f"# {code}｜{d['name']} 原话与中文",
        "",
        "英语、德语原文配中文；粤语字幕转普通话书面表达，粤语底稿仍保留。声音编号只表示本音源分组。标明待核的内容不作为已经确认的原话。",
        "",
    ]
    ass = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 3840",
        "PlayResY: 2160",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Microsoft YaHei,60,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,150,150,150,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for i, c in enumerate(cues):
        text = (
            (c["original"] + "\n" + c["zh"])
            if c["language"] in ("English", "German") and not c.get("unresolved")
            else c["zh"]
        )
        label = f"[{c['speaker']}] "
        end = max(c["end"], c["start"] + 0.2)
        if i + 1 < len(cues):
            end = min(end, max(c["end"], cues[i + 1]["start"]))
        srt.append(f"{i + 1}\n{srtt(c['start'])} --> {srtt(end)}\n{label}{text}\n")
        ass.append(
            f"Dialogue: 0,{asst(c['start'])},{asst(end)},Default,,0,0,0,,{label}"
            + text.replace("\n", r"\N").replace("{", "(").replace("}", ")")
        )
        md.extend(
            [
                f"## {c['id']}｜{tc(c['start'])}—{tc(c['end'])}｜{c['speaker']}",
                f"原文：{c['original']}",
                f"中文：{c['zh']}",
            ]
        )
        if c.get("review_note"):
            md.append("听辨提示：" + c["review_note"])
        if c.get("original_candidate"):
            md.append("未采用的识别候选：" + c["original_candidate"])
        md.append("")
    (out / f"{code}_{d['name']}_双语字幕.srt").write_text("\n".join(srt), encoding="utf-8-sig")
    (out / f"{code}_{d['name']}_双语字幕.ass").write_text("\n".join(ass) + "\n", encoding="utf-8-sig")
    (out / f"{code}_{d['name']}_原话与中文.md").write_text("\n\n".join(md), encoding="utf8")
    save(out / f"{code}_{d['name']}_逐句时间轴.json", dict(cues=cues))
    index = ["# " + code + " 学习定位索引", "", "每五分钟一个回听入口；原录音未剪切。", ""]
    duration = float(probe(d["file"])["format"]["duration"])
    for s in range(0, int(duration) + 1, 300):
        cue = next((c for c in cues if c["start"] >= s), None)
        if cue:
            index.append(f"- {tc(s)}：{cue['zh'][:70]}（下一句 {cue['id']}，{tc(cue['start'])}）")
    (out / f"{code}_{d['name']}_时间索引.md").write_text("\n".join(index), encoding="utf8")
    save(
        ROOT / "核验" / f"{code}_字幕覆盖.json",
        dict(
            cues=len(cues),
            languages=dict(Counter(c["language"] for c in cues)),
            speaker_counts=dict(Counter(c["speaker"] for c in cues)),
            uncertain=sum(bool(c["review_note"]) for c in cues),
            alignment_unresolved=sum(bool(c.get("unresolved")) for c in cues),
            all_translations_nonempty=all(bool(c["zh"]) for c in cues),
            time_order=all(cues[i]["start"] <= cues[i + 1]["start"] for i in range(len(cues) - 1)),
        ),
    )
    log("export_complete", code=code, cues=len(cues))


if __name__ == "__main__":
    for c in sys.argv[1] if len(sys.argv) > 1 else "ABC":
        export(c)
