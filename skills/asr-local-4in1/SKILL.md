---
name: asr-local-4in1
description: Process local multilingual audio/video with Whisper and Qwen dual ASR, voice grouping and listening review; optionally add frames, OCR, local translation, original-audio study video and reviewed documents.
---

# Local multilingual media workflow / 本地多语种媒体工作流

## English

Read the repository's `docs/SETUP.md` and relevant entries in `docs/TROUBLESHOOTING.md`. Use the configurable `media-workbench` CLI for normal tasks; expanded `recipes/` files require their own directory prerequisites.

- Inspect current input, existing results, real processes, local models and available memory before resuming. Keep original media read-only, and separate analysis copies from delivery media.
- Preserve original English/German and Cantonese source wording. Translate or convert Cantonese into written Mandarin in a separate field. Retain recognizer alternatives and unresolved words.
- Run whisper/qwen/diar/fuse in dependency order, with GPU stages sequential. Use fingerprints covering input/model/parameters; a file's existence is not completion.
- Review starts/ends, quiet/overlapping speech, names, numbers, units, conditions and negations. Scores select listening targets, not certified transcripts. Voice clusters do not identify people or automatically match identities across recordings.
- Add frames/OCR/vision only when relevant, align timestamps and inspect unclear original-size frames. Descriptions must not invent unseen clicks. Redact shared images.
- For learning videos, retain original audio via copy and check packet/PCM signatures. Keep previous dialogue above new dialogue, preserve language-specific caption rules, and place glossary explanations in a separate sidebar.
- Build documents from reviewed unified content; preserve substantive steps, examples and failure explanations. Inspect all pages/slides before claiming visual QA.
- Report processing completion, editorial review and visual/audio verification separately. Keep private inputs, configs, transcripts, media, secrets and company/client data out of a public source repository.

## 简体中文

先读仓库docs/SETUP.md及对应排错条目。正常任务使用配置化media-workbench，recipes需要其旧目录前提。

- 恢复前检查原音源、已有结果、真实进程、本地模型与内存。原媒体只读，分析副本和交付分开。
- 保留英语、德语和粤语底稿，译文/粤语转普通话另存。保留两路候选和听不清内容。
- 按whisper/qwen/diar/fuse依赖执行，GPU阶段顺序运行；缓存绑定输入、模型和参数，文件存在不等于完成。
- 复核首尾、低声、重叠、名称、数字、单位、条件和否定。分数只是回听线索，声音簇不猜身份或跨音源人物。
- 按需抽帧/OCR/识图，对齐时间戳，文字不清回查原尺寸。不猜不可见点击，分享配图先脱敏。
- 学习视频复制原声并核对包/PCM；旧对话在上，新对话在下，术语解释放旁栏。
- 文档用统一审校正文，保留实质步骤、实例和排错，全部页面/幻灯片检查后才报告排版通过。
- 分开报告处理、听校、画面/原声验收；私人媒体、配置、转写、凭据、公司和客户数据不入公开源码库。
