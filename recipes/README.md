# Expanded reference algorithms / 扩展算法参考

## English

These files preserve detailed versions of earlier processing algorithms after removing task data and machine-specific bindings. The supported installation path is the root README and `media-workbench` CLI. Recipes are reference material and retain older directory contracts, filename conventions and some incomplete cache/wait behavior.

| Folder | Preserved mechanics |
|---|---|
| `legacy` | Shared pipeline, preflight, time formatting, two ASR paths, speaker process, delivery records |
| `multilingual` | 30-second auto-language recognition, word-window comparison and review flags |
| `learning_video` | Conservative wording selection, stronger full-model relistening, forced word alignment, clause grouping, translation review, original-audio hashes, historical detailed renderer |
| `vision` | PyAV all-frame scene changes, periodic candidates, dHash/delta deduplication, CPU-parallel OCR |

The files use generic environment settings such as `WORKBENCH_TASK_ROOT`, `WORKBENCH_MODEL_ROOT` and `WORKBENCH_FONT`. Private source mappings, glossaries, image mappings and manual dialogue patches have been removed. Recreate those locally from your own authorized input when studying a recipe. Some recipes have top-level initialization; inspect the file instead of importing it for a syntax check. The main CLI replaces infinite upstream-file waits with explicit prerequisites/failures and stronger fingerprints.

## 简体中文

这里保留较完整的历史算法，已移除任务数据和个人机器绑定。正式配置和运行入口是根README与media-workbench。参考脚本仍有旧目录/文件命名约定及部分较弱的缓存、等待行为，不能把它们全部当成主CLI的当前运行接口。

legacy保留共享流程，multilingual保留30秒自动语种对照，learning_video保留复听、保守文本选择、对齐、分句、翻译审查及详细原声渲染，vision保留PyAV、场景/dHash去重及并行OCR。

使用通用WORKBENCH环境配置，私人音源映射、词表、图片映射和手工原话修订已剥离。研究时在本地为自己的输入配置。有些脚本导入即初始化，语法检查不要直接import。主CLI以明确前置依赖/失败取代无限等待，并增加内容指纹。
