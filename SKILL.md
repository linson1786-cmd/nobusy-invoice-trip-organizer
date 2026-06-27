---
name: invoice-trip-organizer
description: "行程报销管家——个人行程与报销文件自动化管理。Personal trip and expense document automation. Auto-classify files (PDF/OFD/XML/image OCR), organize trip folders, download from email, generate expense reports. Triggers: 文件识别, 行程整理, 下载发票, 导入, 升级."
description_zh: "行程报销管家——个人行程与报销文件自动化管理"
description_en: "Trip Expense Butler — Personal trip and invoice reimbursement automation"
version: 1.0.44
display_name: "行程报销管家"
display_name_en: "Trip Expense Butler"
author: linson
visibility: public
agent_created: true
metadata:
  category: office-efficiency
  brand: NoBusy
trigger: ["文件识别", "行程整理", "导入", "导入文件", "新增行程", "初始化", "初始化设置", "重置", "下载发票", "收发票", "升级", "检查更新", "刷新"]
---

# 行程报销管家 (Trip Expense Butler)

## 功能概述

本工具帮助个人自动化管理报销文件和出差行程：

1. **文件自动识别** (`invoice_auto_organizer.py`)
   - 触发命令：`文件识别`
   - **Phase 0 OFD/XML预处理**：OFD/XML 自动转 PDF，多重格式去重
   - **Phase 1 待分类处理**：扫描 `01 待分类/` → 提取日期/金额/类别 → 按标准命名 → 归档 `03 已完成/`；无法识别的移入 `02 待核实/`
   - **Phase 2 待核实质检**：扫描 `02 待核实/`，已手动命名的自动归档
   - **Phase 3 去重校验**：① 发票号去重 ② 行程单交叉去重 ③ 通用去重
   - **Phase 4 台账生成**：更新 03 已完成台账 + 总台账

2. **行程自动整理** (`trip_auto_organizer.py`)
   - 触发命令：`行程整理`
   - **Phase 1 行程创建**：创建行程文件夹结构（详情 MD + 发票附件子目录）
   - **Phase 2 发票匹配**：从 `03 已完成` 按日期范围匹配发票 → 复制到行程附件目录
   - **Phase 3 文档生成**：生成发票清单、行程详情、行程总览、报销单模板
   - 行程去重：同日期范围已存在则复用，清空旧发票重新匹配

3. **邮件下载发票** (`download_invoices.py`，可选）
   - 触发命令：`下载发票`
   - **Phase 1 账户管理**：弹窗选择/注册邮箱（163/QQ/126/自定义），多邮箱支持
   - **Phase 2 邮件拉取**：IMAP 下载发票附件 → 存入 `01 待分类/`
   - **Phase 3 去重**：① Message-ID 去重 ② MD5 内容去重

4. **导入文件** (`upload_files.py`)
   - 触发命令：`导入`
   - 弹出系统原生文件选择窗口，多选文件 → 复制到 `01 待分类/`
   - 自动处理重名（追加 `_1`, `_2`）

5. **新增行程** (`import_trips.py`)
   - 触发命令：`新增行程`
   - **Phase 1 数据采集**：AI 对话收集 / 终端粘贴 / 文件批量导入
   - **Phase 2 行程创建**：按日期去重 → 创建行程文件夹 → 生成行程详情
   - **Phase 3 发票匹配**：自动从 `03 已完成` 匹配发票

6. **初始化设置** (`setup.py init`)
   - 触发命令：`初始化设置`
   - 选择父目录 → 自动创建完整目录架构 → 复制脚本/标准文档/config.py
   - 已存在目录仅补充缺失项

7. **版本管理** (`version_manager.py`)
   - 触发命令：`升级` / `检查更新`
   - Semantic Versioning，自动检测新版本 → 更新脚本保留数据 → 创建备份支持回退

8. **刷新** (`refresh.py`)
   - 触发命令：`刷新`
   - 升级版本后一键更新所有已有数据到最新规则
   - **Phase 0 目录结构**：检查目录命名不一致，更新为最新目录名称
   - **Phase 1 文件识别**：重新扫描 03 已完成，按最新类别规则重新识别；02 待核实文件转回 01 待分类，重新走识别流程
   - **Phase 2 数据迁移**：重新匹配 03 已完成发票到对应行程，清空旧发票附件并重新复制，重新生成发票清单、行程详情、行程总览
   - **Phase 3 台账重生成**：重新扫描 03 已完成 + 行程数据，生成总台账和各月份台账

## 项目位置

本项目独立管理，路径：
`/Users/linson/Documents/Personage/AI Tools Learning/WorkBuddy Skills/`

当前版本：见 `scripts/VERSION` 文件

## 首次使用

对我说「初始化」或「初始化设置」，会弹出文件夹选择窗口，选择父目录后自动创建完整目录架构、复制脚本、生成 config.py。

或手动运行：

```bash
cd scripts/invoice-trip-organizer && python3 setup.py init
```

无界面环境可指定父目录：

```bash
cd scripts/invoice-trip-organizer && python3 setup.py init --base-dir /tmp/invoice-trip-demo
```

初始化完成后：
1. 把发票文件放入 `01 待分类/` 目录
2. 对我说「文件识别」或运行 `cd scripts/invoice-trip-organizer && python3 invoice_auto_organizer.py`

## 新增行程操作指引

> ⚠️ **重要**：AI 通过 Bash 工具运行脚本时，脚本在沙箱中执行，tkinter/GUI 窗口无法显示到用户屏幕。
> 因此在 WorkBuddy AI 对话中，必须使用 stdin 管道输入，不能直接运行脚本等弹窗。

### 场景 1：WorkBuddy AI 对话（主要场景）

AI 按以下步骤操作：

1. AI 向用户说明数据格式，请用户在对话中贴出行程数据
2. 用户贴出数据后，AI 通过 stdin 管道传入脚本执行：

```bash
python3 import_trips.py << 'TRIPDATA'
开始日期	结束日期	行程
2026-01-04	2026-01-09	广州-上海-南通-杭州-成都-重庆-广州
2026/3/11	2026/3/14	广州-中山-深圳-上海-苏州-上海-广州
TRIPDATA
```

3. AI 读取脚本输出，向用户反馈导入结果（新增几条、跳过几条）

### 场景 2：终端直接运行

用户在终端中手动运行 `python3 import_trips.py`，脚本弹出文本输入窗口（tkinter），
用户粘贴数据后提交。此场景下 GUI 窗口正常工作。

### 场景 3：文件批量导入

```bash
python3 import_trips.py --file trips.txt
```

### 数据格式

> 日期格式随意：`2026-01-04`、`2026/3/11`、`2026.3.11` 均可
> 城市用 `-` 连接，如 `广州-上海-北京`
> Tab 分隔，可含表头行（自动跳过）
> 同日期范围已存在的行程自动跳过，仅新增不重复的

## 配置文件说明 (config.py)

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `SKILL_VERSION` | 当前 Skill 版本号（自动更新，勿手动修改） | `"1.0.x"` |
| `OBSIDIAN_VAULT` | Obsidian 笔记库根目录 | `~/Documents/MyVault` |
| `INVOICE_BASE_REL` | 01 文件识别整理相对路径 | `个人行程与报销/01 文件识别整理` |
| `TRIP_BASE_REL` | 行程目录相对路径 | `个人行程与报销/02 行程` |
| `REIMBURSEMENT_BASE_REL` | 报销单目录相对路径 | `个人行程与报销/03 报销单` |
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
├── {TRIP_BASE_REL}/
│   └── 2026 年/
│       └── 1 月/
│           ├── 出差1-2026-01-04～2026-01-09_广州-上海-.../
│           │   ├── 01-行程详情.md
│           │   └── 02-发票文件/
│           │       ├── 机票高铁/
│           │       ├── 住宿/
│           │       ├── 打车/
│           │       ├── 礼品/
│           │       └── 其他/
│           └── 餐饮/          ← 餐饮发票按月归档（不放入行程）
└── {REIMBURSEMENT_BASE_REL}/
    └── 2026 年/
        └── 1 月/
            └── 出差1-报销单.xlsx   ← 报销单 Excel（按行程生成）
```

> **餐饮发票规则**：餐饮类发票不放入行程文件夹，按月归档到月度目录下的"餐饮"文件夹（与出差文件夹同级）。

## 命名规范 (SOP)

```
YYYY-MM-DD_类别_金额[_位置][_购买方简称][_发票号后4位]_MMDD_WB/YB_NNN.ext
```

示例：
- `2026-01-05_餐饮_174.00_乐纯生物_0105_WB_031.pdf`
- `2026-01-10_机票_1280.00_广州-上海_乐纯生物_0110_WB_042.pdf`
- `2026-01-12_住宿_264.00_中山_乐纯生物_0112_WB_043.pdf`
- `2026-03-24_住宿(结账单)_278.00_0324_WB_075.pdf`
- `2026-06-14_机票比价图_广州-长春_0625_WB_055.jpg`（机票比价截图，无金额字段，非报销凭证）

> 机票比价图/高铁比价图/住宿比价图：非报销凭证，文件名不含金额字段。日期以截图内容中的计划出行日期为准（如"计划 1/9 17:30"→`2026-01-09`、"直飞 06-15"→`2026-06-15`），非截图保存日期。路线字段有机票/高铁路线时填写`出发地-到达地`，无路线时省略。不计入报销金额统计。

> 购买方简称：从发票PDF/XML内容自动提取购买方公司名称并转为简称（去除省市前缀和公司类型后缀）。无法提取时不添加。

详细规范见 `docs/文件识别命名标准.md`。

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
cd scripts/invoice-trip-organizer && python3 setup.py update
```

或运行 `version_manager.py`：

```bash
cd scripts/invoice-trip-organizer && python3 version_manager.py
```

### 版本回退

如果更新后出现问题，可从备份目录恢复：

```bash
cd scripts/invoice-trip-organizer/.backup/<版本号>
cp *.py ../../
```

### 多人使用场景

- 每位用户有独立的数据目录（`个人行程与报销/`）
- 脚本共享同一个 Skill 目录（或各自复制到工作目录）
- 版本更新只更新脚本代码，**绝不触碰用户的发票、行程、台账等数据**
- 各用户的 `config.py` 独立配置（邮箱、路径等）

### 发布新版本（开发者）

1. 修改 `scripts/invoice-trip-organizer/VERSION` 文件（如 `1.0.x` → `1.0.y`）
2. 在 `scripts/invoice-trip-organizer/CHANGELOG.md` 中记录变更
3. 更新 `SKILL.md` frontmatter 中的 `version` 和 `description`
4. 用户下次运行任意脚本时，自动检测并更新

## 依赖安装

### Python 依赖

```bash
pip install pdfminer.six PyMuPDF fpdf2 Pillow pytesseract
```

### Tesseract OCR 引擎（图片识别必需）

图片格式发票（JPG/PNG 等微信截图）依赖 Tesseract OCR 引擎识别文字。**未安装时图片将全部移至 02 待核实/**。

| 系统 | 安装命令 | 中文语言包 |
|------|---------|-----------|
| macOS | `brew install tesseract` | `brew install tesseract-lang`（含 chi_sim） |
| Ubuntu/Debian | `sudo apt install tesseract-ocr` | `sudo apt install tesseract-ocr-chi-sim` |
| Windows | [下载安装包](https://github.com/UB-Mannheim/tesseract/wiki) | 安装时勾选 Chinese (Simplified) |

安装后验证：终端运行 `tesseract --version` 能显示版本号即成功。

**⚠️ 中文语言包验证**：运行 `tesseract --list-langs`，确认列表中包含 `chi_sim`。如果没有，说明中文语言包未安装成功，OCR 中文图片会输出乱码。手动安装方法：从 https://github.com/tesseract-ocr/tessdata_fast/raw/main/chi_sim.traineddata 下载 `chi_sim.traineddata` 文件，放入 Tesseract 的 tessdata 目录（macOS: `/opt/homebrew/share/tessdata/`，Linux: `/usr/share/tesseract-ocr/4.00/tessdata/`，Windows: 安装目录下的 `tessdata/`）。

## 常见问题

**Q: 不使用 Obsidian 可以用吗？**
A: 可以。`OBSIDIAN_VAULT` 设为任意文件夹即可，目录结构会自动创建。

**Q: 邮箱下载不工作？**
A: 选择邮箱时，确保使用授权码而非登录密码。各邮箱授权码获取方式：163/126 → 设置 → POP3/SMTP/IMAP；QQ → 设置 → 账户 → POP3/IMAP/SMTP。也可运行 `python3 email_manager.py guide 163` 查看指引。

**Q: 发票金额/类别识别错误？**
A: 把文件移入 `02 待核实/`，手动重命名为标准格式，下次运行会自动归档。

**Q: 重复放入已归档的发票会怎样？**
A: 自动去重，不会产生重复文件。三层机制：① 有发票号的按发票号去重 ② 行程单与对应发票交叉去重 ③ 无发票号的（如 ETC/滴滴网页打印件）按日期+类别+金额匹配 03 已完成，命中则自动删除。

**Q: 图片发票全被移到 02 待核实/？**
A: 这是因为 Tesseract OCR 引擎未安装。图片格式发票（JPG/PNG 等微信截图）必须通过 OCR 才能识别文字内容。安装方法见上方"依赖安装"章节。安装后把文件从 02 待核实/ 移回 01 待分类/，重新运行文件识别即可。

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
- **数据迁移**：升级后自动检测已有文件是否需要更新（类别重分类、购买方简称），有变更则提示确认

### 在对话中升级

直接对 AI 说「升级 Skill」或「检查有没有新版本」，AI 会自动执行上述命令。

### 升级后数据迁移（自动）

当新版本包含分类规则或命名规则变更时，升级流程会**自动检测**已有文件是否需要更新：

1. 代码更新完成后，自动调用 `rename_update.py --check` 检测
2. 如果有变更，显示预览并提示用户确认
3. 确认后执行迁移，完成后自动更新 `LAST_MIGRATION_VERSION`
4. 如果无变更，静默跳过，不打扰用户

**迁移内容：**
- **类别重分类**：用最新 CATEGORY_RULES 重新识别每个文件的类别，不匹配的自动更新
- **购买方简称**：提取购买方公司名称并追加到文件名
- 同步更新行程目录中的发票副本（如有）
- 不会将具体类别降级为"其他"（防止文本提取不完整导致误判）

**手动执行迁移**（如需）：

```bash
python3 ~/.workbuddy/skills/invoice-trip-organizer/scripts/rename_update.py --dry-run  # 预览
python3 ~/.workbuddy/skills/invoice-trip-organizer/scripts/rename_update.py             # 执行
python3 ~/.workbuddy/skills/invoice-trip-organizer/scripts/deploy.py --migrate          # 通过 deploy.py 执行
```

## 刷新操作指引

> 升级版本后，对我说「刷新」，一键将所有已有数据更新到最新规则。

### 刷新内容

| 阶段 | 操作 | 说明 |
|------|------|------|
| Phase 0 | 目录名迁移 | 检查并迁移旧目录名（01 发票整理 / 文件识别整理 → 01 文件识别整理） |
| Phase 1 | 数据迁移 | 重新识别 03 已完成中所有文件的类别和购买方简称 |
| Phase 2 | 行程刷新 | 重新扫描所有已有行程，从 03 已完成重新匹配发票，清空旧副本重新复制，重新生成发票清单/行程详情/行程总览 |
| Phase 3 | 台账重生成 | 重新扫描 03 已完成生成台账 |

### 使用方式

**AI 对话场景**：对我说「刷新」即可，AI 自动运行脚本并反馈结果。

**终端场景**：

```bash
# 预览（不修改文件）
python3 ~/.workbuddy/skills/invoice-trip-organizer/scripts/refresh.py --dry-run

# 执行刷新
python3 ~/.workbuddy/skills/invoice-trip-organizer/scripts/refresh.py
```

### 什么时候需要刷新

- ✅ 升级到新版本后（分类规则、命名规则、目录结构有变更）
- ✅ 手动修改了 03 已完成中的文件后（如重命名、移动）
- ✅ 想确保所有行程数据与 03 已完成保持同步
- ❌ 日常使用不需要，文件识别和新增行程已自动处理

## 文件清单

| 文件 | 说明 |
|------|------|
| `VERSION` | Skill 版本号（语义化版本 1.0.x） |
| `CHANGELOG.md` | 版本变更日志 |
| `version_manager.py` | 版本管理器（检查更新、自动更新、备份、配置合并） |
| `deploy.py` | 部署工具（本地部署、在线升级、版本检查、备份、数据迁移） |
| `config_template.py` | 配置文件模板（复制为 `config.py` 后填写） |
| `config.py` | 你的配置文件（不提交到 git，升级时不覆盖） |
| `init.py` | 初始化脚本（创建目录、检查依赖、版本检查） |
| `invoice_auto_organizer.py` | 文件自动识别主脚本（入口含版本检查） |
| `trip_auto_organizer.py` | 行程自动整理主脚本（入口含版本检查） |
| `download_invoices.py` | 邮箱发票下载脚本（入口含版本检查） |
| `email_manager.py` | 邮箱账户管理器（存储、选择、注册界面） |
| `upload_files.py` | 文件选择导入脚本（入口含版本检查） |
| `import_trips.py` | 批量导入行程脚本（文本输入窗口、日期去重） |
| `setup.py` | 初始化设置 & 重置 & 更新脚本（入口含版本检查） |
| `docs/文件识别命名标准.md` | 命名规范详细文档 |
| `audit_03_done.py` | 03 已完成文件排查脚本（维护用） |
| `release_check.py` | 发布前检查脚本（版本、敏感文件、编译、安装一致性） |
| `rename_update.py` | 升级后数据迁移（类别重分类 + 购买方简称，升级流程自动调用） |
| `refresh.py` | 刷新工具（升级后一键更新所有数据：数据迁移 + 行程刷新 + 台账重生成） |
