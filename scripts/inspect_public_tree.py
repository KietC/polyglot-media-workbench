"""Fail on source-tree media, credentials or personal machine paths.
对源码目录中的媒体、凭据或个人机器路径执行失败检查。
"""

from pathlib import Path
import argparse
import ast
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DENY_SUFFIX = {
    ".wav",
    ".mp3",
    ".m4a",
    ".flac",
    ".mp4",
    ".mkv",
    ".webm",
    ".jpg",
    ".jpeg",
    ".png",
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".srt",
    ".ass",
    ".safetensors",
    ".pt",
    ".pth",
    ".onnx",
    ".bin",
    ".pem",
    ".key",
}
PATTERNS = [
    r"gh[pousr]_[A-Za-z0-9]{30,}",
    r"github_pat_[A-Za-z0-9_]{35,}",
    r"sk-[A-Za-z0-9_-]{30,}",
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"AKIA[A-Z0-9]{16}",
    r"(?i)(?:api_key|api_secret|password|access_token)\s*[:=]\s*[\"\'][A-Za-z0-9+/=_-]{20,}[\"\']",
    r"[A-Za-z]:[/\\]Users[/\\][A-Za-z0-9_.-]+[/\\]",
    r"company_id=\d{10,}",
    r"MsgID=\d{10,}",
]


def inspect(root=ROOT, forbidden=()):
    files = []
    # In a repository inspect tracked files; before initial git add inspect source files.
    # Git仓库检查跟踪文件；首次git add前检查源码文件。
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True)
    if result.returncode == 0 and result.stdout:
        files = [root / p for p in result.stdout.decode("utf8").split("\0") if p]
    else:
        files = [
            p
            for p in root.rglob("*")
            if p.is_file()
            and not any(x in p.parts for x in (".git", ".venv", "__pycache__", ".ruff_cache", "build", "dist"))
            and ".egg-info" not in str(p)
        ]
    findings = []
    compiled = [re.compile(p) for p in PATTERNS]
    for path in files:
        rel = path.relative_to(root).as_posix()
        if path.suffix.lower() in DENY_SUFFIX or path.name.startswith(".env") or path.name == "local_config.json":
            findings.append(dict(file=rel, reason="Disallowed data/config artifact"))
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            findings.append(dict(file=rel, reason="Unexpected binary content"))
            continue
        if path.suffix == ".py":
            try:
                ast.parse(text)
            except SyntaxError as exc:
                findings.append(dict(file=rel, reason=f"Python syntax: {exc.lineno}"))
        for pattern in compiled:
            if pattern.search(text):
                findings.append(dict(file=rel, reason="Credential/private path pattern; value withheld"))
        if any(word.casefold() in text.casefold() for word in forbidden):
            findings.append(dict(file=rel, reason="Forbidden private marker; value withheld"))
    return dict(
        passed=not findings,
        files_checked=len(files),
        findings=findings,
        scope="Finite patterns and source artifacts; pair with manual review before publishing",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--forbid", action="append", default=[])
    args = p.parse_args()
    result = inspect(forbidden=args.forbid)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
