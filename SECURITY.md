# 安全策略 / Security Policy

## 支持的版本 / Supported versions

本项目处于早期开发(0.x)。仅 `main` 分支与最新 release 会收到安全修复。

## 报告漏洞 / Reporting a vulnerability

**请不要公开提 issue 披露安全问题。** 请通过以下任一方式私下报告:

- 邮件:**wootilehq@gmail.com**
- 或 GitHub 的 **Security → Report a vulnerability**(私密披露)

请尽量附上:复现步骤、影响范围、以及(如有)修复建议。我们会尽快确认并处理。

## 使用须知(重要)/ Usage note

⚠️ QuantMill 是**研究与教育框架,不是交易系统**,内置策略**无经证实的盈利能力**。
- 密钥(Alpaca / Anthropic)只经环境变量或本地 `.alpaca` 文件读取,**永不入库**;请勿在 issue/PR 中粘贴任何密钥。
- 网页台默认仅监听 `127.0.0.1`;**请勿在无鉴权的情况下将其暴露到公网**。
- 任何信号/回测仅供研究,**请勿据此进行真实交易**。
