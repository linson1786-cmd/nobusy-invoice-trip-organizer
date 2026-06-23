# 个人行程与报销 Skill

> **版本**: V1.0.1  
> **创建日期**: 2026-06-23  
> **项目归属**: NoBusy 别虾忙｜AI 管理实战  
> **负责人**: Linson  
> **License**: MIT

---

## 项目简介

本项目为 WorkBuddy 的 Skill 插件，用于自动化管理个人行程与报销发票。支持发票自动识别、分类、归档，行程自动关联，邮件发票下载，以及完整的版本管理。

## 功能列表

| 功能 | 脚本 | 说明 |
|------|------|------|
| 初始化设置 | `setup.py` | 创建目录结构、生成配置 |
| 发票自动整理 | `invoice_auto_organizer.py` | PDF 识别、分类、归档、台账 |
| 行程自动整理 | `trip_auto_organizer.py` | 创建行程、匹配发票、生成清单 |
| 邮件下载发票 | `download_invoices.py` | IMAP 下载邮件附件 |
| 文件上传 | `upload_files.py` | 弹窗选择文件，自动复制到待分类 |
| 版本管理 | `version_manager.py` | 自动检测、备份、更新 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

> macOS 额外需要：`brew install tesseract`  
> Windows 额外需要：[下载 Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)

### 2. 初始化设置

```bash
cd scripts/invoice-trip-organizer
python3 setup.py init
```

按提示选择存放目录，脚本会自动创建目录结构。

### 3. 配置邮箱（可选）

复制配置模板：

```bash
cp config_template.py config.py
# 编辑 config.py，填写邮箱和授权码
```

### 4. 开始使用

**发票整理**：将发票放入 `01 待分类/`，然后运行：

```bash
python3 invoice_auto_organizer.py
```

**行程管理**：创建行程并关联发票：

```bash
python3 trip_auto_organizer.py
```

---

## 项目结构

```
invoice-trip-organizer/
├── .gitignore              # Git 忽略规则
├── LICENSE                 # MIT 许可证
├── requirements.txt        # Python 依赖
├── README.md              # 本文件
├── SKILL.md               # Skill 触发词文档
├── V1.0-交付说明.md       # 版本交付说明
├── 项目管理体系说明.md     # 项目管理体系
├── scripts/               # 核心脚本（开发工作目录）
│   └── invoice-trip-organizer/
│   └── invoice-trip-organizer/
│       ├── VERSION            # 当前版本 V1.0
│       ├── CHANGELOG.md       # 变更日志
│       ├── setup.py           # 初始化设置
│       ├── init.py            # 入口脚本
│       ├── config_template.py # 配置模板
│       ├── version_manager.py # 版本管理器
│       ├── invoice_auto_organizer.py
│       ├── trip_auto_organizer.py
│       ├── download_invoices.py
│       ├── upload_files.py
│       ├── email_manager.py
│       └── audit_03_done.py
├── 源文件/                # 版本源码归档
├── 交付包/                # 对外发布包
├── 版本归档/              # 历史版本压缩包
├── 项目管理/              # 项目管理文档
│   ├── 版本发布记录/
│   ├── 需求与计划/
│   ├── 测试记录/
│   └── 使用反馈/
└── Templates/             # 模板文件
```

---

## 版本管理

本项目采用 V1.0 / V1.1 版本号格式。每次运行任意脚本时，版本管理器会自动检测更新并备份旧版本。

### 发布新版本

1. 在 `scripts/invoice-trip-organizer/` 中修改代码
2. 更新 `scripts/invoice-trip-organizer/VERSION` 文件
3. 更新 `scripts/invoice-trip-organizer/CHANGELOG.md`
4. 同步到 `源文件/V{version}/` 和 `交付包/V{version}/`
5. 创建归档到 `版本归档/`

---

## Git 提交规范

```bash
# 初始化仓库
git init

# 添加所有文件（config.py 会被 .gitignore 自动忽略）
git add .

# 提交
git commit -m "V1.0: 初始发布"

# 创建标签
git tag v1.0

# 推送到 GitHub
git remote add origin https://github.com/yourusername/invoice-trip-organizer.git
git push -u origin main
git push origin v1.0
```

---

## 注意事项

- `config.py` 包含用户敏感信息（邮箱、路径），已被 `.gitignore` 忽略，不会提交到 Git
- 首次使用请复制 `config_template.py` 为 `config.py` 并填写自己的配置
- 用户数据（发票、台账、行程）独立于代码，更新不受影响

---

*本项目为 NoBusy 别虾忙｜AI 管理实战 对外 Skill 工具。*
