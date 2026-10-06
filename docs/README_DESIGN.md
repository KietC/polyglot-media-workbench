# README structure references / README格式参考

## English

The README organization was researched on 2026-10-05 against three related public projects:

| Repository | Stars observed via GitHub API | Structure adopted |
|---|---:|---|
| [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 25,718 | Requirements → GPU details → installation → usage → configuration/performance |
| [m-bain/whisperX](https://github.com/m-bain/whisperX) | 24,375 | Clear capabilities → install choices → diarization prerequisites → limitations |
| [QwenLM/Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) | 3,647 | Quickstart → backend/model preparation → concrete examples → deployment |

Star counts are a dated observation, not quality certification. We adopted organization, not project claims, benchmarks or author voice. This project's text and examples are written for its own implemented commands. English precedes Chinese in the root README and all project guides. Detailed setup and pitfalls live in linked documents so the README remains navigable.

Markdown rules: meaningful heading hierarchy; blank lines around lists/fenced code; language tags on code; relative links for repository files; absolute HTTPS links for upstream docs; tables for parameter comparison; a small Mermaid flow for module relationships. Badges link to this repository's own license/workflow and do not imply upstream affiliation.

## 简体中文

2026-10-05参考了上表三个相关高星项目。借鉴的是“功能、依赖、安装、最小示例、完整用法、局限和排错”的组织顺序，不复制项目宣传、性能数据或作者口吻。星数是当日观察，不代表质量认证。

本项目正文和示例对应自身实际命令，README及指南均英文在前、中文在后。详细配置与踩坑独立成MD并在README链接。Markdown使用清楚层级、代码语言标记、列表空行、仓库相对链接和官方HTTPS链接；参数用表格，关系用小型Mermaid图。徽章仅链接本仓库许可和工作流。
