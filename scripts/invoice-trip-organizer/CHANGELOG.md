# 版本变更日志

## 1.0.54 - 2026-06-28

### 改进

- **"其他"恢复为正式类别** 📋
  - 洗浴/家政等生活服务发票归入 `"其他"` 类别（关键词匹配，正常归档）
  - `classify()` 默认返回 `"无法分类"`（区别于关键词匹配的 `"其他"`）
  - `process_inbox()` 拦截 `cat == "无法分类"` → 02 待核实
  - 类别清单：15+1 = 16 个（15 个具体类别 + "其他"）

### 变更文件

- `invoice_auto_organizer.py`：CATEGORY_RULES + "其他" 关键词、classify() 返回 "无法分类"、拦截更新
- `config.py`：同步 CATEGORY_RULES
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.53 - 2026-06-28

### 修复（4项）

- **_rr后缀文件死循环** 🔴 Bug 1
  - 已含 `_rr` 后缀的文件不再移回01待分类，避免反复OCR

- **水单被误判为住宿比价图** 🟡 Bug 4
  - 住宿比价图移除"入住人"关键词（水单也有，导致抢匹配）

- **洗浴/家政发票无关键词** 🟢 Bug 5
  - 礼品类新增"洗浴""家政""生活服务"关键词

- **XML→PDF 日期提取失败** 🟢 Bug 6
  - `extract_date_from_text()` 新增"开票日期: YYYY-MM-DD"精确格式

### 变更文件

- `invoice_auto_organizer.py`：4处修复
- `config.py`：住宿比价图/礼品关键词同步
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.52 - 2026-06-28

### 改进

- **`is_invoice_file()` 改为 ≥3 关键词判定** 📋
  - 原逻辑：命中任一 STRICT_INVOICE_MARKERS → 正式发票
  - 新逻辑：**≥3 个关键词同时命中** → 正式发票
  - 效果：OTA 截图偶然含 1 个词（如"开票日期"）不会被误判，真发票稳定 5-7 个命中不受影响

### 变更文件

- `invoice_auto_organizer.py`：`is_invoice_file()` + `classify()` 两处 `any()` → `sum() >= 3`
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.51 - 2026-06-28

### 修复（4项连锁Bug）

- **真高铁票被比价图抢匹配** 🔴 Bug A
  - 根因：高铁比价图含"二等座""车票"，真高铁票PDF也含，比价图规则排前→抢匹配
  - 修复：`classify()` 中检测 STRICT_INVOICE_MARKERS，真发票跳过所有"比价图"类别

- **"票价"关键词太通用** 🔴 Bug B
  - 根因：机票关键词含"票价"，真高铁票含"票价:￥19.00"→误判为"机票"
  - 修复：机票关键词移除"票价"

- **"电子发票""电子客票"太宽泛** 🟡 Bug C
  - 根因：OTA截图含"仅提供全额电子发票"→触发真发票检测→跳过比价图→误判类别
  - 修复：STRICT_INVOICE_MARKERS 移除"电子发票""电子客票"，保留"铁路电子客票"

- **已核实文件被反复回炉** 🟡 P1
  - 修复：`reprocess_review_files()` 加 `STANDARD_NAME_RE.match()` 检查，已标准格式跳过

### 变更文件

- `invoice_auto_organizer.py`：classify() 真发票跳过比价图 + keyword移除 + STRICT_INVOICE_MARKERS 精简 + 标准格式跳过
- `config.py`：机票关键词同步移除"票价"
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.50 - 2026-06-28

### 新增

- **STRICT_INVOICE_MARKERS 补充关键词** 📋
  - 新增 `"铁路电子客票"`、`"电子客票"` 两个税票种关键词
  - 铁路电子客票（含二维码的 OFD/PDF）现在被正确识别为正式发票

- **SKILL.md 文档更新** 📝
  - 新增"文件识别：分类体系与校验规则"章节
  - 包含：文件性质预分类、类别清单（含文件性质归属）、校验规则、子类型判定

### 变更文件

- `invoice_auto_organizer.py`：STRICT_INVOICE_MARKERS +2 关键词
- `SKILL.md`：新增分类体系文档
- `VERSION` / `CHANGELOG.md`：版本三件套更新

## 1.0.49 - 2026-06-28

### 新增

- **文件类型预分类：发票 vs 普通文件** 📋
  - 新增 `is_invoice_file()` 函数，分类前先判断文件性质
  - **正式发票**（含发票号码/税号/销售方）：严格规则，必须通过 `has_invoice_markers()` 校验
  - **普通文件**（OTA截图/水单/预订确认/行程单等）：宽松规则，不要求发票特征词
  - INVOICE_CONTENT_MARKERS 拆分为 `STRICT_INVOICE_MARKERS` + `NON_INVOICE_MARKERS`

### 设计原则

```
extract text → is_invoice_file(text, ext)
  ├─ True  (正式发票) → 必须通过发票特征词校验
  └─ False (普通文件) → 跳过特征词要求，按内容分类
```

### 变更文件

- `invoice_auto_organizer.py`：新增 `is_invoice_file()` + `STRICT_INVOICE_MARKERS` + `NON_INVOICE_MARKERS` + 处理流程分支
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.48 - 2026-06-27

### 修复

- **`classify()` 返回 None 导致下游崩溃** 🔴
  - 问题：V1.0.45 改 `classify()` 为返回 None，`classify_with_subtype()` / `rename_update.py` 等下游都按"返回有效字符串"设计，None → 43个文件类别变为None + TypeError崩溃
  - 修复：`classify()` 恢复返回 `"其他"`，始终返回有效字符串；`process_inbox()` 中拦截 `cat == "其他"` → 02 待核实

- **refresh.py 增加 `--force` 参数** 🟡
  - 问题：版本号相同时刷新跳过重识别，用户无法手动触发
  - 修复：`refresh.py --force` 忽略版本号校验，强制全量重识别

### 设计原则
- `classify()` = 始终返回有效类别字符串（下游安全）
- `process_inbox()` = 路由决策层，拦截"其他"不进归档
- 两者解耦，互不影响

### 变更文件

- `invoice_auto_organizer.py`：`classify()` 返回 "其他"，3处检查改为 `cat == "其他"`
- `refresh.py`：加 `--force` 参数
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.47 - 2026-06-27

### 修复（P0致命回归根因 + P0/P1）

- **config.py 覆盖脚本 CATEGORY_RULES** 🔴🔴 P0 致命
  - 根因：`invoice_auto_organizer.py` 先用 `if 'CATEGORY_RULES' not in dir()` 定义默认规则，但随后 `config.py` 导入时 `globals()[_attr] = config值` 全部覆盖
  - 影响：v1.0.36～v1.0.46 共 11 个版本的所有关键词修复实际未生效
  - 修复：改名 `_DEFAULT_CATEGORY_RULES` / `_DEFAULT_SUBTYPE_RULES`，在 config.py 加载后强制恢复

- **classify() 返回 None 导致格式化崩溃** 🔴 P0
  - 修复：所有 `classify()` 调用点加 `if cat is None → move_to_review + continue` 容错

- **02待核实回炉无限循环** 🟡 P1
  - 修复：回炉时文件名加 `_rrN_` 计数标记，≥3次自动跳过

### 变更文件

- `invoice_auto_organizer.py`：CATEGORY_RULES/SUBTYPE_RULES 改为 `_DEFAULT_*` + config 加载后强制恢复 + None 容错 + 回炉计数
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.46 - 2026-06-27

### 修复（基于 V1.0.45 用户反馈报告，4项回归修复）

- **`_clean_filename_for_classify()` 过度清理** 🔴 回归根因
  - 问题：V1.0.43 引入的全局 `replace()` 清理所有文件名中的类别标签，子串副作用导致误删有效信息
  - 修复：改为位置精确匹配——只移除文件名 `_` 分隔后位置1（标准格式中的类别位置）的标签

- **PDF CJK 换行导致关键词断裂** 🔴
  - 问题：pdfminer 提取时在 CJK 字符间插入 `\n`，`"国内航空"` → `"国内航\n空"`，`"航空" in text` → False
  - 修复：`extract_pdf_text()` 增加后处理 `re.sub(r'([\u4e00-\u9fff])\\s*\\n\\s*([\u4e00-\u9fff])', r'\\1\\2', text)`

- **关键词缺失** 🟡
  - 机票：补充 `"保险"`（平安保险发票含"责任保险"非"保险服务"）
  - 滴滴：补充 `"didi"`、`"代驾"`（代驾发票不含"滴滴"）
  - 礼品：补充 `"丝巾"`、`"纺织"`
  - 餐饮：补充 `"酒"`、`"白酒"`、`"洋酒"`、`"红酒"`、`"啤酒"`（红酒发票）

- **config.py 关键词缺漏** 🟡
  - config.py 的 CATEGORY_RULES 覆盖 invoice_auto_organizer.py，需两处同步更新

### 变更文件

- `invoice_auto_organizer.py`：`_clean_filename_for_classify()` 重写 + `extract_pdf_text()` 加 CJK 合并 + CATEGORY_RULES 关键词补充
- `config.py`：CATEGORY_RULES 关键词同步补充
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.45 - 2026-06-27

### 改进（严格执行）

- **删除"其他"类别** 🚫
  - `classify()` 返回 `None` 替代 `"其他"`
  - 无匹配类别的文件直接移入 `02 待核实/`（原因："无法分类(无匹配类别)"）
  - `VALID_CATEGORIES` 移除"其他"
  - 改名 `classify()` + `classify_with_subtype()` 链路均兼容 None 返回

- **条件不齐全严格执行** 📋
  - 比价图日期提取失败 → 02 待核实（V1.0.44）
  - 无法分类 → 02 待核实（V1.0.45）
  - 无法提取金额 → 02 待核实（已有）
  - 无法提取日期 → 02 待核实（已有）

### 变更文件

- `invoice_auto_organizer.py`：`classify()` 返回 None、`process_inbox()` 加 None 检查、VALID_CATEGORIES/CATEGORY_LABELS 去"其他"
- `config.py`：VALID_CATEGORIES 移除"其他"
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.44 - 2026-06-27

### 改进

- **比价图日期提取失败时移入 02 待核实** 📋
  - 改进：机票/高铁/住宿比价图类，专用日期提取器失败时不再用通用日期（文件名日期）凑合
  - 三种比价图统一规则：日期提取失败 → 直接移入 `02 待核实/` + 标注原因，等人工核实
  - 原因标注："机票比价图无法提取航班日期" / "高铁比价图无法提取乘车日期" / "住宿比价图无法提取入住日期"

### 变更文件

- `invoice_auto_organizer.py`：三处比价图日期提取 `else` 分支改为 `move_to_review() + continue`
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.43 - 2026-06-27

### 修复（2项）

- **文件名污染分类** 🔴
  - 问题：`reprocess_done_files()` 移回的文件保留旧名（含"机票比价图"），`classify()` 把文件名和 OCR 文本拼接匹配，导致本来就是高铁比价图的文件被文件名劫持为机票比价图
  - 修复：`classify()` 和 `classify_with_subtype()` 中调用 `_clean_filename_for_classify()` 先移除文件名中的已知类别标签再拼接

- **比价页日期兜底提取** 🟡
  - 问题：多日比价页中日期后面是价格网格（非路线），规则7的"城市-城市"上下文匹配不上
  - 修复：新增规则9（兜底规则），无其他规则命中时，取文本中第一个有效 `MM-DD` 作为日期

### 实际效果

| 文件 | 修复前 | 修复后 |
|------|--------|--------|
| WB_061 (G403 武汉-广州) | 机票比价图 | **高铁比价图** ✅ |
| WB_062 (G7118 上海-苏州) | 机票比价图 | **高铁比价图** ✅ |
| WB_054 (比价页) | 日期=06-24(错) | 日期=**06-12** ✅ |
| WB_055 (比价页) | 日期=06-24(错) | 日期=**06-14** ✅ |
| WB_063 (比价页) | 日期=06-24(错) | 日期=**06-13** ✅ |

### 变更文件

- `invoice_auto_organizer.py`：`classify()` + `classify_with_subtype()` 文件名清洗 + `extract_date_for_flight_comparison()` 规则9兜底
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.42 - 2026-06-27

### 修复

- **OTA截图日期提取：OCR将"-"误识为"一"导致路线匹配失败** ✈️
  - 问题：OCR 将 `广州-上海` 识别为 `广州一上海`（"-"→"一"），规则7路线匹配 `[-—→]+` 不含"一"，导致日期提取失败
  - 修复：规则7两处路线分隔符正则从 `[-—→]+` 改为 `[-—→一]+`
  - 测试：`at 5月6日 周三 10:50 广州一上海` → 2026-05-06 ✅

### 变更文件

- `invoice_auto_organizer.py`：`extract_date_for_flight_comparison()` 规则7 两处路线分隔符加"一"
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.41 - 2026-06-27

### 修复

- **OTA截图日期提取：OCR乱码前缀导致规则7失效** ✈️
  - 问题：OCR 将"直飞"识别为乱码（如 `Els)`），导致 `03-11` 前面有非数字前缀，规则7的行首限制 `(?:^|\n\s*)` 匹配不上
  - 修复：规则7行首限制从 `(?:^|\n\s*)` 放宽为 `(?:^|\n|[^\d])`，允许日期前面有非数字字符
  - 测试：`Els) 03-11 周三 深圳-上海 2小时10分钟` → 2026-03-11 ✅

### 变更文件

- `invoice_auto_organizer.py`：`extract_date_for_flight_comparison()` 规则7 行首限制放宽
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.40 - 2026-06-27

### 修复

- **`reprocess_done_files()` 目录遍历 bug** 🔴
  - 问题：函数假设 03 已完成/ 下是 `年/月/文件` 三层结构，但实际是 `YYYY-MM/文件` 两层结构，导致 69 个文件全部被跳过
  - 修复：改为自动检测子目录结构，兼容 `YYYY-MM/文件`（两层）和 `YYYY年/MM月/文件`（三层）

- **`extract_amount_for_flight_comparison` 函数定义丢失** 🔴
  - 问题：V1.0.39 编辑日期提取函数时误删了 `def extract_amount_for_flight_comparison(text):` 函数声明行
  - 修复：补回函数定义行

### 变更文件

- `invoice_auto_organizer.py`：`reprocess_done_files()` 重写目录遍历逻辑 + 补回函数定义
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.39 - 2026-06-27

### 修复

- **机票比价图日期提取：OCR空格干扰** ✈️
  - 问题：OCR 将 `5月6日` 识别为 `5 月 6 日`（数字与"月""日"间多出空格），正则 `(\d{1,2})月(\d{1,2})日` 不匹配
  - 修复：规则3 正则改为 `(\d{1,2})\s*月\s*(\d{1,2})\s*日`，兼容 OCR 空格干扰
  - 测试通过：`直飞 5 月 6 日 周三` → 2026-05-06 ✅
  - `直飞 01-27 周二` 格式原本已支持（规则2），无需改动

### 变更文件

- `invoice_auto_organizer.py`：`extract_date_for_flight_comparison()` 规则3 正则加 `\s*` 容错
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.38 - 2026-06-27

### 新增

- **机票比价图支持"单程"日期格式** ✈️
  - OTA 截图常见"单程 4月9日"格式，原日期提取逻辑不识别
  - `extract_date_for_flight_comparison()` 新增第 8 步：匹配 `单程 + 月日/完整日期`
  - 支持格式：`单程 4月9日` / `单程 04-09` / `单程 4/9` / `单程 2026-04-09`
  - "单程"同时加入机票比价图关键词列表，提高分类命中率

### 变更文件

- `invoice_auto_organizer.py`：CATEGORY_RULES 机票比价图加"单程"关键词 + `extract_date_for_flight_comparison()` 加第 8 步
- `config.py`：CATEGORY_RULES 同步加"单程"关键词
- `VERSION` / `CHANGELOG.md` / `SKILL.md`：版本三件套更新

## 1.0.37 - 2026-06-27

### 修复

- **`__pycache__` 缓存导致升级后旧代码仍生效** 🔴
  - 问题：`deploy.py --upgrade` 和 `version_manager.py` 更新了 `.py` 源文件，但 Python 加载的是 `__pycache__/` 中的旧 `.pyc` 字节码缓存，导致用户升级后分类逻辑等关键变更"看起来没生效"
  - 实际案例：V1.0.36 修复了高铁比价图分类规则，但用户升级后重新识别仍被误判为"机票比价图"，根因就是 `.pyc` 缓存
  - 修复：`deploy.py` 和 `version_manager.py` 在复制完新文件后，自动 `shutil.rmtree(__pycache__)`，强制下次运行重新编译

### 变更文件

- `deploy.py`：`_do_deploy_from()` 中新增 `__pycache__` 清理步骤
- `version_manager.py`：`auto_update()` 中新增 `__pycache__` 清理步骤
- `VERSION`：1.0.36 → 1.0.37
- `CHANGELOG.md`：新增 1.0.37 条目

## 1.0.36 - 2026-06-25

### 修复（7个 Bug 修复，基于 Mia V1.0.35 反馈报告）

- **Bug 1: OTA截图金额误识别（OCR数字粘连）** 🔴
  - 问题：OCR把并排价格读成天文数字（如 `¥1290 ¥6020` → `¥142032`）
  - 修复：金额提取后加合理性校验，个人差旅单张 > ¥50,000 标记待核实
  - 所有比价图金额提取函数上限从 100000 改为 50000

- **Bug 2: 机票关键词缺失 → 全归"其他"** 🔴
  - 问题：携程截图含"经济舱""机建燃油""票价""托运"，但机票关键词列表缺失
  - 修复：补充这4个高频OTA词到机票关键词列表

- **Bug 3: 充电费优先级高于机票** 🟡
  - 问题：CATEGORY_RULES 中充电费排在机票前面，"充电宝禁止携带" → 匹配"充电"
  - 修复：① 机票规则提到充电费之前 ② 充电费关键词移除"充电"，仅保留"充电费"精确匹配
  - "充电宝禁止携带"不再误触发充电费分类

- **Bug 4: PDF酒店水单被误拒** 🟡
  - 问题：维也纳酒店水单PDF被 `has_invoice_markers()` 拦截（无发票特征词）
  - 修复：① INVOICE_CONTENT_MARKERS 增加水单特征词（水单/入离日期/入住人/酒店名称/房费/携程订单/预订确认/订单号/入住日期）
  - ② 增加 fallback：金额+日期都提取成功时即使无发票特征词也放行

- **Bug 5: 19张金额提取失败** 🟡
  - 问题：OTA价格格式 `¥1290起`（"起"后缀）和 `¥xxx+¥yyy`（复合价格）正则不匹配
  - 修复：① 所有金额正则增加 `起` 后缀过滤 ② 新增复合价格支持（取两个金额之和）
  - 覆盖 extract_amount_from_text / extract_amount_for_flight_comparison / extract_amount_for_train_comparison / extract_amount_for_hotel_comparison

- **Bug 6: 刷新≠文件识别功能混淆** 🟢
  - 问题：用户执行"刷新"期望02待核实被重处理，但refresh.py只更新台账和总览
  - 修复：refresh.py 开头检测02待核实是否有文件 > 0，有则提示用户先跑文件识别

- **Bug 7: deploy.py SKILL_VERSION不更新** 🟢
  - 问题：`deploy.py --upgrade` 成功后 config.py 中 SKILL_VERSION 仍为旧版本号
  - 修复：`_do_deploy_from()` 中新增 `_update_skill_version()` 和 `_update_refresh_version_in_deploy()` 调用
  - 升级后自动更新 config.py 中的 SKILL_VERSION 和 LAST_REFRESH_VERSION

### 变更文件

- `invoice_auto_organizer.py`：CATEGORY_RULES 重排+关键词补充、INVOICE_CONTENT_MARKERS 补充水单词、金额合理性校验、OTA价格格式支持
- `config.py`：CATEGORY_RULES 同步重排+关键词补充
- `deploy.py`：新增 `_update_skill_version()` / `_update_refresh_version_in_deploy()` 函数
- `refresh.py`：新增 02待核实 文件检测提示
- `VERSION`：1.0.35 → 1.0.36
- `CHANGELOG.md`：新增 1.0.36 条目

## 1.0.35 - 2026-06-25

### 新增

- **刷新自动核查 03 已完成**：刷新功能新增 Phase 0c「版本核查」
  - 新增 `LAST_REFRESH_VERSION` 配置项，追踪上次完整刷新版本
  - 升级后首次刷新时，自动把 03 已完成 中所有文件移回 01 待分类，用最新规则重新 OCR/分类/命名
  - 版本相同时跳过（零开销），只在升级后触发

### 变更文件

- `config.py` / `config_template.py`：新增 `LAST_REFRESH_VERSION` 字段
- `setup.py`：初始化 config 时生成 `LAST_REFRESH_VERSION`
- `version_manager.py`：新增 `_update_refresh_version()` 函数
- `invoice_auto_organizer.py`：新增 `reprocess_done_files()` — 遍历 03 已完成 年/月子目录，全部移回 01 待分类
- `refresh.py`：新增 Phase 0c + `update_refresh_version()` — 版本比较 → 文件迁移 → 重新分类 → 更新版本标记

## 1.0.34 - 2026-06-25

### 修复

- **机票比价图金额提取优先级错误**：原逻辑优先取「机场燃油」金额，但 OTA 截图中的总价（如 ¥3349）才是用户关心的票价。`extract_amount_for_flight_comparison` 重构优先级：
  1. **总价标签优先**：合计/应付/总价/实付/需付/同意付款 等标签附近的 ¥金额
  2. **降级：最大金额**：图片中所有 ¥金额取最大（过滤 <10 和 >100000）
  3. **再降级：燃油费**：机场燃油/机建燃油/燃油附加费（仅前两步取不到时用）
- **「机建燃油」识别遗漏**：原 regex 只匹配「机场燃油」，不匹配「机建燃油」（场 vs 建一字之差），导致降级到模糊「燃油」匹配返回 220 而非 3349。现统一为 `(?:机场|机建)燃油`
- **Step 4 阻止 Step 5 的 bug**：原第 4 步模糊匹配 `燃油` 在 `机建燃油` 中命中后直接返回 220，导致第 5 步「取最大金额」永不执行。重排后最大金额在燃油费前面，不再被阻塞

## 1.0.33 - 2026-06-25

### 改进

- **目录结构拆分**：原"02 行程与员工报销单"拆分为"02 行程"和"03 报销单"两个独立目录
  - `TRIP_BASE_REL` 由 `个人行程与报销/02 行程与员工报销单` 改为 `个人行程与报销/02 行程`
  - 新增 `REIMBURSEMENT_BASE_REL = "个人行程与报销/03 报销单"` 和 `REIMBURSEMENT_ROOT`
  - 报销单 Excel 模板生成到 `03 报销单/年/月/` 而非行程文件夹内
  - 所有 Obsidian 链接路径同步更新
  - `rename_update.py` 新增 `migrate_trip_reimbursement_split()` 迁移函数：
    - 重命名物理目录 `02 行程与员工报销单` → `02 行程`
    - 创建 `03 报销单` 目录
    - 将行程文件夹中的 `*-报销单.xlsx` 移到 `03 报销单/年/月/`
    - 更新 config.py 路径 + 追加新配置项
  - `refresh.py` 新增 Phase 0b 行程/报销单拆分迁移检查
  - `setup.py` 初始化时分别创建 `02 行程` 和 `03 报销单` 目录

## 1.0.32 - 2026-06-25

### 改进

- **品牌名更新**：Skill 对外展示名由"个人行程与报销"更名为"行程报销管家"（Trip Expense Butler）
  - SKILL.md 标题与 description 更新为新品牌名
  - 技术标识符 `invoice-trip-organizer`（目录名/触发词/配置路径）保持不变，避免破坏性改动
  - 底层数据目录名"个人行程与报销"保持不变（以 config.py 中 TRIP_BASE_REL 为唯一来源）

## 1.0.31 - 2026-06-25

### 修复

- **比价图截图被 has_invoice_markers 拦截**（使用者反馈根因修复）：
  - **图片跳过 has_invoice_markers 检查**：该检查是为过滤非发票 PDF 设计的，OTA 比价截图虽无发票特征词但仍有归档价值，图片（截图/拍照）一律跳过此检查
  - **CATEGORY_RULES 重排**：所有比价图规则提到最前面（机票比价图 → 高铁比价图 → 住宿比价图），防止 OTA 截图中的酒店交叉推广广告词（"酒店"/"入住"）抢先匹配住宿规则
  - **机票比价图关键词扩充**：新增"飞常准"/"值机柜台"/"登机口"/"准点分析"/"前序航班"/"行李转盘"/"到达口"等航班动态截图专用词；新增"机建燃油"/"余票紧张"/"免费手提行李"等 OTA 预订截图词
  - **高铁比价图关键词扩充**：新增"历时"/"检票口"/"询车票"等 12306 截图专用词
  - **机票比价图关键词精简**：移除泛化 OTA 词（"携程"/"飞猪"/"去哪儿"/"同程旅行"/"Ctrip"/"Trip.com"/"预订成功"/"预定成功"/"订单详情"），防止酒店截图被误分类为机票比价图
- 测试结果：39 张 02 待核实截图重新测试，36 张正确识别为比价图（机票比价图 30 + 高铁比价图 6），0 张被 has_invoice_markers 拦截

## 1.0.30 - 2026-06-25

### 改进

- **02 待核实文件重新识别**：文件识别时，自动把 02 待核实/ 中的文件移回 01 待分类/ 重新识别
  - 解决升级后新增类别（高铁比价图、住宿比价图）无法识别已在 02 待核实的旧文件的问题
  - 移回前检查 01 待分类/ 中是否已有同名文件，避免覆盖
  - 移回的文件将在 Phase 1 用最新逻辑重新识别

## 1.0.29 - 2026-06-25

### 修复

- **"联系人信"再加固**：`extract_passenger_name` 三个匹配模式（标签/OTA/通用）全部添加排除词校验（联系人、乘客、新增、姓名、选择、请填写、填写人、购票、登机、信息、明细），防止"联系人信息"等 UI 标签跨行误匹配为乘机人姓名
- Pattern 1/3 正则 `\s` → `[ \t]` 禁止跨行匹配

## 1.0.28 - 2026-06-25

### 新增

- **高铁比价图类别**：新增"高铁比价图"文件识别类别，用于识别 12306/携程/飞猪等 OTA 平台的高铁票价比较截图（非报销凭证）。
  - 识别关键词：乘车人、车次、运行时间、出发站、到达站、12306、抢票、候补等
  - 日期提取：支持乘车日期/出发日期标签 + OTA 裸日期（附近有车次/运行时间）
  - 金额提取：支持票价/总价标签 + 二等座/一等座/商务座等级金额 + 降级取最大金额
  - 路线提取：复用高铁站名映射（extract_route_for_gaotie）
  - 乘车人提取：复用 extract_passenger_name，传入 ['乘车人'] 标签
  - 归入"机票高铁"子目录，标记为非报销（NON_REIMBURSE）
- **住宿比价图类别**：新增"住宿比价图"文件识别类别，用于识别携程/美团/飞猪等 OTA 平台的酒店价格比较截图（非报销凭证）。
  - 识别关键词：房型、大床房、双床房、标准间、入住人、连住、每晚等
  - 日期提取：支持入住日期/入住标签 + OTA 裸日期（附近有酒店/每晚/连住/房型）
  - 金额提取：支持总价/总额标签 + 每晚/房费单价 + 降级取最大金额
  - 城市提取：复用 extract_lodging_city
  - 入住人提取：复用 extract_passenger_name，传入 ['入住人'] 标签
  - 归入"住宿"子目录，标记为非报销（NON_REIMBURSE）
- **extract_passenger_name 泛化**：支持传入 labels 参数，适配乘机人/乘车人/入住人多种标签。

### 修复

- **油电类"燃油"关键词误匹配**：`油电类` 关键词 `"燃油"` 会匹配到 `"机场燃油"` 的子串，导致含"机场燃油"的机票比价图被误分类为油电类。改为 `"燃油费"` 更精确匹配。

## 1.0.27 - 2026-06-25

### 修复

- **乘机人提取跨行匹配 bug**：`extract_passenger_name` 的 Pattern 1 正则 `乘机人[：:\s]+` 中 `\s` 包含换行符，导致「十新增乘机人」末尾 + 换行 + 下一行「联系人信息」被跨行匹配为"联系人信"。改为 `[ \t]` 禁止跨行。
- **新增 OTA 截图乘机人识别**：增加 Pattern 2（身份证附近的独立中文姓名），支持去哪儿/飞猪/携程等 OTA 预订截图中无标签的乘机人姓名提取，同时排除「联系人信息」等标题文字误匹配。

## 1.0.26 - 2026-06-25

### 改进

- **无年份日期改用动态当前年份**：`extract_date_for_flight_comparison` 和 `extract_date_from_filename` 中所有硬编码的 `2026` 替换为 `datetime.now().year`，确保跨年后自动适配。

## 1.0.25 - 2026-06-25

### 修复

- **机票比价图 OTA 裸日期提取失败**：去哪儿/飞猪/携程等预订截图的航班日期以 `MM-DD` 裸格式显示（如 `01-04 周日 广州-上海`），前面无"直飞""出发日期"等标签词，原有 6 种正则模式全部 miss，降级使用截图文件名日期（错误）。修复：新增第 7 种模式（OTA 裸日期 + 路线信息），识别行首/换行后独立 `MM-DD` 后跟城市-城市路线或航班时长信息的场景。

## 1.0.24 - 2026-06-25

### 修复

- **金额解析不支持整数格式**：`extract_amount_from_text` 所有策略均要求 `\.\d{2}`（两位小数），导致 `¥1129`（整数）无法识别。修复：策略 1-8 改为 `([\d,]+(?:\.\d{1,2})?)` 兼容整数和小数；策略 9（全文兜底）保持仅小数防止误匹配。
- **机票比价图降级金额同样不支持整数**：`extract_amount_for_flight_comparison` 降级策略 5 同样修复。
- **`process_inbox()` 中 `OCR_AVAILABLE` 作用域 bug**：V1.0.23 新增 Tesseract 自动安装后在函数内赋值 `OCR_AVAILABLE = True`，Python 将其视为局部变量导致 `UnboundLocalError`。修复：添加 `global OCR_AVAILABLE` 声明。

### 改进

- **机票比价图分类扩展**：新增 OTA 平台关键词（飞猪、携程、Ctrip、Trip.com、去哪儿、同程旅行、预订成功、订单详情、出发城市、到达城市、起降时间、航班动态），让飞猪/携程预订截图正确匹配 机票比价图 而非 机票（后者会因无发票特征词被移入待核实）。
- **机票比价图日期提取扩展**：`extract_date_for_flight_comparison` 新增"出发日期"、"起飞时间"、"乘机日期"、"航班日期"、"出发时间"、"行程日期" + 日期的识别模式，不再仅依赖"直飞"关键词。
- **新增策略 5b**：`extract_amount_from_text` 新增"总价/订单金额/票价/总金额/合计金额/实付"+ 金额的识别，覆盖预订截图无 ¥ 前缀的场景。
- **NON_REIMBURSE / CAT_ORDER fallback 补全**：`_gen_master_ledger` 硬编码 fallback 补入"机票比价图"。

## 1.0.23 - 2026-06-24

### 新功能

- **Tesseract OCR 自动安装**：新增 `check_and_install_tesseract()` 函数，在三个场景自动检测并尝试安装：
  - `setup.py` 初始化时：创建目录后自动检查，macOS 下通过 `brew install tesseract tesseract-lang` 自动安装
  - `deploy.py` 升级时：升级完成后自动检查，提示安装状态
  - `invoice_auto_organizer.py` 文件识别时：检测到图片但 OCR 不可用时，自动尝试安装，安装成功后立即重新识别
- macOS 下全自动（Homebrew 安装不需要 sudo），Ubuntu/Windows 给出安装命令引导用户手动执行

## 1.0.22 - 2026-06-24

### 修复

- **目录名迁移链式替换导致 "01 01" 重复**：`migrate_directory_name()` 更新 config.py 时遍历全部旧名列表（`["01 发票整理", "文件识别整理"]`）逐个替换，第一次 `"01 发票整理"` → `"01 文件识别整理"` 后，第二次 `"文件识别整理"` 又匹配到结果中的子串，产生 `"01 01 文件识别整理"`。修复：只替换实际检测到的旧名，不再遍历全部。

## 1.0.21 - 2026-06-24

### 修复

- **目录名迁移对 os.path.join 格式 config.py 失效**：`migrate_directory_name()` 原先用正则提取 `BASE_ROOT`，但其他使用人的 config.py 从 `config_template.py` 生成，`BASE_ROOT` 是 `os.path.join()` 计算式而非字符串字面量，正则匹配不到导致迁移静默失败。修复：改为动态加载 config 模块获取实际计算路径，兼容两种 config 格式。

### 改进

- **升级时自动检测目录名迁移**：`deploy.py` 升级流程新增目录名迁移检测步骤，升级完成后自动执行 `migrate_directory_name()`，不再依赖使用人手动运行「刷新」。迁移成功后提示运行「刷新」更新所有数据。

## 1.0.20 - 2026-06-24

### 改进

- **OCR 依赖检测提示**：当待分类目录中有图片文件但 Tesseract OCR 未安装时，脚本启动时自动打印安装指引（macOS/Ubuntu/Windows），避免使用人不知道为何图片全被移到待核实。
- **SKILL.md 依赖安装说明完善**：新增 Tesseract OCR 引擎安装表格（含中文语言包），覆盖 macOS/Ubuntu/Windows 三平台；新增"图片发票全被移到 02 待核实"常见问题解答。

### 修复

- **`extract_invoice_number` 函数丢失 bug**：V1.0.18 添加"机票比价图"功能时，`extract_passenger_name` 函数的代码意外覆盖了 `extract_invoice_number` 的 `def` 行，导致该函数被调用 7 次但从未定义，文件识别整理直接报 `NameError`。修复：补回 `def extract_invoice_number(text):` 函数定义行。

## 1.0.18 - 2026-06-24

### 新增

- **机票比价图类别**：新增"机票比价图"文件识别类别
  - 识别关键词：直飞、乘机人、托运行李、机场燃油、机票比价
  - 日期提取：从"直飞"后提取航班日期（支持多种格式：06-15 / 2026-06-15 / 06月15日）
  - 金额提取：优先提取"机场燃油"金额，降级取图片最大金额
  - 路线提取：城市-城市格式（如 广州-上海）
  - 乘机人：提取乘机人姓名代替购买方简称
  - 属于非报销凭证（NON_REIMBURSE），归入"机票高铁"子目录
  - 跳过发票特征词检查（比价截图不是发票）
  - 涉及文件：config.py, config_template.py, invoice_auto_organizer.py, trip_auto_organizer.py, SKILL.md

## 1.0.17 - 2026-06-24

### 变更

- **目录重命名**：`文件识别整理` → `01 文件识别整理`（恢复序号前缀，与 02 行程目录保持编号一致）
  - config.py / config_template.py / setup.py 中所有路径引用同步更新
  - invoice_auto_organizer.py 中 Obsidian wikilink 链接同步更新
  - release_check.py 测试路径同步更新
  - rename_update.py `migrate_directory_name()` 升级为多旧名迁移（支持 `01 发票整理` 和 `文件识别整理` 两个旧名）
  - SKILL.md 目录结构引用同步更新

## 1.0.16 - 2026-06-24

### 变更

- **目录重命名**：`01 发票整理` → `文件识别整理`（文件不只是发票，会有不同类型的文件）
  - config.py / config_template.py / setup.py 中所有路径引用同步更新
  - invoice_auto_organizer.py 中 Obsidian wikilink 链接同步更新
  - release_check.py 测试路径同步更新
  - rename_update.py 新增 `migrate_directory_name()` 目录迁移函数
  - refresh.py 新增 Phase 0 目录名迁移检查（升级后自动检测并迁移旧目录名）
- **命令重命名**：`发票整理` → `文件识别`
  - SKILL.md trigger 列表更新
  - 各脚本中的提示文案同步更新
- **删除触发词**：移除 `跑一次发票整理`、`有新行程`、`从邮件下载发票` 三个触发词
- **行程状态文案**：行程总览中状态从 `发票整理中` 改为 `文件整理中`
- **文件清单补全**：setup.py / deploy.py / version_manager.py 的 SCRIPT_FILES 列表补充 `refresh.py` 和 `rename_update.py`

## 1.0.15 - 2026-06-24

### 新增

- **刷新命令** (`refresh.py`)：升级版本后一键将所有已有数据更新到最新规则
  - Phase 1 数据迁移：重新识别 03 已完成中所有文件的类别和购买方简称（集成 rename_update.py）
  - Phase 2 行程刷新：扫描所有已有行程，从 03 已完成重新匹配发票，清空旧副本重新复制
    - 重新生成发票清单、行程详情、行程总览（确保格式和链接为最新版本）
    - 餐饮发票归档到月度餐饮目录
  - Phase 3 台账重生成：重新扫描 03 已完成生成台账
  - 支持 `--dry-run` 预览模式
  - SKILL.md 新增「刷新操作指引」章节，trigger 列表新增"刷新"

## 1.0.14 - 2026-06-24

### 改进

- **餐饮发票独立管理**：餐饮类发票不再放入行程文件夹，改为按月归档到月度目录下的"餐饮"文件夹
  - 行程文件夹的 `02-发票文件/` 不再创建"餐饮"子目录（SUBDIRS 移除"餐饮"）
  - 新增 `copy_dining_to_monthly()` 函数，将餐饮发票复制到 `{年} 年/{月} 月/餐饮/` 目录
  - `copy_invoices_to_trip()` 跳过餐饮类文件，`clear_existing` 时自动清除旧的餐饮子目录
  - 发票文件清单.md 不再包含餐饮明细，改为添加指向月度餐饮目录的链接
  - 行程详情.md 发票文件列表移除餐饮链接，改为指向月度餐饮目录
  - `import_trips.py` 批量导入同步支持餐饮独立归档
  - `config.py` / `config_template.py` 的 SUBDIRS 移除"餐饮"

## 1.0.13 - 2026-06-24

### 新增

- **行程去重机制**：新增行程时按日期范围自动检测是否已存在，已有则复用并刷新发票，不再创建重复行程目录
  - `trip_auto_organizer.py` 新增 `find_existing_trip()` 函数，扫描所有已有行程按日期匹配
  - 复用时自动清空旧发票附件，重新从 03 已完成复制最新数据
  - `import_trips.py` 批量导入时同步支持：已存在行程自动刷新而非跳过
- **升级后数据迁移自动化**：版本升级时自动检测已有文件是否需要更新（类别重分类 / 购买方简称）
  - `deploy.py --upgrade` 和 `version_manager.py` 升级流程自动集成迁移检测
  - 新增 `LAST_MIGRATION_VERSION` 配置项，记录已迁移版本，避免重复检测
  - `rename_update.py` 新增 `--check` 模式，静默检测并输出 JSON，供升级流程程序化调用
  - `deploy.py` 新增 `--migrate` 参数，直接执行数据迁移
  - 迁移完成后自动更新 `LAST_MIGRATION_VERSION`，重新生成台账
- **发票归档通用去重机制**：无发票号的文件（ETC/滴滴网页打印件等）按日期+类别+金额匹配 03 已完成，命中则自动删除，不再产生重复归档
  - 三层去重：① 发票号去重 ② 行程单与发票交叉去重 ③ 通用日期+类别+金额去重
  - 覆盖 OFD/XML/PDF 三条处理路径
- **邮箱下载双层去重**：下载发票附件时自动去重，不再重复下载已存在的文件
  - 第一层：邮件 Message-ID 去重，已下载过的邮件直接跳过，记录保存在 `~/.invoice-trip/downloaded_msgids.json`
  - 第二层：附件内容 MD5 去重，预扫描 01 待分类 + 03 已完成构建哈希索引，下载附件后比对 MD5，命中则不保存
  - 实时更新索引，同批次内不同邮件含相同附件也能去重
  - 归档后实时更新索引，同批次内重复也能捕获

### 修复

- **`rename_update.py` 循环依赖 bug**：重分类时 `classify_with_subtype(text, fn)` 传了文件名，旧文件名中的类别名（如"充电费"）被当成关键词匹配，导致永远检测不到需要重分类。修复：只传 text 不传 fn。

## 1.0.12 - 2026-06-24

### 新增

- **发票文件名增加购买方公司简称**：自动从发票内容提取购买方名称，生成简称后写入文件名。
  - 标准命名格式：`日期_类别_金额[_路线][_购买方简称]_MMDD_WB/YB_NNN.ext`
  - 简称生成算法：去省市前缀 → 去公司类型后缀 → 去尾部描述词 → 超 6 字取前 4 字
  - 向后兼容：旧格式文件名（无购买方简称）正则仍可匹配
- **新增"油电类"分类**：覆盖加油、汽油、供电、电费、充电服务等发票。
  - 关键词：加油、汽油、柴油、中石化、中石油、中海油、壳牌、油品、燃油、加油站、供电、电费、充电服务
  - 归档子目录：其他（与充电费/高速费一致）
- **新增 `rename_update.py` 升级数据迁移工具**：版本升级后一键迁移已有数据。
  - 类别重分类：用最新 CATEGORY_RULES 重新扫描已有文件，类别不符的自动更新
  - 购买方简称补充：对已有文件提取购买方并追加到文件名
  - 安全规则：不从具体类别降级为"其他"，防止文本提取不完整导致误判
  - 支持 `--dry-run` 预览模式
  - 同步更新行程目录中的发票副本

### 修复

- **非发票文件过滤**（双层防护）：
  - 下载层：`is_invoice_filename()` 重写，文件名/邮件主题需含发票关键词，黑名单排除员工手册/发货/申请表/物料等
  - 整理层：新增 `has_invoice_markers()` 内容特征词校验，非发票内容移入待核实
- **邮箱下载默认弹窗**：默认弹出邮箱选择窗口（原默认自动用上次邮箱），`--auto` 才自动选择
- **显示名称输入框高度**：修复 macOS 上 `entry.insert()` 在 `pack()` 前执行导致高度异常
- **充电费/油电类关键词冲突**：`"充电"` → `"充电费"` 精确匹配，充电费规则移到油电类之前，避免子串误匹配

### 改进

- `trip_auto_organizer.py` 正则同步更新，支持购买方简称，行程后续流程可正确匹配
- `download_invoices.py` 默认行为翻转，多邮箱用户不再需要每次加 `--pick`
- SKILL.md 新增"升级后数据迁移"说明段落

## 1.0.11 - 2026-06-24

### 新增

- 住宿类发票命名增加酒店所在城市字段，例如：`2026-01-12_住宿_264.00_中山_0112_WB_043.pdf`。
- 城市提取优先级：销售方名称 → 酒店/住宿关键词行 → 地址字段 → 全文城市关键词。
- 标准命名正则支持单城市字段，也继续兼容机票/高铁的 `出发地-到达地` 字段。
- 用户升级后首次运行发票整理时，会对 `03 已完成/` 内既有住宿类文件、以及原行程目录 `02-发票文件/住宿/` 内的住宿类发票副本执行一次迁移；能识别城市的文件会自动补入城市字段。
- 行程附件文件名迁移后，会同步刷新对应行程的 `发票文件清单.md`。
- 迁移完成后写入 `.migration_lodging_city_v1_0_11.done` 标记，避免每次重复重命名。
- 修复 `version_manager.py` 自动升级清单，确保其他人升级时同步 `import_trips.py`、`deploy.py`、`release_check.py`、`config_template.py`。
- 发布检查新增住宿城市提取与单城市命名验证。

## 1.0.10 - 2026-06-24

### 修复

- 修复 WorkBuddy 触发「新增行程」时不弹窗的问题。
- 原因：宿主可能将触发词写入 stdin，脚本误认为 stdin 已提供数据，解析失败后退出。
- 现在只有 stdin 内容能解析出有效行程时才走管道输入；如果 stdin 只是触发词或其他无效文本，则继续打开输入窗口。
- 更新 WorkBuddy `SKILL.md`：本机正常使用以弹窗输入为主，Codex/自动化测试才使用管道输入。
- 修复 `deploy.py` 部署清单漏掉 `import_trips.py`，导致 WorkBuddy 运行目录未同步新脚本的问题。

## 1.0.9 - 2026-06-24

### 修复

- 修复源码目录 `import_trips.py` 缺少已记录的 `--file/-f` 文件输入模式问题。
- 保留并验证 stdin 管道输入：`printf ... | python3 import_trips.py`。
- 修正 Codex 专用 Skill 示例命令，要求先进入初始化后的 `个人行程与报销/scripts` 目录再执行管道导入。
- 发布检查新增 WorkBuddy 部署脚本与源码脚本一致性检查，避免再次出现三处漂移。

## 1.0.8 - 2026-06-24

### 新增

- 新增 `release_check.py`，作为发布前统一门禁，检查版本、跟踪文件、必需资源、Python 编译、本地安装版本和 Codex 校验。
- `setup.py init` 新增 `--base-dir` 参数，支持无界面初始化，便于自动化测试和 demo-safe 验证。
- 新增 `docs/SOP-发票文件命名标准.md`，初始化时复制到用户工作目录。

### 修复

- 修复初始化复制清单漏掉 `import_trips.py` 的问题。
- 修复初始化 SOP 文档路径错误，避免发布包缺资源。
- 删除根层 `scripts/*.py` 旧副本，统一以 `scripts/invoice-trip-organizer/` 作为唯一源码目录。
- 移除标准脚本中的本机 `NoBusy-Demo` 硬编码兜底路径。
- 修复行程详情链接使用 `01 月` 导致与实际 `1 月` 目录不一致的问题。
- 修复空发票整理时把 `日志.md`、`台账.md` 计入发票数量的问题。

## 1.0.7 - 2026-06-24

### 修复

- 统一项目源码、WorkBuddy 安装目录、GitHub 仓库的版本号为 1.0.7。
- 修复 `config_template.py` 路径变量，补齐脚本实际使用的 `BASE_ROOT`、`INVOICE_ROOT`、`TRIP_ROOT` 等配置。
- 修复初始化配置默认版本号仍为 1.0.6 的问题。
- 移除标准脚本中的本机 `NoBusy-Demo` 硬编码兜底路径，未初始化时改为明确提示先运行 `setup.py init`。

### 新增

- `import_trips.py` 支持 `--file/-f` 文件输入模式。
- README 记录 WorkBuddy 安装目录、本地项目目录、GitHub 仓库三处固定路径。

## 1.0.0 - 2026-06-23

### 初始发布

- **发票自动整理**：PDF 发票识别、分类、归档、命名标准化、台账生成
- **行程自动整理**：创建行程文件夹、匹配发票、生成清单和总览
- **邮件下载发票**：支持多邮箱（163/QQ/126/自定义），IMAP 下载
- **上传文件**：系统弹窗选择文件，自动复制到 01 待分类
- **初始化设置**：自动创建目录结构、生成 config.py、复制 SOP 文档
- **重置功能**：确认后删除目录，可选重新初始化
- **版本管理**：引入 Semantic Versioning，支持自动更新

### 修复记录

- 修复 `trip_auto_organizer.py` 中 `TRIP_BASE` 未定义变量（应为 `TRIP_ROOT`）
- 修复 `init.py` 依赖检查包名错误（`fpdf2`→`fpdf`, `pillow`→`PIL`）
- 修复 `invoice_auto_organizer.py` 中 `link_to_trips` 路径错误
- 修复 `trip_auto_organizer.py` 正则表达式不匹配完整文件名
- 修复月份目录名不一致（`"06 月"` vs `"6 月"`）
- 修复 `audit_03_done.py` 硬编码路径
- 修复 `SKILL.md` 文档中命令路径缺少 `scripts/` 前缀



## 1.0.1 - 2026-06-23

### 新增

- **版本管理**：支持自动检测和更新 Skill 版本
- **备份机制**：更新前自动创建 .backup/ 目录，支持回退
- **配置合并**：新版本新增配置项自动合并到用户 config.py

### 改进

- 邮件下载发票后直接放入 01 待分类
- 所有脚本入口自动检查版本并更新


## 1.0.2 - 2026-06-23

### 新增

- **在线升级**：deploy.py 新增 `--upgrade` 命令，一键从 GitHub 拉取最新版本
- **远程检查**：deploy.py 新增 `--check-update` 命令，检查 GitHub 是否有新版本
- **三重降级**：git ls-remote → GitHub API → raw.githubusercontent.com 读取 VERSION 文件
- **配置保护**：升级时绝不覆盖用户 config.py，仅更新脚本和模板文件

### 改进

- SKILL.md description 嵌入版本号，安装列表直接显示当前版本
- SKILL.md 文档增加在线升级使用说明
- 部署工具新增 `--status` / `--backup` / `--force` 命令

### 修复

- 修复导入文件双击选择时窗口重复弹出的问题
  - 原因：osascript 返回非零退出码时回退到 tkinter，导致第二个文件选择窗口弹出
  - 修复：优先检查 stdout 是否有文件路径，有则直接使用；非取消错误直接退出不再回退
  - 修复：`-128 in err_lower` 整数在字符串中查找的 TypeError（改为 `'-128' in err_lower`）


## 1.0.3 - 2026-06-23

### 新增

- **导入行程**：批量导入行程数据（`import_trips.py`）
  - 弹出文本输入窗口，粘贴 Tab 分隔行程数据
  - 支持多种日期格式：`2026-01-04`、`2026/3/11`、`2026.3.11`
  - 自动跳过表头行和空行，支持多块数据混合粘贴
  - 按日期去重：同日期范围已存在则跳过，仅新增不存在的行程
  - 自动创建行程文件夹、行程详情、发票匹配、行程总览更新
  - 支持快捷键：Ctrl+Enter 提交，Esc 取消

### 修复

- 初始化时保留已有 config.py，不覆盖用户配置（邮箱、授权码等）


## 1.0.4 - 2026-06-23

### 修复

- 修复导入行程窗口在其他电脑上不弹出的问题
  - 原因：`show_input_dialog_macos()` 静默吞掉所有异常返回 None，用户只看到"用户取消了输入"
  - 修复：打印实际错误信息，让用户知道是 tkinter 加载失败还是其他问题
  - 新增文件编辑器回退方案：tkinter 不可用时自动创建临时 txt 文件，用系统编辑器打开，保存后自动读取
  - 全平台支持：macOS / Windows / Linux 均有 tkinter → 文件编辑器两级回退

### 改进

- tkinter 导入失败时打印各平台安装指引
- 提交按钮文字增加快捷键提示"提 交 (Ctrl+Enter)"


## 1.0.6 - 2026-06-23

### 修复

- 修复沙箱环境下新增行程 tkinter 窗口无法显示的问题
  - 脚本新增 stdin 管道输入支持：`echo "数据" | python3 import_trips.py`
  - AI 对话场景通过管道传数据，不再依赖 GUI 窗口
  - 终端直跑场景仍可弹窗（保留 tkinter 回退）
  - SKILL.md 新增「新增行程操作指引」章节，AI 按指引在对话中收集数据


## 1.0.5 - 2026-06-23

### 修复

- 修复"导入"触发词与"导入行程"冲突，导致其他电脑用户说"导入"时误触发行程导入
  - 将行程导入触发词从"导入行程"改为"新增行程"，彻底消除歧义
  - "导入"明确指向文件导入功能（upload_files.py）
  - 新增"导入文件"作为同义触发词

### 改进

- import_trips.py 窗口标题、输出提示统一改为"新增行程"
- SKILL.md 触发词列表新增"导入文件"
