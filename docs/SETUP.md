# Setup and complete operating order / 配置与完整执行顺序

## English

### 1. Choose a supported interpreter

Use Python 3.10–3.12. Python 3.12 is the primary documented path. Confirm `python --version` and `python -c "import sys; print(sys.executable)"` before installing anything. A copied virtual environment may still point to the Python that created it; recreate it with the current interpreter rather than copying another computer's `.venv`.

Create a new environment in this checkout, activate it, then confirm that the executable is inside `.venv`. If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` directly for pip and `.\.venv\Scripts\media-workbench.exe` for the CLI. You do not have to change the global execution policy.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\media-workbench.exe --help
```

Linux/macOS equivalents are `.venv/bin/python` and `.venv/bin/media-workbench`. GPU branches are primarily intended for NVIDIA CUDA on Windows/Linux; CPU Whisper is available with `device: cpu` and `whisper_compute_type: int8`. A full Qwen CPU run can be slow.

### 2. Install and test FFmpeg

Use the [official FFmpeg download page](https://ffmpeg.org/download.html) or your operating system's package manager. Put `ffmpeg` and `ffprobe` in PATH, or specify their executable paths in your local JSON. Both tools are required.

```bash
ffmpeg -version
ffprobe -version
```

A browser-playable file is not proof that a downloaded file is complete. For a selected input, inspect its streams and optionally perform a complete decode:

```bash
ffprobe -v error -show_format -show_streams -of json input/example.wav
ffmpeg -v error -xerror -i input/example.wav -f null -
```

The main CLI uses the first audio stream `0:a:0`. If your video has commentary on another track, extract that track explicitly first; see the pitfalls guide.

### 3. Install the PyTorch build before ASR extras

Select the command for your platform/GPU from [PyTorch's official selector](https://pytorch.org/get-started/locally/). For a CUDA 12.8 setup, this is a documented starting point, not a command for every machine:

```bash
python -m pip install torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu128
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
```

Confirm that torch, torchaudio and torchvision resolve to compatible releases. Do not force an old torchaudio alongside a new torch. The NVIDIA driver must support the CUDA runtime being installed. For newer GPUs, very old wheels may not contain the required architecture.

### 4. Install task extras and inspect conflicts

```bash
python -m pip install -e ".[asr,diar,vision,documents,download]"
python -m pip check
```

For a smaller setup choose only `.[asr]`, `.[vision]`, `.[documents]` or `.[download]`. The all-components path includes large dependencies. ASR uses `qwen-asr==0.0.6` and its matching `transformers==4.57.6` contract. The version ranges for other optional packages are installation guidance, not a universal lockfile. After a working setup, record `python -m pip freeze` locally for that machine.

CTranslate2 may need CUDA 12 cuBLAS and cuDNN 9 libraries independently of torch. Follow [faster-whisper's GPU instructions](https://github.com/SYSTRAN/faster-whisper#gpu) for the selected CTranslate2 version. Windows needs the DLL directories visible before Python loads the engine. Linux needs the library search path set before starting Python. A successful torch CUDA check does not test CTranslate2.

The Windows Whisper branch automatically exposes installed `torch/lib`, `nvidia/cublas/bin` and `nvidia/cudnn/bin` directories to **that process only**; it does not install CUDA or change system PATH. If the libraries are absent, install the required runtime rather than copying arbitrary DLLs into Windows system folders. On Linux, one explicit setup is:

```bash
python -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
export LD_LIBRARY_PATH="$(python -c 'import os,nvidia.cublas.lib,nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__)+":"+os.path.dirname(nvidia.cudnn.lib.__file__))'):${LD_LIBRARY_PATH:-}"
```

Run this in the same shell before starting the CLI. Library versions must match the selected CTranslate2 release.

### 5. Download models as a separate, explicit preparation step

Install the Hugging Face CLI if needed, then download compatible checkpoints into the folders used by the example config. Model downloads involve network access; normal inference with `offline: true` uses local paths.

```bash
python -m pip install "huggingface_hub>=0.34,<1"
hf download mobiuslabsgmbh/faster-whisper-large-v3-turbo --local-dir models/whisper-turbo
hf download Qwen/Qwen3-ASR-1.7B --local-dir models/qwen-asr
hf download Qwen/Qwen3-ForcedAligner-0.6B --local-dir models/forced-aligner
hf download OpenGVLab/InternVL3-2B --local-dir models/internvl
```

Whisper requires **CTranslate2** weights; an `openai/whisper-*` Transformers checkpoint is not directly interchangeable. Qwen requires its full checkpoint, tokenizer and configuration. The aligner and vision checkpoint are needed only for their corresponding commands. Inspect the model card/license and any custom Python code before enabling `trust_remote_code` in the vision branch.

Prepare 3D-Speaker cache explicitly:

```bash
python scripts/download_speaker_models.py --cache models/speaker-cache
```

This retrieves CAMPPlus `iic/speech_campplus_sv_zh_en_16k-common_advanced` and FSMN VAD `iic/speech_fsmn_vad_zh-cn-16k-common-pytorch`. The cache path must contain the model-id hierarchy and each model's `configuration.json`; the script writes a machine-local inventory. Do not rely on HF offline flags to block ModelScope downloads.

### 6. Configure paths and limits

Copy `config.example.json` to `local_config.json`. Place it at the repository root for the examples below. **Relative model/cache paths resolve from the config file's directory.** Moving the config into `config/` without updating paths moves the expected model folders too.

| Setting | Meaning and initial choice |
|---|---|
| `ffmpeg`, `ffprobe` | Commands in PATH or explicit executable paths |
| `device` | `cuda` for a supported NVIDIA GPU, `cpu` for CPU |
| `models.whisper/qwen/aligner/vision` | Actual local checkpoint directories |
| `speaker_cache` | ModelScope cache root, not one individual checkpoint |
| `speaker_repo` | Optional path to vendored 3D-Speaker when installed from a wheel outside the checkout |
| `cpu_threads` | Start at 8; avoid launching many libraries each using every core |
| `batch_size` | Start at 16 on a sufficiently large GPU; try 8, 4, 2, 1 after OOM |
| `chunk_seconds` | Positive integer, default 30; short windows preserve multilingual checks |
| `whisper_compute_type` | `float16` on CUDA; `int8` for a CPU starting point |
| `whisper_vad` | False uses full-duration windows; true can save silence but may omit quiet speech |
| `command_timeout` | Seconds for FFmpeg and speaker subprocesses; default 14400 |
| `offline` | True requires preexisting local models; acquisition scripts remain explicit network tools |
| `translation.url` | Loopback `/v1/chat/completions` URL only |
| `translation.model` | Exact served model name, default `local-translator` |
| `translation.timeout` | Per-request seconds; bounded retries are three attempts |

Run `media-workbench --config local_config.json doctor`. Inspect tools, packages, CUDA and the model folders needed for your command. Optional aligner/vision folders can be absent when you are not using those stages. `doctor` is an inventory, not an accuracy test or a guarantee that all model kernels load.

### 7. Start from a short test clip

Keep `input/` separate from `outputs/`. Use a short synthetic or otherwise non-sensitive clip to verify the environment. All input paths with spaces should be quoted.

```bash
media-workbench --config local_config.json run --input "input/example.wav" --output outputs/example --stages whisper qwen
```

Open `whisper.json` and `qwen.json`: confirm non-empty text, plausible timing, original languages and the expected duration. If one engine fails, inspect `state.json`, fix that engine, and rerun the same stages. Successful stages with matching fingerprints will be reused. A changed input, model, config, code or installed recognition package invalidates the cache.

### 8. Complete diarization and comparison

```bash
media-workbench --config local_config.json run --input input/example.wav --output outputs/example --stages diar fuse export
```

`diar.json` lists voice intervals. `fuse.json` lists each Qwen window with Whisper comparison, language, speaker group, difference score and review flag. `transcript.md` keeps the recognizers distinguishable. Speaker IDs apply only within this recording; a `SPEAKER_00` in two files is not evidence of the same person. The grouping is automatic, including the number of groups.

Check openings, endings, quiet speech, overlapping voices, long silence, names, numbers, units, negations and every flagged difference. Automatic language detection and a similarity threshold are helpful triage, not a final editorial decision. Save corrections in a separate reviewed JSON and keep raw model results.

### 9. Align reviewed wording when required

The aligner needs audio and the exact text to align. For the generic CLI, `align` reads `fuse.json`; if editing its `original` fields, preserve a raw copy first and maintain the ids/times. Qwen forced alignment supports fewer languages than ASR; unsupported languages are marked skipped.

```bash
media-workbench --config local_config.json run --input input/example.wav --output outputs/example --stages align
```

Review zero-duration words, boundary spill and punctuation. The result is `align.json`; it still has pending review. A sentence-level 30-second chunk may be too long for a readable video card. Split it using word boundaries or clause times before producing study video, keeping the original timing and all substantive text. Do not use a fixed arbitrary split for fast speech.

### 10. Extract frames, OCR and interpret screenshots

```bash
media-workbench --config local_config.json frames --input input/video.mp4 --output outputs/frames --interval 1 --ocr
media-workbench --config local_config.json vision --frames outputs/frames/frames.json
```

The extractor checks every decoded frame for scene changes and uses interval candidates plus conservative deduplication. PNG preserves decoded pixels without another JPEG compression pass. OCR stores text, boxes and confidence. Vision descriptions use the local InternVL checkpoint; they record what is visible and remain pending review. Use `timestamp` to associate a frame with the spoken unit. For brief popups, check the video directly and extract extra frames around that time.

The `vision` extra includes its own Transformers, Accelerate, timm, einops and SentencePiece dependencies; it can be installed without the ASR extra. The documented model uses the [upstream InternVL3 model interface](https://huggingface.co/OpenGVLab/InternVL3-2B). A model that exposes a different chat API is not a drop-in replacement. GPU inference is the intended path; a full BF16 vision run on CPU may be unsupported or slow.

Review screenshots before sharing: hide passwords, verification codes, full account identifiers, card information, subscription links and eSIM QR codes. The generic extractor does not automatically redact every secret.

### 11. Prepare a local translation service

Use a separate Linux/WSL environment for vLLM if necessary. The core ASR environment does not need vLLM. Prepare a suitable local checkpoint, then bind the service to loopback:

```bash
# Linux / WSL, in a separate environment:
python3 -m venv .venv-translation
source .venv-translation/bin/activate
python -m pip install --upgrade pip
python -m pip install vllm
hf download Qwen/Qwen3-8B --local-dir models/local-translator
vllm serve models/local-translator --host 127.0.0.1 --port 5127 --served-model-name local-translator --gpu-memory-utilization 0.65 --max-model-len 8192
```

Use the [official vLLM platform instructions](https://docs.vllm.ai/en/stable/getting_started/installation/gpu/) when its wheel does not match your OS, GPU or driver; do not install vLLM into the ASR environment to solve that mismatch. `Qwen3-8B` is a starting choice, not a quality benchmark or a minimum-memory guarantee. Install `huggingface_hub` in this separate environment if `hf` is unavailable. Stop other GPU models before serving; lower the context/memory allocation if needed.

Query `http://127.0.0.1:5127/v1/models` with curl (or PowerShell `Invoke-RestMethod`) **from the OS running the workbench**, and confirm `local-translator` appears. Keep the service terminal open while translating. WSL port forwarding must be working; do not solve it by exposing a private translation service on `0.0.0.0`. Ensure the service supports the chat-completions shape, JSON object output and the chat-template options used by your model. Change the config's `translation.model` to the exact served name. A failed or unsupported response must be corrected before full translation.

```bash
media-workbench --config local_config.json translate --input outputs/example/fuse.json --output outputs/example/translated.json
```

Translations preserve ids/order and cannot merge phrases. Review figures, negative statements, incomplete sentences, ambiguous technical terms and Cantonese-to-Mandarin expression against the original audio. Keep the original text next to the reviewed `zh`. For a changed model or service behavior, update the configured model identifier so the translation cache does not reuse a previous model's output.

### 12. Make a 4K original-audio learning video

Use the reviewed cue JSON with `units`, including `id/start/end/speaker/language/original/zh`. Use `examples/cues.json` only with a matching synthetic two-second test input. Choose a font that actually supports both Latin and Chinese glyphs; this repository does not distribute proprietary fonts.

```bash
media-workbench --config local_config.json study-video --input input/example.wav --cues outputs/example/translated.json --output outputs/example/study.mkv --font /path/to/bilingual-font.ttf
```

Optionally supply an assets file shaped like `examples/assets.json`, with local term explanations and image time ranges. Relative image paths resolve from that assets file. Explanations are sidebar notes, not invented spoken text. The video is 3840×2160, 16:9, 25 fps. New dialogue sits at the bottom; old dialogue remains above until space runs out. English/German display original plus Chinese; Cantonese displays reviewed Mandarin while the original audio stays unchanged.

Select `h264_nvenc` to encode video on NVIDIA hardware, or use default `libx264`. Audio always uses stream copy. PCM WAV audio normally needs MKV; AAC source often needs MP4 to retain priming/skip-sample behavior. Inspect the adjacent `.qa.json`; a failed packet/PCM comparison makes the command fail. Also decode the full finished video and inspect its first, last and dense-dialogue frames. Do not equate a hash check with a complete visual layout review.

The QA also checks the **video packet end time**, not just the container duration, so an audio track cannot hide a prematurely ending last card. With `.[documents]` installed, `python scripts/smoke_media.py --font /path/to/bilingual-font.ttf` reproduces the two-second synthetic 4K/audio test before a long render.

### 13. Produce reviewed MD, Word and PowerPoint

Write content using the `examples/content.json` schema. Each section contains a title, full paragraphs, local figure paths/captions and optional source text. This is editorial material, not an automatic summary of the raw ASR output.

```bash
media-workbench documents --content examples/content.json --output outputs/documents
```

The shared data produces `tutorial.md`, `tutorial.docx` and `tutorial.pptx`. Split long teaching paragraphs into clear steps; the exporter rejects paragraphs over 650 characters. First slides can show a corresponding image; further section figures receive their own slides. Pictures are aspect-fitted, captions remain visible, and Markdown gets its own `assets/` copies rather than broken links back to the input folder. Necessary steps remain in the visible slide body. Review every Word page and every slide, especially long captions, wide/tall images, page breaks and non-Latin text. On Windows with Office installed, use `scripts/export_office.ps1` for native PDF/slide export. Office is optional; source generation uses python-docx/python-pptx.

### 14. Resume and retain records

Re-run the same command after fixing the cause of a failure. The pipeline does not poll abandoned progress files indefinitely. Check the current process and `state.json`, which records failed stages explicitly. Do not overwrite the original source with an analysis copy, edited transcript or rendered video. Keep input/output checksums, review notes and your machine's environment lock locally; generated records do not belong in a public code repository.

## 简体中文

### 1. 先确认Python

使用Python 3.10–3.12，文档以3.12为主。执行`python --version`和`python -c "import sys; print(sys.executable)"`，确认实际解释器。复制来的虚拟环境可能仍指向创建它的旧Python，应该用当前解释器重新创建环境。

按照英文第1节的PowerShell命令创建`.venv`。若激活被阻止，可以直接使用`.venv/Scripts/python.exe`及`media-workbench.exe`，不必修改全局执行策略。Linux/macOS对应`.venv/bin/`。CUDA分支主要针对Windows/Linux上的NVIDIA硬件，CPU Whisper可配置`device: cpu`和`whisper_compute_type: int8`；完整Qwen CPU识别可能较慢。

### 2. 再准备FFmpeg

安装FFmpeg与ffprobe，将它们加入PATH或在配置中填写可执行文件位置。分别运行`ffmpeg -version`和`ffprobe -version`。输入需能读取音轨和有效时长；网页可播放不证明下载文件完整。英文第2节给出了探测与完整解码命令。

主CLI选择第一音轨`0:a:0`。多音轨视频若所需讲话位于其他轨道，先明确提取该轨道。

### 3. 先安装匹配的PyTorch

根据官方选择器确定系统、GPU及CUDA对应命令。英文示例是CUDA12.8起点，不适合所有设备。安装后检查torch版本、torch.version.cuda和torch.cuda.is_available()；torch、torchaudio、torchvision应为兼容版本。驱动必须支持所选运行时，新GPU不要使用缺少该架构的过旧wheel。

### 4. 再安装扩展依赖

执行`python -m pip install -e ".[asr,diar,vision,documents,download]"`，随后`python -m pip check`。按任务可只安装某个扩展。Qwen固定使用`qwen-asr==0.0.6`及其匹配的`transformers==4.57.6`。其他版本范围是配置依据，不代表所有平台均验证；环境跑通后在本地保存pip freeze。

CTranslate2可能单独需要cuBLAS和cuDNN9。按faster-whisper官方说明配置。Windows在启动Python前让DLL目录可见，Linux在启动前设置动态库搜索路径。torch能使用CUDA，不代表CTranslate2也能加载。

Windows Whisper会为当前进程自动查找已安装的torch/lib及nvidia下的cuBLAS/cuDNN目录，不修改系统PATH，也不安装CUDA。缺库时按版本安装所需运行时，不要向系统目录乱放DLL。Linux的安装和LD_LIBRARY_PATH命令见英文第4节，必须在启动CLI的同一shell执行。

### 5. 单独下载模型

英文第5节提供hf下载命令。Whisper必须是CTranslate2格式，不可直接把Transformers格式当成同一种模型。Qwen需要完整权重、配置和tokenizer。强制对齐、InternVL只在相应功能需要时下载。识图启用trust_remote_code前先检查模型自定义代码及模型许可。

运行`python scripts/download_speaker_models.py --cache models/speaker-cache`明确下载CAMPPlus与FSMN VAD。缓存要包含模型ID层级和configuration.json，不是随便一个权重文件。HF离线变量不能自动阻止ModelScope下载。

### 6. 配置路径与参数

将config.example.json复制为local_config.json，示例放在仓库根目录。相对模型路径按配置文件所在目录解析；移动配置文件也会改变预期模型位置。参数含义见英文第6节表格。

初始cpu_threads=8、batch_size=16、chunk_seconds=30。显存不足依次减为8、4、2、1。低声场景默认关闭Whisper VAD；开启后需特别检查漏掉的弱语音。command_timeout为子进程秒数。翻译只连接本机回环地址。执行doctor核对本任务需要的工具、包、CUDA和模型，未使用的可选模型缺失可以暂不处理。

### 7. 先试短音频

输入和输出分开放，带空格路径用引号。先运行`--stages whisper qwen`，查看文字、语种、时长及时间轴。某路失败时查看state.json，解决后重跑相同命令。输入、模型、配置、实现代码、依赖变化均影响缓存；文件存在不等于有效断点。

### 8. 完成声音分组与双路对照

再运行`--stages diar fuse export`。diar.json为声音区间，fuse.json为Qwen块与Whisper原话对照及待核标记，transcript.md保留两路区别。编号仅表示本录音的声音簇，不自动推断人数或跨音源人物身份。

复核开头、结尾、低声、重叠、长静音、专名、数字、单位、否定及所有分歧。保存独立审校副本，保留模型底稿。

### 9. 需要时强制对齐

对齐器读取fuse.json中的文字及音频。修改original前保留底稿和id/时间。对齐支持语种少于ASR，不支持的会标记跳过。运行`--stages align`后查看align.json，检查零时长词、边界溢出及标点。它仍然需要审校。

长达30秒的口述块可能无法放进一张学习卡片，需要依据词或子句时间拆开，保留全部实质内容。不能凭固定字符数随意猜时间。

### 10. 抽帧、OCR与识图

按英文第10节执行frames与vision。抽帧逐帧检查场景变化，并补间隔候选、去除近似重复。PNG不再增加JPEG损失。OCR保留框、文字和置信度；识图描述待核。用timestamp与讲话对齐。短暂弹窗不足时，回看原视频并在对应区间补帧。

vision扩展已单独声明Transformers、Accelerate、timm、einops及SentencePiece，不必为了识图安装ASR扩展。使用文档对应的InternVL3接口；其他模型的chat接口可能不兼容。GPU是预期路径，CPU BF16可能不支持或很慢。

分享截图前遮住密码、验证码、完整账户、卡信息、订阅链接和eSIM二维码。抽帧器不能自动覆盖所有敏感内容。

### 11. 本地翻译

需要时在Linux/WSL单独部署vLLM，不把它装进核心ASR环境。将服务绑定127.0.0.1、端口5127，served-model-name与配置完全一致。检查/v1/models及chat-completions、JSON输出和模型模板参数支持情况后再翻译完整文件。

英文第11节给出独立venv、安装vLLM、下载Qwen3-8B、启动服务的完整命令。8B只是起点，不保证任何显存都足够。启动前释放其他模型，必要时降低上下文及显存比例；轮子不匹配时按vLLM官方平台说明解决。缺hf命令时在翻译环境单独安装huggingface_hub。

从运行workbench的系统查询http://127.0.0.1:5127/v1/models，确认local-translator，再保持服务终端开启。WSL端口转发需可用；不要为省事把私人翻译服务暴露到0.0.0.0。

translate保持id和顺序，不合并语句。核对数字、否定、不完整句、术语和粤语转普通话表达，保留原文与审校zh。替换服务模型时同步更新配置模型标识，避免命中旧翻译缓存。

### 12. 4K原声学习视频

字幕结构见examples/cues.json；它是两秒合成示例，只能与匹配的测试音源搭配。正式视频使用审校的id、起止时间、语言、声音编号、原文和中文。选择确实支持中英文的字体。

study-video生成3840×2160、16:9、25fps黑底字幕，新句放下方，旧句向上移动。英语、德语显示原文与中文；粤语显示普通话书面字幕，声音不改变。assets.json可加术语解释及按时间显示的配图，解释属于旁注，不应冒充原话。

可选h264_nvenc加速视频编码，默认libx264。音轨始终复制；PCM通常选MKV，AAC常选MP4以保留预卷信息。查看.qa.json，音频包或PCM不一致会报错。还要完整解码并审看首尾及密集对话画面，哈希通过不代表排版自动通过。

QA还检查实际视频包结尾，而不是仅看容器时长，避免音轨长度掩盖最后画面提前结束。安装documents扩展后，可先用scripts/smoke_media.py和本机字体验证两秒合成4K片。

### 13. Word、PPT和MD

按examples/content.json编写审校正文，包含章节、完整段落、图片与图注。documents由同一正文生成三种格式。超过650字符的段落需拆成教学步骤；关键步骤必须可见，不能只藏备注。

首张配图可与正文同页，章节其他配图单独生成图页；图片按比例完整放入框内，图注可见。Markdown将配图复制到输出assets目录，不留下指向输入文件夹的断链。

检查全部Word页面和PPT幻灯片，特别是长图注、宽高图片、分页与非拉丁文字。Windows安装Office时可用scripts/export_office.ps1原生导出。生成逻辑使用python-docx/python-pptx，Office仅用于可选导出检查。

### 14. 断点和记录

修复失败原因后重跑原命令。程序不无限等旧进度文件；核对真实进程和state.json。原媒体不能被分析音频、修订稿或视频覆盖。输入输出校验、审校记录和本机依赖清单留在本地，生成数据不要放进公开代码仓库。
