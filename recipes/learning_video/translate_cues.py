# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
# REVIEW SNAPSHOT: redacted task data; see source provenance and audit.
from common import *
import requests, concurrent.futures, threading, re, sys, time

BASE = "http://127.0.0.1:5127"
SYSTEM = """你是会议录音的逐句字幕翻译员。输出简体中文，忠于每句原话，不是报告、摘要或分析。
输入是带id的连续字幕。英语和德语逐句译成中文；粤语改成普通话书面表达，原有中文转简体。保留数字、单位、否定、条件、重复、问句和未说完的句子，不编造缺失内容，不添加解释，不写“他表示”。只能参考前后句理解本句，不能把下一句意思提前挪到本句；一句一条、顺序不变。原话本身不完整就保留不完整，不推断完整交易或人物身份。
专名以输入为准，保留原文拼写。疑似错词且确实无法理解时，仅在该词位置写[听不清]；其余可辨部分照译，不补造上下文。
只输出JSON对象 {"translations":[{"id":"原id","zh":"中文"}]}，不能漏项，不能合并，不复述英文。
"""


# Reference helper: request batch; see recipe prerequisites.
# 参考辅助函数：request batch；执行前查看参考脚本依赖。
def request_batch(cues):
    data = [dict(id=c["id"], text=c["original"], language=c["language"]) for c in cues]
    payload = dict(
        model="local-translator",
        temperature=0,
        max_tokens=2400,
        chat_template_kwargs={"enable_thinking": False},
        messages=[dict(role="system", content=SYSTEM), dict(role="user", content=json.dumps(data, ensure_ascii=False))],
        response_format={"type": "json_object"},
    )
    r = requests.post(BASE + "/v1/chat/completions", json=payload, timeout=240)
    r.raise_for_status()
    response = r.json()
    text = response["choices"][0]["message"]["content"]
    result = json.loads(text)["translations"]
    assert [x["id"] for x in result] == [c["id"] for c in cues], "id/order mismatch"
    for x, c in zip(result, cues):
        assert isinstance(x["zh"], str) and x["zh"].strip(), "empty"
        assert len(x["zh"]) < max(200, len(c["original"]) * 4), "overlong"
    return result


# Reference helper: run; see recipe prerequisites.
# 参考辅助函数：run；执行前查看参考脚本依赖。
def run(code, limit=None):
    folder = ROOT / "work" / code
    cues = read(folder / "cues_original.json")["cues"]
    if limit:
        cues = cues[:limit]
    cache = folder / "translation_batches"
    cache.mkdir(exist_ok=True)
    batches = [cues[i : i + 10] for i in range(0, len(cues), 10)]
    lock = threading.Lock()
    completed = 0

    # Reference helper: process; see recipe prerequisites.
    # 参考辅助函数：process；执行前查看参考脚本依赖。
    def process(index):
        nonlocal completed
        batch = batches[index]
        digest = hashlib.sha256(
            json.dumps([(c["id"], c["original"]) for c in batch], ensure_ascii=False).encode()
        ).hexdigest()[:16]
        p = cache / f"{index:04}_{digest}.json"
        if p.exists():
            return read(p)["translations"]
        todo = [c for c in batch if not c.get("unresolved")]
        fixed = [dict(id=c["id"], zh="[低声或重叠，无法可靠辨认]") for c in batch if c.get("unresolved")]
        last = None
        for attempt in range(3):
            try:
                translated = request_batch(todo) if todo else []
                result = {x["id"]: x["zh"] for x in fixed + translated}
                rows = [dict(id=c["id"], zh=result[c["id"]]) for c in batch]
                save(p, dict(translations=rows, model="Qwen3-8B-AWQ", local_only=True))
                with lock:
                    completed += 1
                    log("translate_progress", code=code, batches=completed, total=len(batches))
                return rows
            except Exception as exc:
                last = exc
        # Split malformed outputs into smaller requests without losing IDs.
        result = {x["id"]: x["zh"] for x in fixed}
        for c in todo:
            for attempt in range(3):
                try:
                    result[c["id"]] = request_batch([c])[0]["zh"]
                    break
                except Exception as exc:
                    last = exc
            if c["id"] not in result:
                raise RuntimeError(f"{c['id']}: {last}")
        rows = [dict(id=c["id"], zh=result[c["id"]]) for c in batch]
        save(p, dict(translations=rows, model="Qwen3-8B-AWQ", split_retry=True))
        return rows

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        result = list(pool.map(process, range(len(batches))))
    tr = {x["id"]: x["zh"] for batch in result for x in batch}
    for c in cues:
        c["zh"] = tr[c["id"]]
    out = folder / ("cues_sample.json" if limit else "cues_translated.json")
    save(out, dict(status="translated_pending_editorial_qa", cues=cues))
    log("translate_complete", code=code, cues=len(cues))


if __name__ == "__main__":
    for i in range(240):
        try:
            r = requests.get(BASE + "/health", timeout=3)
            if r.ok:
                break
        except Exception:
            pass
        time.sleep(3)
    else:
        raise RuntimeError("local translator did not become ready")
    for code in sys.argv[1] if len(sys.argv) > 1 else "ABC":
        run(code, 80 if "--sample" in sys.argv else None)
