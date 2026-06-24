# 个人行程与报销 Skill

> **版本**: 见 `scripts/invoice-trip-organizer/VERSION` 文件
> **创建日期**: 2026-06-23  
> **项目归属**: NoBusy 别虾忙｜AI 管理实战  
> **负责人**: Linson  
> **License**: MIT
> **GitHub**: https://github.com/linson1786-cmd/nobusy-invoice-trip-organizer.git

---

## 固定路径

| 类型 | 路径 |
|---|---|
| WorkBuddy 安装目录 | `/Users/linson/.workbuddy/skills/invoice-trip-organizer/` |
| 本地项目目录 | `/Users/linson/Documents/Personage/AI Tools Learning/WorkBuddy Skills/invoice-trip-organizer/` |
| GitHub 仓库 | `linson1786-cmd/nobusy-invoice-trip-organizer` |

分工：

- 本地项目目录：源码开发、版本管理、Git 提交；
- GitHub 仓库：远程版本存档、发布与升级来源；
- WorkBuddy 安装目录：实际运行目录，不作为源码编辑目录。

---

## 项目简介

本项目为 WorkBuddy 的 Skill 插件，用于自动化管理个人行程与报销发票。支持发票自动识别、分类、归档，行程自动关联，邮件发票下载，批量导入行程，文件导入，以及完整的版本管理和在线升级。

## 功能列表

| 功能 | 脚本 | 说明 |
|------|------|------|
| 初始化设置 | `setup.py` | 弹窗选择目录，创建完整目录结构，生成 config.py（已有则保留） |
| 发票自动整理 | `invoice_auto_organizer.py` | PDF/OFD/XML/图片识别、分类、归档、台账 |
| 行程自动整理 | `trip_auto_organizer.py` | 创建行程、匹配发票、生成清单和总览 |
| 邮件下载发票 | `download_invoices.py` | IMAP 下载邮件附件，支持多邮箱 |
| 导入文件 | `upload_files.py` | 弹窗选择文件，自动复制到 01 待分类 |
| 导入行程 | `import_trips.py` | 粘贴 Tab 分隔数据，按日期去重批量创建行程 |
| 在线升级 | `deploy.py` | 从 GitHub 一键升级，自动备份旧版 |
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

在 WorkBuddy 中对我说「初始化设置」，或手动运行：

```bash
cd scripts/invoice-trip-organizer
python3 setup.py init
```

弹窗选择父目录后，脚本自动创建目录结构、复制 SOP 文档、生成 config.py。

自动化测试或无界面环境可指定父目录：

```bash
python3 setup.py init --base-dir /tmp/invoice-trip-demo
```

### 3. 配置邮箱（可选）

运行 `download_invoices.py` 时会弹出邮箱选择/注册界面，账户信息保存在 `~/.invoice-trip/email_accounts.json`，支持多个邮箱。

### 4. 开始使用

**发票整理**：将发票放入 `01 待分类/`，然后对我说「发票整理」或运行：

```bash
python3 invoice_auto_organizer.py
```

**行程管理**：创建行程并关联发票：

```bash
python3 trip_auto_organizer.py
```

**导入行程**：批量粘贴行程数据：

```bash
python3 import_trips.py
```

---

## 在线升级

```bash
# 检查是否有新版本
python3 deploy.py --check-update

# 一键升级到最新版本
python3 deploy.py --upgrade

# 查看当前版本状态
python3 deploy.py --status
```

升级保障：
- 数据安全：仅更新脚本文件，绝不覆盖用户 config.py、发票、行程、台账
- 自动备份：升级前自动备份旧版本到 `.backup/`
- 三重降级：git clone → HTTP ZIP → GitHub API

---

## 项目结构

```
invoice-trip-organizer/
├── .gitignore
├── LICENSE                 # MIT 许可证
├── README.md              # 本文件
├── CHANGELOG.md           # 变更日志
├── SKILL.md               # WorkBuddy Skill 触发词文档
├── codex/SKILL.md         # Codex 专用 Skill 安装文件
├── requirements.txt        # Python 依赖
├── install.sh             # 安装脚本
├── 交付说明.md             # 版本交付说明
├── 项目管理体系说明.md      # 项目管理体系
├── docs/                  # SOP 文档
├── scripts/               # 核心脚本
│   └── invoice-trip-organizer/
│       ├── VERSION            # 当前版本号
│       ├── CHANGELOG.md       # 详细变更日志
│       ├── setup.py           # 初始化设置 & 重置 & 更新
│       ├── init.py            # 入口脚本
│       ├── config_template.py # 配置模板
│       ├── config.py          # 用户配置（gitignore）
│       ├── version_manager.py # 版本管理器
│       ├── deploy.py          # 部署 & 在线升级
│       ├── invoice_auto_organizer.py
│       ├── trip_auto_organizer.py
│       ├── download_invoices.py
│       ├── upload_files.py
│       ├── import_trips.py
│       ├── email_manager.py
│       ├── audit_03_done.py
│       ├── rename_update.py
│       └── release_check.py
├── Templates/             # 模板文件
└── 项目管理/              # 项目管理文档
    ├── 版本发布记录/
    ├── 需求与计划/
    ├── 测试记录/
    └── 使用反馈/
```

---

## 版本管理

本项目采用 **Semantic Versioning**（语义化版本号），格式为 `MAJOR.MINOR.PATCH`。

### 自动更新机制

每次运行脚本时自动检测 Skill 版本，发现新版本时自动更新脚本文件（保留用户数据和配置）。

### 发布新版本（开发者）

1. 修改 `scripts/invoice-trip-organizer/VERSION` 文件
2. 更新 `scripts/invoice-trip-organizer/CHANGELOG.md`
3. 更新 `SKILL.md` frontmatter 中的 `version` 和 `description`
4. 运行 `python3 scripts/invoice-trip-organizer/release_check.py`
5. 同步到 GitHub 并创建对应 tag（如 `v1.0.x`）
5. 使用人运行 `deploy.py --upgrade` 自动升级

---

## 注意事项

- `config.py` 包含用户敏感信息（邮箱、路径），已被 `.gitignore` 忽略
- 首次使用请运行 `setup.py init` 自动生成配置
- 用户数据（发票、台账、行程）独立于代码，升级不受影响

---

*本项目为 NoBusy 别虾忙｜AI 管理实战 对外 Skill 工具。*
