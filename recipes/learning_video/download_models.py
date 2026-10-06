# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
from common import *
import concurrent.futures, requests


# Reference helper: download repo; see recipe prerequisites.
# 参考辅助函数：download repo；执行前查看参考脚本依赖。
def download_repo(repo):
    base = ROOT / "work/models" / repo.split("/")[-1]
    base.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    meta = session.get("https://huggingface.co/api/models/" + repo, timeout=30)
    meta.raise_for_status()
    revision = meta.json()["sha"]
    response = session.get(
        f"https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true&expand=false", timeout=30
    )
    response.raise_for_status()
    files = [
        x
        for x in response.json()
        if x["type"] == "file" and x["path"].endswith((".json", ".safetensors", ".txt", ".jinja"))
    ]

    # Reference helper: one; see recipe prerequisites.
    # 参考辅助函数：one；执行前查看参考脚本依赖。
    def one(info):
        name = info["path"]
        p = base / name
        p.parent.mkdir(parents=True, exist_ok=True)
        size = info["size"]
        if p.exists() and p.stat().st_size == size:
            return
        part = p.with_suffix(p.suffix + ".part")
        for retry in range(3):
            try:
                offset = part.stat().st_size if part.exists() else 0
                origin = (
                    f"https://modelscope.cn/models/{repo}/resolve/master/{name}"
                    if retry < 2 and name.endswith(".safetensors")
                    else f"https://huggingface.co/{repo}/resolve/{revision}/{name}"
                )
                req = requests.get(
                    origin, headers={"Range": f"bytes={offset}-"} if offset else {}, stream=True, timeout=(20, 25)
                )
                req.raise_for_status()
                if req.status_code != 206:
                    offset = 0
                with part.open("ab" if offset else "wb") as f:
                    for chunk in req.iter_content(2 * 1024 * 1024):
                        f.write(chunk)
                assert part.stat().st_size == size, (name, size, part.stat().st_size)
                part.replace(p)
                log("download_file", repo=repo, file=name, bytes=size)
                return
            except Exception as exc:
                log("download_retry", repo=repo, file=name, attempt=retry, error=str(exc))
                if retry == 2:
                    raise
        raise RuntimeError(name)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(one, files))
    save(base / "download_manifest.json", dict(repo=repo, revision=revision, files=files, status="complete"))
    log("download_complete", repo=repo, path=str(base))


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(download_repo, ["Qwen/Qwen3-ForcedAligner-0.6B", "Qwen/Qwen3-8B-AWQ"]))
