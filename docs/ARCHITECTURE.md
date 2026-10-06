# Architecture and data contracts / 结构与数据约定

## English

`src/media_workbench` is the supported configurable entry. `recipes` keeps expanded reference implementations. `vendor/3d-speaker` contains the optional upstream clustering engine and its license. `skills` contains an agent workflow entry; `tests` uses synthetic input, while `examples` contains invented captions/content only.

| Module | Responsibility |
|---|---|
| `core.py` | Atomic JSON, config paths, bounded subprocesses, hashes/cache, dependency doctor |
| `asr.py` | Read-only source intake, analysis WAV, Whisper/Qwen, diarization, comparison, alignment, MD |
| `vision.py` | Scene/periodic frames, PNG, OCR, local InternVL interpretation |
| `translation.py` | Loopback chat-completions, strict ordered ids, bounded retries |
| `learning_video.py` | 4K rolling dialogue, bilingual/Cantonese captions, term/image sidebar, audio-copy checks |
| `documents.py` | One reviewed JSON schema to MD, Word and PPT |
| `cli.py` | Commands and lazy optional imports |

### Task artifacts

`source.json` binds the original checksum, selected stream, duration, analysis WAV and its checksum. The original file is never an output target. A new source in the same task directory regenerates analysis audio and invalidates recognition checkpoints.

Whisper uses `segments` with `start/end/text/words`. Qwen uses `results` with `start/end/text/language`. Diarization uses `segments` with `start/end/speaker`. Comparison and aligned/translated results use `units`:

```json
{
  "editorial_status": "pending",
  "units": [{
    "id": "U00001", "start": 0.0, "end": 1.0,
    "language": "English", "speaker": "SPEAKER_00",
    "original": "Synthetic example.", "whisper": "Synthetic example.",
    "zh": "合成示例。", "similarity": 1.0, "needs_review": false,
    "words": [{"start": 0.0, "end": 0.5, "word": "Synthetic"}]
  }]
}
```

`status: complete` describes a processing stage. `editorial_status: pending` describes review. Keep both; processing completion must not silently erase review status. Voice IDs are local clusters. Optional identity labels require the user's own supported attribution outside the automatic engine.

### Checkpoints and failures

Fingerprints cover source SHA-256, local model files, config, package versions, current module code and relevant upstream results. Atomic files use unique temporary names. A failed subprocess has a timeout and a nonzero/error state. If a checkpoint is corrupt, it is not reused. Translation model names must change after replacing a server's model because remote service weights cannot be inferred from a URL.

The main pipeline executes GPU recognizers sequentially. It does not launch all models simultaneously or infer completion from an old PID/progress file. Qwen handles OOM by reducing its batch and explicitly checks returned item count. Whisper failures are reported; choose a smaller configured batch before retrying.

### Review boundaries

Machine visual observations do not certify click paths. ASR similarity does not certify fidelity. Alignment does not translate or identify speakers. Generated document files do not certify every page's layout. Rendered video images are encoded; original audio is separately copied and compared using compressed-packet and decoded-PCM hashes.

### Source-only publication

The public tree contains no source recording, real transcript, client glossary, private media/image mappings, device/user paths, cookie, access key, production output or company-specific configuration. Synthetic examples are labelled. Standard upstream model/project names and licenses remain intact. The public copy starts a fresh Git history after scanning so older private paths cannot reappear in earlier commits.

## 简体中文

src/media_workbench是配置化主入口；recipes保存更完整的算法参考；vendor/3d-speaker为可选上游引擎并保留许可；skills为代理工作流入口；tests和examples仅使用合成输入及虚构示例。

core负责配置、原子保存、命令时限、哈希断点和依赖检查；asr负责分析音频、双路识别、声音分组、对照、对齐与MD；vision负责抽帧/OCR/识图；translation负责本机有序翻译；learning_video负责4K滚动对话和原声校验；documents由统一正文生成MD/Word/PPT；cli按需加载可选依赖。

source.json记录原媒体SHA-256、所选音轨、时长、分析副本及其校验值。原文件不作为输出。同目录更换输入后重新生成分析音频，并让旧推理失效。

Whisper使用segments，Qwen使用results，说话人使用带speaker的segments；对照、对齐及翻译使用上面的units结构。status=complete仅表示处理完成，editorial_status=pending仍表示需要审校。声音编号是本音源簇，不自动标记真实身份。

缓存同时绑定输入、模型文件、配置、依赖、代码及上游结果；原子保存使用独立临时文件。子进程失败或超时明确记为failed。GPU阶段顺序执行，Qwen遇OOM减批并检查返回数量；Whisper失败后按配置减批再重试。

识图不证明点击顺序，文本相似不证明转写无误，对齐不等于翻译或身份识别，文档可打开不代表排版已审。视频画面重新编码，原声音轨另行复制并校验音频包和解码PCM。

公开副本排除真实录音、转写、客户词表、私人图片映射、个人路径、cookie、密钥、生产输出及公司特征配置。保留通用上游模型名和许可，示例注明合成。扫描后建立全新Git历史，旧私密路径不会进入过去提交。
