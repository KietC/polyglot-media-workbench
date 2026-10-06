# Pitfalls and remedies / 踩坑与排错

## English

Follow the failed stage in `state.json`; fix that stage before continuing to its consumers. Keep the original media and raw model output while correcting a reviewed copy.

| Symptom | Cause to check | Concrete remedy and success check |
|---|---|---|
| A copied `.venv` says “No Python at …” | Environment points to the previous interpreter | Create a new environment with the current Python; print `sys.executable` and reinstall dependencies there. |
| `media-workbench` is not found | Wrong shell/environment or base package not installed | Use the environment's executable directly; `python -m pip show polyglot-media-workbench`; confirm `--help` works. |
| `ffprobe` or `ffmpeg` is not found | PATH/config points to the wrong executable | Set both config entries, quote paths with spaces and run each `-version`. |
| Wrong speaker language/content is recognized | First audio track is not the desired commentary | Inspect stream ids; extract `-map 0:a:1` to a new analysis file if that is the correct track. Do not overwrite the source. |
| GPU appears in `nvidia-smi` but torch says False | CPU wheel, old driver, incompatible runtime | Install the platform-specific torch build; confirm CUDA availability inside the same environment used by the CLI. |
| CTranslate2 cannot load cuDNN/cuBLAS | Its runtime dependencies differ from torch | Read faster-whisper GPU instructions; make required DLL/library directories visible before launching Python. |
| CUDA out of memory | Batch/model/GPU contention | Reduce batch 16→8→4→2→1; close your own conflicting inference process; process GPU stages sequentially. Qwen retries with smaller batches; persistent OOM still fails. |
| Whisper cannot find `model.bin` | Transformers-format checkpoint used | Download a CTranslate2 checkpoint; verify model.bin plus tokenizer/config files. |
| Qwen model/tokenizer load fails | Incomplete checkpoint or mismatched transformers | Check qwen-asr/transformers versions, all model shards and config; use a local model directory, not one safetensors file. |
| Offline diarization says cache missing | Wrong root or missing model-id hierarchy | Run the explicit speaker download script with the same cache root; inspect configuration.json under each full model id. |
| Speaker clustering cannot import fastcluster | An upstream optional dependency was omitted | Install the current `.[diar]` extra, which explicitly includes fastcluster; do not install the old vendor requirements over the new environment. |
| Diarization works locally but the uploaded copy lacks CAMPPlus | An unanchored `models/` gitignore also excluded architecture source | Keep private weights ignored as `/models/`, but include `vendor/3d-speaker/speakerlab/models/*.py`; check the tracked tree, not only local files. |
| Speaker engine attempts a download | ModelScope cache not prepared | HF offline flags alone do not control ModelScope. The main diarization preflight checks cache configuration; ensure weights also exist. |
| Same text appears after changing a model | Stale results in a recipe or untracked service model change | Use the CLI's content/parameter cache keys. Update a translation model's configured identifier after replacement. Do not rely on file existence. |
| Model hash phase seems slow | Weight files are being read for cache validity | Allow the disk read to finish; stages hash local model files before deciding reuse. This is not stalled GPU inference. |
| Quiet speech disappears | VAD exclusions, clipping or low amplitude | Use `whisper_vad: false`, check full 30-second windows and the corresponding Qwen chunk; a gain-adjusted analysis copy can assist, but keep original audio. |
| Silence produces plausible sentences | ASR hallucination | Compare both recognizers, no-speech/log-probability fields, audio and visible context. Mark unresolved speech; remove only after review. |
| Chinese unexpectedly becomes English | Translate mode or forced language/prompt | Keep `task=transcribe`, auto language and no topic prompt; inspect the raw output before translation. |
| Someone's name changes between models | Ambiguous pronunciation or contextual prompt bias | Replay a short segment and check visible spelling. Keep uncertainty; do not insert a client glossary into a public repository. |
| Number of voice groups seems wrong | Clustering, overlap and short speech | Inspect intervals and reassignment manually. Groups are not identities; short/overlapping voices may be merged or split. |
| `fuse` fails because JSON is missing | Upstream stage not completed | Run missing whisper/qwen/diar stages first; check status/fingerprint and non-empty files. |
| Wrong time after forced alignment | Unreviewed wording, unsupported language or weak audio | Correct text first, inspect word boundaries/zero spans; unsupported languages are skipped. Alignment does not identify speakers. |
| A study-video cue overflows | A whole 30-second ASR window is too long | Split using word/clause timestamps and retain all words; the renderer refuses to silently clip long cues. |
| The last picture ends before the audio | Still-image/VFR timestamps were not held | Use the current FPS resampling/final-card hold and inspect `video_covers_audio` in QA; container duration alone can be misleading. |
| Font boxes appear instead of Chinese | Font lacks CJK glyphs | Select an installed bilingual font; inspect a dense bilingual card before a long render. |
| MP4 rejects PCM audio | Container does not support that codec for stream copy | Use MKV for PCM or choose another compatible container. Do not silently re-encode when preserving audio is required. |
| Copied AAC packet hashes match but PCM differs | Priming/skip-sample metadata changed during muxing | Try MP4 with original AAC; inspect QA and first/last decoded samples. Stream copy alone does not prove identical playback timing. |
| Translation response is reordered/incomplete | Model output/schema mismatch | The client rejects ids/order/empty content. Verify service/model name and JSON mode; retry only bounded attempts and inspect the short sample. |
| Loopback translation port unavailable | Server did not start, wrong port, WSL forwarding | Query `/v1/models` from the calling OS, confirm served name and endpoint; fix routing before translating real material. |
| Tiny settings popup is missing from sampled frames | A brief, low-change transition was deduplicated | Replay the specific interval; add a direct frame at the popup timestamp. OCR confidence alone does not certify the button location. |
| OCR reads a domain, number or amount incorrectly | Blur, small font or compression | Inspect the original-size PNG and original video; compare speech and OCR; do not guess. |
| Word/PPT text is clipped | Too much text, image/caption size or font substitution | Split steps, resize images without obscuring text and inspect every exported page/slide. File integrity is not visual QA. |
| PowerShell continuation command fails | Bash backslash copied into PowerShell | Use a single-line command or PowerShell backtick. Commands in README identify the shell. |
| Old progress never changes | An abandoned recipe process/state file | Inspect the real process; use the new bounded CLI path. Do not repeatedly poll old task files. |

### Commands worth keeping

```bash
python -m pip check
python -c "import sys; print(sys.executable)"
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
ffprobe -v error -show_streams -show_format -of json input/example.mp4
ffmpeg -v error -xerror -i outputs/example/study.mkv -f null -
```

Logs can contain source filenames, text and environment paths. Share a minimal synthetic reproduction, package versions and redacted errors when opening an issue.

## 简体中文

先看state.json中失败的阶段，修好再继续下游。保留原媒体和模型输出，在独立审校副本修改文字。

| 现象 | 重点原因 | 操作与成功判断 |
|---|---|---|
| 复制的venv找不到Python | 仍指向旧解释器 | 用当前Python新建环境，打印sys.executable后重新安装。 |
| 找不到media-workbench | 未装基础包或环境错误 | 用venv中的exe直接运行；pip show确认包存在，--help能显示命令。 |
| 找不到FFmpeg/ffprobe | PATH或配置错误 | 两个位置都核对，带空格路径加引号，各自-version成功。 |
| 识别到了另一条配音 | 第一音轨不是所需轨道 | ffprobe检查轨道，对所需轨使用-map另行提取；原文件不覆盖。 |
| nvidia-smi有GPU但torch不可用 | CPU wheel、驱动/运行时不匹配 | 按官方安装对应torch，在CLI相同环境检查CUDA。 |
| CTranslate2缺cuDNN/cuBLAS | 库依赖与torch不同 | 按faster-whisper说明准备库，启动Python前设置DLL/动态库路径。 |
| 显存不足 | 批次过大或并发模型争抢 | 16、8、4、2、1逐级减小，GPU阶段顺序运行；持续OOM仍应报错。 |
| Whisper找不到model.bin | 下载了Transformers格式 | 使用CTranslate2格式并检查配置、tokenizer和model.bin。 |
| Qwen加载失败 | 模型缺文件或依赖不匹配 | 检查全部分片、tokenizer、qwen-asr和transformers版本。 |
| 说话人缓存缺失 | 根目录或ID层级错误 | 按配置的同一cache运行下载脚本，检查完整ID目录的configuration.json及权重。 |
| 聚类缺fastcluster | 上游未完整声明可选依赖 | 安装本项目当前diar扩展，已显式加入fastcluster；不要覆盖安装旧vendor的requirements。 |
| 本地正常但上传副本缺CAMPPlus | 未限定根目录的models/规则误排除架构代码 | 私人权重用/models/忽略，vendor中模型架构.py必须跟踪；检查Git树而不只看硬盘文件。 |
| 离线仍想下载说话人模型 | ModelScope缓存不足 | HF离线标记不等于阻止ModelScope网络访问，应先完整准备模型。 |
| 换模型后文字仍不变 | 旧recipe缓存或服务标识未变 | 使用CLI内容指纹；翻译服务更换模型后更新配置名。 |
| 哈希阶段较慢 | 正在读取大权重文件 | 等待磁盘读取完成，不误判为GPU卡住。 |
| 低声被漏掉 | VAD、音量或剪裁 | 关闭VAD，逐30秒窗口和Qwen块回查；增益仅用于分析副本。 |
| 静音出现合理句子 | 幻听 | 对照两路、no-speech/概率和原声，不能直接接受。 |
| 中文变英文 | 错用translate或语言提示 | 保持transcribe、自动语种和无主题prompt。 |
| 专名错写 | 发音不清或提示偏差 | 短片段回听并核对画面拼写，保留待核，不补造客户词表。 |
| 声音编号数量不对 | 聚类及重叠导致合并/拆分 | 人工检查区间，编号不等于人物身份或真实人数。 |
| fuse找不到JSON | 上游未成功 | 先完成whisper、qwen、diar，检查有效结果。 |
| 对齐漂移、零时长 | 原文未审或语种不支持 | 先审文字，再检查边界；不支持语种跳过。 |
| 学习字幕一页装不下 | 一整块口述过长 | 按词/句时间拆分并保留全部内容，不能静默裁掉。 |
| 中文显示方框 | 字体不支持中文 | 选支持CJK的中英文字体，先看密集样片。 |
| PCM不能写MP4 | 容器不兼容复制音轨 | PCM选MKV，保原声时不能自动重编码。 |
| AAC包相同但PCM不同 | 封装丢预卷/跳过采样信息 | 尝试原AAC写MP4，并核对QA及首尾采样。 |
| 翻译乱序、漏项 | 返回结构/模型能力不匹配 | 客户端拒绝错误id与空内容，先核验服务和短样例。 |
| 本地翻译端口不通 | 服务未启动、端口或WSL转发问题 | 从调用系统查询/v1/models及模型名。 |
| 抽帧漏短弹窗 | 小变化画面去重 | 回看对应区间，补精确时间帧。 |
| OCR金额、域名错 | 小字、模糊或压缩 | 原尺寸PNG、原视频及语音一起核对。 |
| Word/PPT裁切 | 内容、配图或字体替换 | 拆步骤并逐页审阅，文件可打开不等于排版通过。 |
| PowerShell续行报错 | 复制了Bash反斜杠 | 使用单行命令或PowerShell反引号。 |
| 旧进度不更新 | 孤立recipe进程/状态 | 检查真实进程，转用有时限主CLI，不无限等旧状态。 |

日志可能含输入名、原话和环境路径。提交issue时使用合成最小复现、版本信息和脱敏错误。
