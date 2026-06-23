# Security Policy

## 数据边界

本仓库只存放 NoBusy 别虾忙｜AI 管理实战的 WorkBuddy Skill 源码、说明文档和示例配置。

禁止提交：

- 邮箱地址、授权码、密码、Token、Cookie、API Key；
- `config.py`、`.env`、证书、密钥文件；
- 真实发票、报销单、Excel 台账、PDF/OFD 附件；
- 真实个人、真实组织、真实审批系统或真实业务数据；
- WorkBuddy 内部目录、部署备份和本地缓存。

## 配置规则

- 本地配置使用 `config.py` 或用户本地配置文件；
- 仓库只保留 `config_template.py`；
- 示例数据必须使用虚构内容；
- 发布前必须执行敏感信息扫描。

## 发布前检查

```bash
git status --short
python3 -m py_compile scripts/invoice-trip-organizer/*.py
rg -n "EMAIL_AUTH_CODE|YOUR_AUTH_CODE|/Users/|真实姓名|真实组织|真实路径|password|token|secret" .
find . -name ".DS_Store" -o -name "__pycache__" -o -name "config.py" -o -name "*.zip"
```

命中 `config.py`、压缩包、真实数据或敏感信息时，不允许提交或发布。

