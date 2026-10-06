# Third-party notices / 第三方声明

## English

The first-party implementation, generic recipes and project documentation are provided under the root MIT license. `vendor/3d-speaker` contains upstream Python source from [3D-Speaker](https://github.com/modelscope/3D-Speaker); its Apache-2.0 license and copyright headers remain in place. The vendored `infer_diarization.py` cache default was modified to use a generic environment variable and portable fallback. Its original upstream requirements are preserved for reference; they are not the current project's installation lock.

Dependencies/models are not redistributed here. faster-whisper, Qwen ASR/ForcedAligner, InternVL, RapidOCR, PyTorch, FFmpeg, vLLM, python-docx and python-pptx retain their own licenses. Check the selected model card and dependency release before redistribution. Model names and citations are attribution, not affiliation. No proprietary font or desktop application runtime is included.

## 简体中文

主实现、通用参考脚本和本项目文档采用根目录MIT许可。vendor/3d-speaker来自上游3D-Speaker，保留Apache-2.0许可及版权头；infer_diarization.py仅将缓存默认配置改为通用环境变量及可移植位置。保留的上游requirements为参考，不是本项目当前安装锁文件。

依赖和模型不随包分发，各自适用许可。重新分发前查看所选模型卡及依赖版本。上游名称用于归属说明，不表示合作关系。仓库不包含专有字体或桌面软件运行时。
