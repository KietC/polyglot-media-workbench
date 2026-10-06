"""Configuration, bounded commands and content-based checkpoints.
配置、有时限命令及基于内容的断点。
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

DEFAULTS = {
    "ffmpeg": "ffmpeg",
    "ffprobe": "ffprobe",
    "device": "cuda",
    "cpu_threads": 8,
    "batch_size": 16,
    "chunk_seconds": 30,
    "beam_size": 5,
    "whisper_compute_type": "float16",
    "whisper_vad": False,
    "command_timeout": 14400,
    "offline": True,
    "models": {
        "whisper": "models/whisper-turbo",
        "qwen": "models/qwen-asr",
        "aligner": "models/forced-aligner",
        "vision": "models/internvl",
    },
    "speaker_cache": "models/speaker-cache",
    "translation": {"url": "http://127.0.0.1:5127/v1/chat/completions", "model": "local-translator", "timeout": 240},
}

_DLL_HANDLES = []


def prepare_cuda_runtime():
    """Expose installed Windows CUDA DLL folders for this Python process only.
    仅为当前Python进程开放已安装的Windows CUDA DLL目录。
    """
    if os.name != "nt":
        return []
    folders = set()
    for module, relatives in (("torch", ("lib",)), ("nvidia", ("cublas/bin", "cudnn/bin"))):
        try:
            spec = importlib.util.find_spec(module)
        except (ImportError, ValueError):
            spec = None
        if spec:
            for base in spec.submodule_search_locations or []:
                for relative in relatives:
                    folder = Path(base) / relative
                    if folder.is_dir():
                        folders.add(str(folder))
    for folder in sorted(folders):
        if folder not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            _DLL_HANDLES.append(os.add_dll_directory(folder))
    return sorted(folders)


def save_json(path, data):
    # Unique temporary files prevent writers from sharing one .tmp file.
    # 独立临时文件防止多个写入者争用同一个.tmp文件。
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        for attempt in range(20):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.05)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path):
    """Read UTF-8 JSON, accepting the BOM written by some Windows editors.
    读取UTF-8 JSON，兼容部分Windows编辑器写入的BOM。
    """
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha256(path):
    """Stream file content in bounded blocks instead of loading model weights into RAM.
    分块读取文件内容，避免将模型权重整体装入内存。
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_config(path=None):
    """Merge local overrides and validate integer resource limits before model loading.
    合并本地配置，并在加载模型前验证整数资源限制。
    """
    config = json.loads(json.dumps(DEFAULTS))
    base = Path.cwd()
    if path:
        path = Path(path).resolve()
        incoming = read_json(path)
        base = path.parent
        for key, value in incoming.items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key].update(value)
            else:
                config[key] = value
    # Paths resolve relative to the config, not the invoking shell directory.
    # 路径相对配置文件解析，不随调用命令的当前目录变化。
    for key, value in config["models"].items():
        config["models"][key] = str((base / os.path.expandvars(value)).resolve())
    config["speaker_cache"] = str((base / os.path.expandvars(config["speaker_cache"])).resolve())
    if config.get("speaker_repo"):
        config["speaker_repo"] = str((base / os.path.expandvars(config["speaker_repo"])).resolve())
    for key in ("batch_size", "chunk_seconds", "cpu_threads", "command_timeout"):
        if not isinstance(config[key], int) or isinstance(config[key], bool) or config[key] <= 0:
            raise ValueError(f"{key} must be positive / 必须大于零")
    return config


def offline_environment(config):
    # This sets library flags; it is not an operating-system network firewall.
    # 此处设置库的离线标记，并非操作系统级网络防火墙。
    if config["offline"]:
        for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
            os.environ[key] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["MEDIA_WORKBENCH_SPEAKER_CACHE"] = config["speaker_cache"]


def command(args, timeout=14400, cwd=None, env=None):
    # A list of arguments avoids shell expansion and quoting of user paths.
    # 参数列表避免shell展开及用户路径引号问题。
    result = subprocess.run(
        [str(a) for a in args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {result.stderr[-6000:]}")
    return result.stdout


def probe(path, config):
    """Inspect actual streams and duration through a bounded ffprobe subprocess.
    通过有时限的ffprobe子进程检查实际音视频轨道及总时长。
    """
    return json.loads(
        command([config["ffprobe"], "-v", "error", "-show_format", "-show_streams", "-of", "json", path], 120)
    )


def fingerprint(source_hash, stage, config):
    # Include model content, package versions and parameters in the cache key.
    # 缓存键同时绑定模型文件、依赖版本和参数。
    model_key = {"whisper": "whisper", "qwen": "qwen", "align": "aligner", "vision": "vision"}.get(stage)
    model_hashes = {}
    if model_key:
        root = Path(config["models"][model_key])
        if not root.is_dir():
            raise FileNotFoundError(f"Missing model directory: {root}")
        for p in sorted(root.rglob("*")):
            if p.is_file() and ".cache" not in p.parts:
                model_hashes[p.relative_to(root).as_posix()] = sha256(p)
    if stage == "diar":
        root = Path(config["speaker_cache"])
        for p in sorted(root.rglob("*")):
            if p.is_file():
                model_hashes[p.relative_to(root).as_posix()] = sha256(p)
    versions = {}
    for package in ("faster-whisper", "qwen-asr", "torch", "transformers", "modelscope", "funasr"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    # Hash the implementation too: a code edit must invalidate stale inference.
    # 也绑定实现代码，代码修改后不能继续命中旧推理缓存。
    code = {p.name: sha256(p) for p in Path(__file__).parent.glob("*.py")}
    data = dict(
        schema=1, source=source_hash, stage=stage, config=config, models=model_hashes, packages=versions, code=code
    )
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def cached(path, key):
    """Only completed, readable, exactly matching checkpoints may be reused.
    仅复用已完成、可读取且指纹完全匹配的断点。
    """
    try:
        data = read_json(path)
        return data if data.get("status") == "complete" and data.get("fingerprint") == key else None
    except (OSError, ValueError):
        return None


def timestamp(seconds):
    # Integer milliseconds handle 59.9996 rounding across a minute boundary.
    # 整数毫秒可正确处理59.9996秒跨分钟的舍入。
    ms = max(0, round(seconds * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"


def doctor(config):
    """Inventory tools and installed packages; do not imply accuracy or kernel certification.
    列出工具与安装包，不将清单当作准确率或模型内核验证。
    """
    report = {"tools": {}, "models": {}, "packages": {}}
    for tool in ("ffmpeg", "ffprobe"):
        found = shutil.which(config[tool])
        report["tools"][tool] = found
    for key, value in config["models"].items():
        report["models"][key] = {"directory_exists": Path(value).is_dir()}
    for package in (
        "torch",
        "faster-whisper",
        "qwen-asr",
        "soundfile",
        "modelscope",
        "rapidocr-onnxruntime",
        "python-docx",
        "python-pptx",
    ):
        try:
            report["packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            report["packages"][package] = None
    try:
        import torch

        report["cuda"] = {"available": torch.cuda.is_available(), "torch_cuda": torch.version.cuda}
        if torch.cuda.is_available():
            report["cuda"]["gpu"] = torch.cuda.get_device_name(0)
    except ImportError:
        report["cuda"] = {"available": False}
    return report
