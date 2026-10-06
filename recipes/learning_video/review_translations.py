# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
# REVIEW SNAPSHOT: redacted task data; see source provenance and audit.
from common import *
import re, requests, concurrent.futures, sys, time
from opencc import OpenCC

CC = OpenCC("t2s")
VY = r"[佢嘅咗咁係冇唔哋啲嗰畀睇嚟喺啩噉俾乜嘢]"
NAMES = {}
MANUAL = {}


# Reference helper: direct; see recipe prerequisites.
# 参考辅助函数：direct；执行前查看参考脚本依赖。
def direct(c):
    text = c["original"]
    system = "You are a precise subtitle translator. Translate ONLY the user speech into Simplified Mandarin Chinese. If Cantonese, convert it to standard written Mandarin: no Cantonese pronouns or particles. Translate English and German into Chinese. Preserve all numbers, negations, conditions, questions, repetitions and unfinished phrases. Do not summarize, explain or invent context. Keep proper names in their original Latin spelling. Unintelligible words: [听不清]. Output ONLY the Chinese translation, no quotes, labels, JSON or source text."
    payload = dict(
        model="local-translator",
        temperature=0,
        max_tokens=500,
        chat_template_kwargs={"enable_thinking": False},
        messages=[dict(role="system", content=system), dict(role="user", content=text)],
    )
    r = requests.post("http://127.0.0.1:5127/v1/chat/completions", json=payload, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


# Reference helper: invalid; see recipe prerequisites.
# 参考辅助函数：invalid；执行前查看参考脚本依赖。
def invalid(c, zh):
    if c.get("unresolved"):
        return False
    if c["language"] == "Cantonese" and re.search(VY, zh):
        return True
    han = len(re.findall(r"[\u4e00-\u9fff]", zh))
    latin = len(re.findall("[a-zA-Z]", zh))
    return (han == 0 and latin > 10) or (latin > max(45, han * 3) and len(c["original"]) > 40)


# Reference helper: run; see recipe prerequisites.
# 参考辅助函数：run；执行前查看参考脚本依赖。
def run(code, sample=False):
    folder = ROOT / "work" / code
    inputp = folder / ("cues_sample.json" if sample else "cues_translated.json")
    while not inputp.exists():
        time.sleep(3)
    cues = read(inputp)["cues"]
    cache = folder / "review_translation_cache"
    cache.mkdir(exist_ok=True)
    # The extra pass covers every Cantonese cue, plus copied/untranslated foreign text.
    todo = [c for c in cues if not c.get("unresolved") and (c["language"] == "Cantonese" or invalid(c, c["zh"]))]

    # Reference helper: fix; see recipe prerequisites.
    # 参考辅助函数：fix；执行前查看参考脚本依赖。
    def fix(c):
        if c["id"] in MANUAL:
            return c["id"], MANUAL[c["id"]]
        key = hashlib.sha256(c["original"].encode()).hexdigest()[:12]
        p = cache / (c["id"] + "_" + key + ".json")
        if p.exists():
            return c["id"], read(p)["zh"]
        result = c["zh"]
        for attempt in range(3):
            result = CC.convert(direct(c))
            if not invalid(c, result):
                break
        if invalid(c, result):
            prompt_c = dict(c, original="请把下面这句粤语完整转换成普通话书面语，不得保留粤语用字：\n" + c["original"])
            result = CC.convert(direct(prompt_c))
        if invalid(c, result):
            substitutions = [
                ("佢哋", "他们"),
                ("我哋", "我们"),
                ("你哋", "你们"),
                ("有冇", "有没有"),
                ("唔係", "不是"),
                ("点解", "为什么"),
                ("呢啲", "这些"),
                ("嗰啲", "那些"),
                ("咁样", "这样"),
                ("佢", "他"),
                ("嘅", "的"),
                ("咗", "了"),
                ("咁", "这样"),
                ("係", "是"),
                ("冇", "没有"),
                ("唔", "不"),
                ("啲", "一些"),
                ("嗰", "那"),
                ("畀", "给"),
                ("俾", "给"),
                ("睇", "看"),
                ("嚟", "来"),
                ("喺", "在"),
                ("乜嘢", "什么"),
                ("乜", "什么"),
                ("嘢", "东西"),
                ("哋", "们"),
                ("噉", "这样"),
                ("啩", "吧"),
            ]
            for a, b in substitutions:
                result = result.replace(a, b)
        if invalid(c, result):
            result = "[该句中文仍待核对，请结合原声与原文回听]"
        save(p, dict(id=c["id"], original=c["original"], zh=result, method="single_sentence_mandarin_repair"))
        return c["id"], result

    repairs = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for i, (key, value) in enumerate(pool.map(fix, todo)):
            repairs[key] = value
            if (i + 1) % 30 == 0:
                log("review_progress", code=code, done=i + 1, total=len(todo))
    changes = []
    for c in cues:
        before = c["zh"]
        c["zh"] = CC.convert(MANUAL.get(c["id"], repairs.get(c["id"], before)))
        for a, b in NAMES.items():
            c["zh"] = c["zh"].replace(a, b)
        if before != c["zh"]:
            changes.append(dict(id=c["id"], before=before, after=c["zh"]))
        if invalid(c, c["zh"]):
            raise RuntimeError("Untranslated cue: " + c["id"])
    save(
        folder / ("cues_sample_reviewed.json" if sample else "cues_reviewed.json"),
        dict(status="reviewed_with_marked_asr_uncertainty", cues=cues),
    )
    save(
        ROOT / "核验" / f"{code}_{'样片' if sample else '全片'}_翻译修订.json",
        dict(changes=changes, all_cues_checked=len(cues), cantonese_and_copy_repair=len(todo)),
    )
    log("review_complete", code=code, cues=len(cues), repairs=len(changes))


if __name__ == "__main__":
    for code in sys.argv[1] if len(sys.argv) > 1 else "ABC":
        run(code, "--sample" in sys.argv)
