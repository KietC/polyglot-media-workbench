"""Ordered subtitle translation over an explicitly local endpoint.
通过明确的本地端点按顺序翻译字幕。
"""

from __future__ import annotations
from pathlib import Path
import json
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import HTTPError

from .core import cached, fingerprint, read_json, save_json, sha256

SYSTEM = """Translate each item into Simplified Chinese. Translate English and German; convert Cantonese into standard written Mandarin. Preserve numbers, units, negation, conditions, questions, repetition, uncertainty and unfinished clauses. Do not summarize, infer identities or fill gaps. Keep one item per input id in the same order. Return only {"translations":[{"id":"...","zh":"..."}]}.
逐项翻译为简体中文，粤语转普通话书面表达。保留数字、否定、条件、疑问、重复、不确定和未完成句。禁止总结、推断身份和补造内容。id与顺序必须完全一致。
"""


class NoRedirect(HTTPRedirectHandler):
    """Do not forward private text from a loopback service to a redirect target.
    不将私人文字从本机回环服务转发至重定向目标。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Redirects disabled for local translation", headers, fp)


def local_open(request, timeout):
    """Ignore environment proxies and disable redirects for local translation traffic.
    本地翻译流量不采用环境代理，也不跟随重定向。
    """
    return build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout)


def request_batch(units, config):
    """Call a loopback chat service and reject omitted, duplicated or reordered ids.
    调用本机回环对话服务，并拒绝漏项、重复或乱序的id。
    """
    endpoint = config["translation"]["url"]
    if urlparse(endpoint).hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Translation endpoint must be loopback / 翻译端点必须为本机回环地址")
    payload = dict(
        model=config["translation"]["model"],
        temperature=0,
        max_tokens=3000,
        chat_template_kwargs={"enable_thinking": False},
        response_format={"type": "json_object"},
        messages=[
            dict(role="system", content=SYSTEM),
            dict(
                role="user",
                content=json.dumps(
                    [dict(id=u["id"], text=u["original"], language=u["language"]) for u in units], ensure_ascii=False
                ),
            ),
        ],
    )
    request = Request(endpoint, json.dumps(payload).encode("utf8"), headers={"Content-Type": "application/json"})
    with local_open(request, timeout=config["translation"]["timeout"]) as response:
        answer = json.load(response)
    results = json.loads(answer["choices"][0]["message"]["content"])["translations"]
    # Exact id equality rejects reordered, omitted and duplicated translations.
    # id完全相等可拒绝乱序、漏项及重复翻译。
    if [r["id"] for r in results] != [u["id"] for u in units] or any(
        not isinstance(r["zh"], str) or not r["zh"].strip() for r in results
    ):
        raise ValueError("Translation id/order/content mismatch / 翻译id、顺序或正文不匹配")
    return results


def translate(input_file, output, config):
    """Translate eight units per request, with three attempts and an explicit pending status.
    每次翻译八个单元，最多尝试三次，明确保留待审校状态。
    """
    input_file = Path(input_file)
    key = fingerprint(sha256(input_file), "translation", dict(config, translation_prompt=SYSTEM))
    previous = cached(output, key)
    if previous:
        return previous
    units = read_json(input_file)["units"]
    translated = []
    for start in range(0, len(units), 8):
        batch = units[start : start + 8]
        for attempt in range(3):
            try:
                results = request_batch(batch, config)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1 + attempt)
        translated.extend(dict(u, zh=r["zh"]) for u, r in zip(batch, results))
        # Processing is checkpointed; generated translation still needs human review.
        # 处理按块保存断点，自动翻译仍需人工审校。
        save_json(
            output,
            dict(
                status="complete" if len(translated) == len(units) else "running",
                fingerprint=key,
                editorial_status="pending",
                units=translated,
            ),
        )
    return read_json(output)
