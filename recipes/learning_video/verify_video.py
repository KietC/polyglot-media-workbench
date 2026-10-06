# Generic reference implementation; main supported CLI is media-workbench.
# 通用参考实现；主使用入口为media-workbench。
from common import *
import sys, collections, re


# Reference helper: pcm signature; see recipe prerequisites.
# 参考辅助函数：pcm signature；执行前查看参考脚本依赖。
def pcm_signature(path):
    out = subprocess.check_output(
        [
            FFMPEG,
            "-hide_banner",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-c:a",
            "pcm_f32le",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ],
        encoding="utf8",
    )
    return out.strip()


# Reference helper: preserve aac priming; see recipe prerequisites.
# 参考辅助函数：preserve aac priming；执行前查看参考脚本依赖。
def preserve_aac_priming():
    # Native MP4 preserves AAC skip-sample/edit-list metadata; Matroska dropped the
    # source's 2112-sample leading priming marker in the empirical round-trip test.
    d = SOURCES["A"]
    dest = video_path("A")
    manifest = ROOT / "核验/A_全片_封装.json"
    if dest.exists():
        return
    mkv = ROOT / "视频" / f"A_{d['name']}_4K原声学习.mkv"
    subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-v",
            "error",
            "-nostdin",
            "-n",
            "-i",
            str(mkv),
            "-i",
            str(d["file"]),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c",
            "copy",
            "-map_metadata",
            "-1",
            "-video_track_timescale",
            "25000",
            "-movflags",
            "+faststart",
            str(dest),
        ],
        check=True,
    )
    m = read(manifest)
    m.update(
        output=str(dest),
        container_reason="MP4 retains original AAC priming/skip_samples without audio re-encoding",
        probe=probe(dest),
    )
    save(manifest, m)
    mkv.rename(ROOT / "work/A" / f"封装修订前_{int(time.time())}.mkv")


# Reference helper: packet signature; see recipe prerequisites.
# 参考辅助函数：packet signature；执行前查看参考脚本依赖。
def packet_signature(path):
    cmd = [
        FFPROBE,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_packets",
        "-show_data_hash",
        "sha256",
        "-show_entries",
        "packet=pts_time,duration_time,size,data_hash",
        "-of",
        "compact=p=0",
        str(path),
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf8")
    digest = hashlib.sha256()
    count = 0
    size = 0
    first = None
    last = None
    for line in p.stdout:
        fields = dict(part.split("=", 1) for part in line.strip().split("|") if "=" in part)
        h = fields.get("data_hash")
        if not h:
            continue
        digest.update(h.encode())
        count += 1
        size += int(fields.get("size", 0))
        timing = dict(pts=fields.get("pts_time"), duration=fields.get("duration_time"))
        if first is None:
            first = timing
        last = timing
    error = p.stderr.read()
    assert p.wait() == 0, error
    return dict(packet_hash=digest.hexdigest(), packet_count=count, payload_bytes=size, first=first, last=last)


# Reference helper: verify; see recipe prerequisites.
# 参考辅助函数：verify；执行前查看参考脚本依赖。
def verify(code):
    if code == "A":
        preserve_aac_priming()
    d = SOURCES[code]
    path = video_path(code)
    assert path.exists()
    original = packet_signature(d["file"])
    output = packet_signature(path)
    same = all(original[k] == output[k] for k in ("packet_hash", "packet_count", "payload_bytes"))
    pr = probe(path)
    sourcepr = probe(d["file"])
    v = next(s for s in pr["streams"] if s["codec_type"] == "video")
    a = next(s for s in pr["streams"] if s["codec_type"] == "audio")
    oa = next(s for s in sourcepr["streams"] if s["codec_type"] == "audio")
    format_same = all(a[k] == oa[k] for k in ("codec_name", "sample_rate", "channels"))
    with (ROOT / "核验" / f"{code}_完整解码.log").open("w", encoding="utf8") as f:
        result = subprocess.run(
            [
                FFMPEG,
                "-hide_banner",
                "-v",
                "error",
                "-nostdin",
                "-xerror",
                "-threads",
                "8",
                "-i",
                str(path),
                "-f",
                "null",
                "-",
            ],
            stdout=f,
            stderr=f,
        )
    pcm_source = pcm_signature(d["file"])
    pcm_output = pcm_signature(path)
    report = dict(
        file=str(path),
        sha256=sha(path),
        bytes=path.stat().st_size,
        original_audio=original,
        output_audio=output,
        compressed_audio_payload_identical=same,
        audio_format_identical=format_same,
        decoded_pcm_source_sha256=pcm_source,
        decoded_pcm_output_sha256=pcm_output,
        decoded_pcm_identical=pcm_source == pcm_output,
        video_size=[v["width"], v["height"]],
        duration=float(pr["format"]["duration"]),
        source_duration=float(sourcepr["format"]["duration"]),
        full_decode_exit=result.returncode,
    )
    report["passed"] = (
        same
        and format_same
        and pcm_source == pcm_output
        and result.returncode == 0
        and [v["width"], v["height"]] == [3840, 2160]
        and abs(report["duration"] - report["source_duration"]) < 0.2
    )
    save(ROOT / "核验" / f"{code}_视频音轨验收.json", report)
    assert report["passed"], report
    log("verify_complete", code=code, passed=True, bytes=report["bytes"], audio_packets=original["packet_count"])


if __name__ == "__main__":
    for c in sys.argv[1] if len(sys.argv) > 1 else "ABC":
        verify(c)
