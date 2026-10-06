# Security and private inputs / 安全与私人输入

## English

The local translation client disables environment proxies and HTTP redirects, so a loopback endpoint cannot silently forward a request to another host. This does not make unreviewed local model code trustworthy; inspect custom model code and maintain OS/network controls when stronger isolation is needed.

This project processes user-supplied local files. Keep actual media, transcripts, models, config, logs and generated outputs outside the public tree or in ignored task folders. The ignore file is a secondary safeguard; inspect tracked files before publishing. Do not paste secrets into issue reports.

Inference uses local model paths. Acquisition/model download scripts explicitly access the network. Translation is restricted to loopback; library offline flags are not an OS firewall. Optional custom model code is executable Python and must be reviewed before using `trust_remote_code`.

Report a suspected vulnerability through the repository's GitHub Security Advisory feature if available; otherwise describe the issue without private input or exploit credentials. Include a synthetic reproduction and affected version.

## 简体中文

本地翻译客户端不使用环境代理，也不跟随HTTP重定向，避免回环端点静默将请求转发到其他主机。这不等于未审查的模型自定义代码可信；需要更强隔离时仍应检查模型代码并维护系统与网络控制。

真实媒体、转写、模型、配置、日志和输出放在公开目录之外或已忽略的任务目录。gitignore是辅助措施，发布前检查实际跟踪文件。issue不得粘贴密钥。

推理使用本地模型，获取/下载脚本明确联网；翻译限制在回环地址，库离线标记不等于系统防火墙。模型自定义代码可执行，启用trust_remote_code前先审阅。

漏洞通过可用的GitHub Security Advisory提交，否则只提供不含私人资料的说明、合成复现和受影响版本。
