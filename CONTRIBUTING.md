# Contributing / 参与贡献

## English

Use a fresh Python 3.10–3.12 environment. Install `python -m pip install -e ".[dev]"`, then run `python -m unittest discover -s tests -v`, `python scripts/inspect_public_tree.py` and `python -m ruff check src tests`. Optional integrations use their own extras/models; do not require a GPU for unit tests.

Submit a focused change with the triggering input shape, expected/actual behavior and checks performed. Use synthetic media or a minimal invented JSON example. Do not attach private conversations, production logs, credentials or identifying customer data. Preserve English-first/Chinese-second prose and paired explanatory comments. Update setup commands when changing dependencies or configuration.

Keep raw recognizer output, editorial review and derived tutorials distinct. New caches must cover their inputs and parameters. New subprocess calls need argument lists, timeouts and clear failure status. Retain third-party license headers and document modifications to vendored code.

## 简体中文

使用独立Python 3.10–3.12环境，安装dev扩展后执行英文部分的单测、公开目录检查和ruff检查。单测不要求GPU，可选集成另装对应模型和依赖。

提交聚焦的改动，说明触发输入、预期/实际行为及验证结果。使用合成媒体或虚构JSON，不要附真实会话、生产日志、凭据或客户信息。保持英文先、中文后及成对解释性注释，依赖/配置变化同步更新指南。

模型底稿、听校和教程分层。缓存覆盖输入及参数；子进程用参数列表、时限和失败状态。第三方许可头保留，修改须记录。
