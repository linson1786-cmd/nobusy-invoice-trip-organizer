---
name: invoice-trip-organizer
description: 个人行程与报销 V1.0.6 | 配置化版本，支持分享与在线升级
version: 1.0.6
trigger: ["跑一次发票整理", "有新行程", "从邮件下载发票", "发票整理", "行程整理", "导入", "导入文件", "新增行程", "初始化", "初始化设置", "重置", "下载发票", "收发票", "升级", "检查更新"]
---

# 个人行程与报销

## 功能概述

本工具帮助个人自动化管理发票和出差行程：

1. **发票自动整理** (`invoice_auto_organizer.py`)
   - 扫描 `01 待分类/` → 自动识别分类 → 归档到 `03 已完成/`（或移入 `02 待核实/`）
   - 支持 PDF / OFD / XML / 图片（OCR）
   - 自动提取日期、金额、类别，按 SOP 标准命名
   - 自动关联行程、生成台账

2. **行程自动整理** (`trip_auto_organizer.py`)
   - 创建行程文件夹结构（详情 MD + 发票附件目录）
   - 从 `03 已完成` 匹配发票 → 复制到行程附件
   - 生成发票清单、行程总览、报销单模板

3. **邮件下载发票** (`download_invoices.py` + `email_manager.py`，可选）
   - 弹出界面选择/注册邮箱账户，支持多邮箱
   - 通过 IMAP 从 163 / QQ / 126 / 自定义邮箱下载发票附件
   - 默认选中上次使用的邮箱
   - 未登记邮箱时自动弹出注册界面（含授权码获取指引）

4. **导入文件** (`upload_files.py`)
   - 触发命令：`导入`
   - 弹出系统原生文件选择窗口，支持多选
   - 选择的文件自动复制到 `01 待分类/` 目录
   - 自动处理重名文件（追加 _1, _2 ...）
   - macOS 优先使用 osascript 原生窗口，其他平台用 tkinter

5. **新增行程** (`import_trips.py`)
   - 触发命令：`新增行程`
   - **AI 对话场景**（推荐）：AI 在对话中收集用户粘贴的行程数据，通过管道传给脚本
   - **终端直跑场景**：脚本弹出文本输入窗口，粘贴 Tab 分隔行程数据
   - 数据格式：开始日期 + 结束日期 + 行程路线（城市用 - 连接）
   - 支持多种日期格式：2026-01-04、2026/3/11
   - 按日期去重：同日期范围已存在则跳过，仅新增不存在的行程
   - 自动创建行程文件夹、行程详情、匹配发票

6. **初始化设置** (`setup.py init`)
   - 触发命令：`初始化设置`
   - 弹出文件夹选择窗口，选择父目录
   - 在所选目录下自动创建完整的「个人行程与报销」目录架构
   - 自动复制脚本、SOP 文档，生成 config.py
   - 目录已存在时保留已有文件，仅补充缺失项

7. **版本管理** (`version_manager.py`)
   - 版本号格式：Semantic Versioning（1.0.x，支持自动更新）
   - 每次运行脚本时自动检查新版本
   - 发现新版本时自动更新脚本文件，保留用户数据
   - 更新前自动创建备份（`.backup/<version>/`），支持回退
   - 配置合并：保留用户自定义配置，自动追加新版本新增的配置项

## 项目位置

本项目独立管理，路径：
`/Users/linson/Documents/Personage/AI Tools Learning/WorkBuddy Skills/`

当前版本：**V1.0.6**

## 首次使用

对我说「初始化」或「初始化设置」，会弹出文件夹选择窗口，选择父目录后自动创建完整目录架构、复制脚本、生成 config.py。

或手动运行：

```bash
cd scripts && python3 setup.py init
```

初始化完成后：
1. 把发票文件放入 `01 待分类/` 目录
2. 对我说「发票整理」或运行 `cd scripts && python3 invoice_auto_organizer.py`

## 新增行程操作指引（AI 必读）

当用户说「新增行程」时，**不要直接运行脚本弹窗**（沙箱环境 GUI 窗口无法显示）。正确流程：

1. **告诉用户**：请把行程数据贴在对话里，每行一条，Tab 分隔：
   ```
   开始日期	结束日期	行程
   2026-01-04	2026-01-09	广州-上海-南通-杭州-成都-重庆-广州
   ```
2. **收到数据后**，将数据写入临时文件，通过管道传给脚本：
   ```bash
   cat /tmp/trips_data.txt | python3 import_trips.py
   ```
   或直接用 heredoc：
   ```bash
   python3 import_trips.py << 'TRIPDATA'
   开始日期	结束日期	行程
   2026-01-04	2026-01-09	广州-上海
   TRIPDATA
   ```
3. **将脚本输出反馈给用户**（新增了几条、跳过了几条）

> 日期格式随意：`2026-01-04`、`2026/3/11`、`2026.3.11` 均可
> 城市用 `-` 连接，如 `广州-上海-北京`

## 配置文件说明 (config.py)

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `SKILL_VERSION` | 当前 Skill 版本号（自动更新，勿手动修改） | `"1.0.6"` |
| `OBSIDIAN_VAULT` | Obsidian 笔记库根目录 | `~/Documents/MyVault` |
| `INVOICE_BASE_REL` | 发票整理相对路径 | `个人行程与报销/01 发票整理` |
| `TRIP_BASE_REL` | 行程目录相对路径 | `个人行程与报销/02 行程与个人报销单` |
| `REIMBURSEMENT_TEMPLATE` | 报销单 Excel 模板路径 | `...xlsx` |

> 📮 邮箱配置不再写入 config.py。运行下载脚本时会弹出界面选择/注册邮箱，账户信息保存在 `~/.invoice-trip/email_accounts.json`，支持多个邮箱。

## 目录结构

```
{OBSIDIAN_VAULT}/
├── {INVOICE_BASE_REL}/
│   ├── 01 待分类/     ← 放入新发票
│   ├── 02 待核实/     ← 脚本无法识别的文件
│   └── 03 已完成/     ← 已整理归档（按月分文件夹）
│       └── 台账.md
└── {TRIP_BASE_REL}/
    └── 2026 年/
        └── 1 月/
            └── 出差1-2026-01-04～2026-01-09_广州-上海-.../
                ├── 01-行程详情.md
                └── 02-发票文件/
                    ├── 机票高铁/
                    ├── 住宿/
                    ├── 餐饮/
                    ├── 打车/
                    ├── 礼品/
                    └── 其他/
```

## 命名规范 (SOP)

```
YYYY-MM-DD_类别_金额[_出发-到达][_发票号后4位]_MMDD_WB/YB_NNN.ext
```

示例：
- `2026-01-05_餐饮_174.00_0105_WB_031.pdf`
- `2026-01-10_机票_1280.00_广州-上海_0110_WB_042.pdf`
- `2026-03-24_住宿(结账单)_278.00_0324_WB_075.pdf`

详细规范见 `docs/SOP-发票文件命名标准.md`。

## 版本管理

本 Skill 采用 **Semantic Versioning**（语义化版本号），格式为 `MAJOR.MINOR.PATCH`：

- **MAJOR**：重大更新，可能不兼容旧版本
- **MINOR**：新增功能，向后兼容
- **PATCH**：Bug 修复，向后兼容

### 自动更新机制

每次运行任何脚本时，会自动检测 Skill 版本：

1. 读取 `config.py` 中的 `SKILL_VERSION`（用户当前版本）
2. 读取 Skill 目录 `VERSION` 文件（最新版本）
3. 如果 `最新版本 > 当前版本`，自动触发更新：
   - ✅ 自动备份旧版本脚本到 `.backup/<version>/`
   - ✅ 更新所有脚本文件（`.py` / `VERSION` / `CHANGELOG.md`）
   - ✅ 合并 `config.py`：保留用户配置，更新版本号，追加新增配置项
   - ✅ 完全不影响用户数据（发票、行程、台账等）

### 手动检查更新

```bash
cd scripts && python3 setup.py update
```

或运行 `version_manager.py`：

```bash
cd scripts && python3 version_manager.py
```

### 版本回退

如果更新后出现问题，可从备份目录恢复：

```bash
cd scripts/invoice-trip-organizer/.backup/1.0.4
cp *.py ../../
```

### 多人使用场景

- 每位用户有独立的数据目录（`个人行程与报销/`）
- 脚本共享同一个 Skill 目录（或各自复制到工作目录）
- 版本更新只更新脚本代码，**绝不触碰用户的发票、行程、台账等数据**
- 各用户的 `config.py` 独立配置（邮箱、路径等）

### 发布新版本（开发者）

1. 修改 `scripts/invoice-trip-organizer/VERSION` 文件（如 `1.0.5` → `1.0.6`）
2. 在 `scripts/invoice-trip-organizer/CHANGELOG.md` 中记录变更
3. 如有新增配置项，更新 `config_template.py`
4. 用户下次运行任意脚本时，自动检测并更新

## 依赖安装

```bash
pip install pdfminer.six PyMuPDF fpdf2 Pillow pytesseract
# OCR 额外需要: brew install tesseract (macOS) 或 apt install tesseract-ocr (Ubuntu)
```

## 常见问题

**Q: 不使用 Obsidian 可以用吗？**
A: 可以。`OBSIDIAN_VAULT` 设为任意文件夹即可，目录结构会自动创建。

**Q: 邮箱下载不工作？**
A: 选择邮箱时，确保使用授权码而非登录密码。各邮箱授权码获取方式：163/126 → 设置 → POP3/SMTP/IMAP；QQ → 设置 → 账户 → POP3/IMAP/SMTP。也可运行 `python3 email_manager.py guide 163` 查看指引。

**Q: 发票金额/类别识别错误？**
A: 把文件移入 `02 待核实/`，手动重命名为标准格式，下次运行会自动归档。

## 在线升级

本 Skill 支持从 GitHub 一键在线升级，使用人无需手动下载文件。

### 升级命令

```bash
# 检查是否有新版本（不执行升级）
python3 ~/.workbuddy/skills/invoice-trip-organizer/scripts/deploy.py --check-update

# 一键升级到最新版本（自动备份旧版 → 拉取新版 → 部署）
python3 ~/.workbuddy/skills/invoice-trip-organizer/scripts/deploy.py --upgrade

# 查看当前版本状态
python3 ~/.workbuddy/skills/invoice-trip-organizer/scripts/deploy.py --status
```

### 升级保障

- **数据安全**：升级仅更新脚本文件，绝不覆盖用户 `config.py`、发票、行程、台账
- **自动备份**：升级前自动备份旧版本到 `.backup/<version>_<timestamp>/`
- **版本对比**：仅在远程版本 > 本地版本时执行升级，避免重复部署
- **三重降级**：git clone → HTTP ZIP 下载 → GitHub API，确保网络不佳时也能升级

### 在对话中升级

直接对 AI 说「升级发票整理 Skill」或「检查发票整理有没有新版本」，AI 会自动执行上述命令。

## 文件清单

| 文件 | 说明 |
|------|------|
| `VERSION` | Skill 版本号（语义化版本 1.0.x） |
| `CHANGELOG.md` | 版本变更日志 |
| `version_manager.py` | 版本管理器（检查更新、自动更新、备份、配置合并） |
| `deploy.py` | 部署工具（本地部署、在线升级、版本检查、备份） |
| `config_template.py` | 配置文件模板（复制为 `config.py` 后填写） |
| `config.py` | 你的配置文件（不提交到 git，升级时不覆盖） |
| `init.py` | 初始化脚本（创建目录、检查依赖、版本检查） |
| `invoice_auto_organizer.py` | 发票自动整理主脚本（入口含版本检查） |
| `trip_auto_organizer.py` | 行程自动整理主脚本（入口含版本检查） |
| `download_invoices.py` | 邮箱发票下载脚本（入口含版本检查） |
| `email_manager.py` | 邮箱账户管理器（存储、选择、注册界面） |
| `upload_files.py` | 文件选择导入脚本（入口含版本检查） |
| `import_trips.py` | 批量导入行程脚本（文本输入窗口、日期去重） |
| `setup.py` | 初始化设置 & 重置 & 更新脚本（入口含版本检查） |
| `docs/SOP-发票文件命名标准.md` | 命名规范详细文档 |
| `audit_03_done.py` | 03 已完成文件排查脚本（维护用） |
