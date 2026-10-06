# Release validation / 发布验证

## English

Validation date: **2026-10-05**, release candidate **0.1.0**. Checks used synthetic speech, a generated tone, synthetic captions and synthetic document content. No production recording, customer transcript, company document or account credential is included.

| Check | Result and actual scope |
|---|---|
| Unit contracts | 19 tests passed: paths, integer limits, UTF-8 JSON, source hashes, cache invalidation, failure states, model comparison, voice overlap, translation ordering/redirect rejection, video packet timing and vendored model architecture presence. |
| GPU ASR pipeline | A 6.19-second synthetic English utterance completed Whisper, Qwen, CAMPPlus/FSMN diarization, fusion, Qwen forced alignment and Markdown export. Both recognizers returned the spoken synthetic sentence; the source hash was unchanged. This is not a multilingual accuracy benchmark. |
| Frame extraction/OCR | Two-second synthetic 3840×2160 video decoded 50 frames, retained both caption states and produced OCR text from the PNGs. |
| Study video | NVIDIA H.264 encoding, 25 fps, 50 video packets, two-second coverage, unchanged source, identical audio packet count/content and decoded PCM hashes, complete FFmpeg decode. |
| Translation interface | A local mock chat-completions service passed ids/order/non-empty-content checks. Unit tests reject a reordered response. Translation model quality was not measured. |
| Document generation | Synthetic MD/DOCX/PPTX produced; Word text and the two-slide deck were reopened and checked. All-page Office visual QA is still a per-document obligation, not a release certification. |
| Portable figures | A second synthetic document with wide and tall images retained both pictures in Word/PPT, kept slide image bounds inside the canvas and generated working Markdown asset copies. |
| Packaging | Source distribution and wheel built successfully. A fresh environment installed the wheel without model dependencies and ran the CLI help. Package contents were checked for private markers; the source archive includes the speaker source and licenses. |
| Source checks | Syntax, Ruff, skill frontmatter and PowerShell parser checks passed. Public artifact/secret-pattern checks and a separate private-marker review passed before upload. A finite scanner is not proof against every possible secret. |

The GPU smoke run used Windows, Python 3.12, an NVIDIA GPU, torch/torchaudio 2.11.0 (CUDA 12.8), faster-whisper 1.2.1, qwen-asr 0.0.6, transformers 4.57.6, ModelScope 1.37.1 and FunASR 1.3.9. These are observed versions, not a promise that every later dependency combination behaves identically. The repository CI checks source contracts on Windows and Linux, Python 3.10 and 3.12; check the live Actions badge for its current status.

### Reproduce the checks

```bash
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m ruff check src tests scripts
python scripts/inspect_public_tree.py
```

After installing Pillow/document dependencies and FFmpeg, run the independent synthetic video test with your own installed CJK font:

```bash
python scripts/smoke_media.py --font /path/to/bilingual-font.ttf
```

Use `--codec h264_nvenc` only when that encoder is available. It creates and cleans a temporary synthetic clip; no model weights or real media are required. GPU inference checks require separately prepared models and a short clip using the setup guide.

### Remaining responsibilities

Local InternVL inference, real translation quality, multiple simultaneous voices, quiet/overlapping multilingual recordings, real download availability and long-document layout were not certified by this smoke test. Review each real task against its source. No real identity, payment, purchase, subscription or transaction was executed.

## 简体中文

验证日期：**2026年10月5日**，候选版本**0.1.0**。使用合成讲话、测试音、合成字幕和合成正文；不包含生产录音、客户转写、公司文档或账户凭据。

| 检查 | 实际结果与范围 |
|---|---|
| 单元约定 | 19项通过，覆盖路径、整数参数、UTF-8、哈希、缓存失效、失败状态、双路对照、声音重叠归属、翻译顺序/拒绝重定向、视频包时间及第三方模型架构源码是否齐全。 |
| GPU识别 | 6.19秒合成英语完成Whisper、Qwen、CAMPPlus/FSMN分离、融合、Qwen强制对齐和MD导出。两路均识别出测试句，原文件哈希不变；不等于多语言准确率测评。 |
| 抽帧/OCR | 两秒3840×2160测试视频完整解码50帧，保留两个字幕状态，PNG产生OCR文字。 |
| 学习视频 | NVIDIA H.264、25fps、50视频包、完整两秒覆盖；原音源未变，音频包数量/内容与PCM哈希一致，完整解码通过。 |
| 翻译接口 | 本机模拟服务验证id、顺序和非空内容；单元测试拒绝乱序。未评测真实翻译模型质量。 |
| 文档 | 合成MD、Word、PPT生成成功，重开检查Word文字和两页PPT。实际长文仍需逐页视觉审阅，不能把文件完整性当排版验收。 |
| 可移动配图 | 另用宽图、高图验证，两张图片均进入Word/PPT，PPT图片位于画布边界内，Markdown配图副本链接有效。 |
| 打包 | 源码分发包和wheel构建成功，全新环境无模型依赖安装wheel并运行CLI帮助；包内私人标记检查通过，源码包含说话人引擎及许可。 |
| 源码 | 语法、Ruff、skill格式及PowerShell解析通过。上传前另做禁用数据类型、凭据模式和私人标记检查；有限扫描不保证穷尽所有秘密。 |

GPU实测环境为Windows、Python3.12、NVIDIA显卡、torch/torchaudio2.11.0 CUDA12.8、faster-whisper1.2.1、qwen-asr0.0.6、transformers4.57.6、ModelScope1.37.1、FunASR1.3.9。它们是实际观测版本，不是所有组合的兼容保证。CI检查Windows/Linux及Python3.10/3.12的源码约定，当前结果以Actions徽章为准。

复现命令见英文部分。`scripts/smoke_media.py`使用临时合成音源验证4K和原声，无需模型或真实录音；必须提供支持中文的本机字体，有NVIDIA编码器才选h264_nvenc。

InternVL真实推理、真实翻译质量、多说话人、低声重叠多语言、实际下载及长篇排版未由本次冒烟测试认证，正式任务逐项复核。本次未执行真实身份验证、付款、购买、订阅或交易。
