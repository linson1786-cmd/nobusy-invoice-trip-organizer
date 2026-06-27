#!/usr/bin/env python3
"""
行程自动整理工具
功能:
  1. 创建新行程文件夹结构（01-行程详情.md + 02-发票文件/6子目录 + 发票文件清单.md）
  2. 从03已完成扫描匹配发票，复制到行程附件目录
  3. 生成行程发票文件清单.md
  4. 更新行程总览.md
  5. 生成报销单模板（发票齐全时）
触发方式: 用户说"有新行程"，助手收集行程信息后调用此脚本

参数:
  --start-date  开始日期 (YYYY-MM-DD)
  --end-date    结束日期 (YYYY-MM-DD)
  --route       途经城市列表 (逗号分隔，如 广州,上海,杭州,成都,重庆,广州)
  --trip-id     出差编号 (如 出差4，可选，自动递增)
  --year        年份 (默认2026)
  --month       月份 (可选，默认按开始日期计算)

使用示例:
  python3 trip_auto_organizer.py --start-date 2026-02-10 --end-date 2026-02-15 --route 广州,北京,天津,广州
"""
import os, re, sys, shutil, json, glob as glob_module
from collections import defaultdict
from datetime import datetime, timedelta

# ===== 尝试从 config.py 读取配置 =====
_script_dir = os.path.dirname(os.path.abspath(__file__))
_config_path = os.path.join(_script_dir, "config.py")
try:
    import importlib.util
    if os.path.exists(_config_path):
        spec = importlib.util.spec_from_file_location("config", _config_path)
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        for _attr in dir(config):
            if _attr.isupper():
                globals()[_attr] = getattr(config, _attr)
        print(f"✅ 已从 config.py 读取配置 (TRIP_ROOT={globals().get('TRIP_ROOT', 'N/A')})")
except Exception as e:
    print(f"⚠️ 读取 config.py 失败: {e}")

# ===== 默认配置：未初始化时保持为空，运行前给出明确提示 =====
if 'BASE_ROOT' not in dir():
    BASE_ROOT = ""
    INVOICE_ROOT = ""
    DONE_DIR = ""
    TRIP_ROOT = ""
    REIMBURSEMENT_ROOT = ""
    if 'REIMBURSEMENT_TEMPLATE' not in dir():
        REIMBURSEMENT_TEMPLATE = ""
    if 'CAT_TO_SUBDIR' not in dir():
        CAT_TO_SUBDIR = {
            "机票": "机票高铁", "机票(保险)": "机票高铁", "机票比价图": "机票高铁", "高铁": "机票高铁",
            "住宿": "住宿", "住宿(结账单)": "住宿",
            "餐饮": "餐饮",
            "滴滴打车": "打车", "滴滴打车(行程单)": "打车",
            "礼品": "礼品",
            "高速费": "其他", "高速费(行程单)": "其他", "充电费": "其他", "油电类": "其他",
            "行程单": "其他", "结账单": "其他", "其他": "其他",
        }
    if 'SUBDIRS' not in dir():
        SUBDIRS = ["机票高铁", "住宿", "打车", "礼品", "其他"]
    if 'NON_REIMBURSE' not in dir():
        NON_REIMBURSE = ["行程单", "滴滴打车(行程单)", "高速费(行程单)", "住宿(结账单)", "结账单", "机票比价图"]

if 'VALID_CATEGORIES' not in dir():
    VALID_CATEGORIES = [
        "餐饮", "住宿", "机票", "机票比价图", "高铁", "滴滴打车", "行程单", "高速费", "充电费", "油电类", "礼品", "结账单", "其他",
        "机票(保险)", "滴滴打车(行程单)", "住宿(结账单)", "高速费(行程单)"
    ]

# 标准文件名正则 (与 invoice_auto_organizer.py 保持一致，支持购买方简称)
STANDARD_NAME_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2})_(' + '|'.join(re.escape(c) for c in VALID_CATEGORIES) + r')_(\d+\.\d{2})'
    r'(?:_([^_\d]+(?:-[^_\d]+)?(?:_[\u4e00-\u9fa5]{2,10})?))?'   # Optional route/city + buyer
    r'(?:_(\d{1,4}))?'            # Optional suffix: 发票号后4位或序号
    r'(?:_(\d{4})_(WB|YB))?'      # Optional status: 操作日期_报销状态(WB未报/YB已报)
    r'(?:_(\d{3}))?'              # Optional seq: 序号编号(3位数字)
    r'(\.\w+)$'
)

# V1.0.58: 比价图文件名正则（无金额字段）
# 格式: YYYY-MM-DD_比价图类别[_路线][_接收航变]_MMDD_WB_NNN.ext
COMPARISON_NAME_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2})_(' + '|'.join(re.escape(c) for c in VALID_CATEGORIES if '比价图' in c) + r')'
    r'(?:_([^_\d]+(?:-[^_\d]+)?))?'    # Optional route
    r'(?:_(\d{4})_(WB|YB))?'            # Optional status
    r'(?:_(\d{3}))?'                    # Optional seq
    r'(\.\w+)$'
)

# 报销单模板路径
TEMPLATE_XLSX = globals().get("REIMBURSEMENT_TEMPLATE", "")


def ensure_configured():
    """确认已完成初始化并存在有效路径配置。"""
    required = {
        "INVOICE_ROOT": INVOICE_ROOT,
        "DONE_DIR": DONE_DIR,
        "TRIP_ROOT": TRIP_ROOT,
        "REIMBURSEMENT_ROOT": globals().get("REIMBURSEMENT_ROOT", ""),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        print("❌ 未完成初始化：缺少路径配置 " + ", ".join(missing))
        print("请先运行：python3 setup.py init")
        return False
    # 补充默认值
    if not globals().get("REIMBURSEMENT_ROOT"):
        globals()["REIMBURSEMENT_ROOT"] = ""
    return True


def get_next_trip_id(year_dir):
    """获取下一个出差编号"""
    max_id = 0
    if os.path.isdir(year_dir):
        for month_dir in os.listdir(year_dir):
            month_path = os.path.join(year_dir, month_dir)
            if not os.path.isdir(month_path):
                continue
            for folder in os.listdir(month_path):
                m = re.match(r'出差(\d+)-', folder)
                if m:
                    max_id = max(max_id, int(m.group(1)))
    return max_id + 1


def find_existing_trip(start_date, end_date):
    """
    扫描已有行程文件夹，按日期范围匹配。
    返回 (trip_dir, folder_name, trip_id) 或 None。
    """
    if not TRIP_ROOT or not os.path.isdir(TRIP_ROOT):
        return None

    # 匹配出差N-YYYY-MM-DD～YYYY-MM-DD_路线
    folder_re = re.compile(
        r'出差(\d+)-(\d{4}-\d{2}-\d{2})[～~](\d{4}-\d{2}-\d{2})'
    )

    for year_name in os.listdir(TRIP_ROOT):
        year_dir = os.path.join(TRIP_ROOT, year_name)
        if not os.path.isdir(year_dir):
            continue
        for month_name in os.listdir(year_dir):
            month_dir = os.path.join(year_dir, month_name)
            if not os.path.isdir(month_dir):
                continue
            for folder_name in os.listdir(month_dir):
                full_path = os.path.join(month_dir, folder_name)
                if not os.path.isdir(full_path):
                    continue
                m = folder_re.match(folder_name)
                if m and m.group(2) == start_date and m.group(3) == end_date:
                    trip_id = int(m.group(1))
                    return (full_path, folder_name, trip_id)

    return None


def parse_args():
    """解析命令行参数"""
    import argparse
    parser = argparse.ArgumentParser(description='行程自动整理工具')
    parser.add_argument('--start-date', required=True, help='开始日期 YYYY-MM-DD')
    parser.add_argument('--end-date', required=True, help='结束日期 YYYY-MM-DD')
    parser.add_argument('--route', required=True, help='途经城市列表(逗号分隔)')
    parser.add_argument('--trip-id', type=int, help='出差编号(可选，自动递增)')
    parser.add_argument('--year', default='2026', help='年份')
    parser.add_argument('--month', help='月份(可选，按开始日期计算)')
    return parser.parse_args()


def create_trip_folder(trip_id, start_date, end_date, route_list, year, month):
    """创建行程文件夹结构"""
    route_str = '-'.join(route_list)
    folder_name = f"出差{trip_id}-{start_date}～{end_date}_{route_str}"
    year_dir = os.path.join(TRIP_ROOT, f"{year} 年")
    month_dir = os.path.join(year_dir, f"{month} 月")
    trip_dir = os.path.join(month_dir, folder_name)

    # 创建目录
    os.makedirs(month_dir, exist_ok=True)
    os.makedirs(trip_dir, exist_ok=True)
    invoice_dir = os.path.join(trip_dir, "02-发票文件")
    os.makedirs(invoice_dir, exist_ok=True)
    for subdir in SUBDIRS:
        os.makedirs(os.path.join(invoice_dir, subdir), exist_ok=True)

    print(f"✅ 创建行程文件夹: {folder_name}")
    return trip_dir, folder_name


def gen_trip_detail_md(trip_id, start_date, end_date, route_list, trip_dir, folder_name):
    """生成01-行程详情.md"""
    days = (datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days

    # YAML frontmatter
    yaml_route = '  - ' + '\n  - '.join(route_list)
    fm = f"""---
trip_id: 2026-{trip_id:02d}
start_date: {start_date}
end_date: {end_date}
departure: {route_list[0]}
return: {route_list[-1]}
route:
{yaml_route}
days: {days}
status: 文件整理中
tags:
  - 行程
  - 出差
---"""

    # 基本信息表
    info_table = f"""
# {start_date}～{end_date} {'-'.join(route_list)}

## 基本信息

| 项目 | 内容 |
|------|------|
| 出差编号 | 出差{trip_id} |
| 开始日期 | {start_date} |
| 返程日期 | {end_date} |
| 天数 | {days}天 |
| 出发/返程 | {route_list[0]} |"""

    # 行程路线 mermaid
    mermaid_edges = ' --> '.join(route_list)
    mermaid = f"""
## 行程路线

```mermaid
graph LR
    {mermaid_edges}
```"""

    # 途中城市表
    cities = ""
    for i, city in enumerate(route_list):
        note = "出发" if i == 0 else ("返程" if i == len(route_list) - 1 else "")
        cities += f"| {i+1} | {city} | {note} |\n"
    cities_table = f"""
## 途中城市

| 序号 | 城市 | 备注 |
|------|------|------|
{cities}"""

    # 发票文件链接
    # 与实际目录名保持一致：1 月、2 月，不使用 01 月。
    month_in_name = f"{int(start_date[5:7])} 月"
    invoice_links = f"""
## 发票文件清单

> 详见 [[个人行程与报销/02 行程/2026 年/{month_in_name}/{folder_name}/02-发票文件/发票文件清单|发票文件清单]]

## 发票文件

- 📁 [[{month_in_name}/{folder_name}/02-发票文件/机票高铁|机票高铁]] — 机票、高铁
- 📁 [[{month_in_name}/{folder_name}/02-发票文件/住宿|住宿]] — 住宿、结账单
- 📁 [[{month_in_name}/{folder_name}/02-发票文件/打车|打车]] — 滴滴打车
- 📁 [[{month_in_name}/{folder_name}/02-发票文件/礼品|礼品]] — 礼品
- 📁 [[{month_in_name}/{folder_name}/02-发票文件/其他|其他]] — 高速费、充电费等
- 🍽️ 餐饮发票不放入行程，按月归档至 [[{month_in_name}/餐饮|{month_in_name}/餐饮]]"""

    md = fm + info_table + mermaid + cities_table + invoice_links

    md_path = os.path.join(trip_dir, "01-行程详情.md")
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f"✅ 生成行程详情: 01-行程详情.md")
    return md_path


def scan_done_invoices(start_date, end_date):
    """扫描03已完成中日期范围内的发票"""
    matched = []
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')

    for month_folder in sorted(os.listdir(DONE_DIR)):
        month_path = os.path.join(DONE_DIR, month_folder)
        if not os.path.isdir(month_path):
            continue
        # 检查月份是否在范围内
        try:
            month_dt = datetime.strptime(month_folder, '%Y-%m')
        except:
            continue
        # 月份范围检查（宽松：开始月前1月到结束月后1月）
        if month_dt < start_dt - timedelta(days=31) or month_dt > end_dt + timedelta(days=31):
            continue

        for fname in sorted(os.listdir(month_path)):
            m = STANDARD_NAME_RE.match(fname)
            if m:
                inv_date = m.group(1)
                category = m.group(2)
                amount = m.group(3)
                route = m.group(4) or ""
                suffix = m.group(5) or ""
                ext = m.group(6)
            else:
                # V1.0.58: 尝试匹配比价图（无金额字段）
                m2 = COMPARISON_NAME_RE.match(fname)
                if not m2:
                    continue
                inv_date = m2.group(1)
                category = m2.group(2)
                amount = "0.00"
                route = m2.group(3) or ""
                suffix = ""
                ext = m2.group(4)

            # 日期范围匹配
            try:
                inv_dt = datetime.strptime(inv_date, '%Y-%m-%d')
            except:
                continue
            if inv_dt < start_dt or inv_dt > end_dt:
                continue

            src = os.path.join(month_path, fname)
            matched.append({
                'date': inv_date,
                'category': category,
                'amount': amount,
                'route': route,
                'suffix': suffix,
                'ext': ext,
                'filename': fname,
                'src_path': src,
                'is_reimburse': category not in NON_REIMBURSE,
                'subdir': CAT_TO_SUBDIR.get(category, '其他'),
            })

    print(f"   扫描到 {len(matched)} 张匹配发票")
    return matched


def copy_invoices_to_trip(matched, trip_dir, clear_existing=False):
    """复制发票到行程附件目录。clear_existing=True 时先清空各子目录旧文件。
    餐饮类文件不放入行程，由 copy_dining_to_monthly() 单独处理。"""
    invoice_dir = os.path.join(trip_dir, "02-发票文件")
    if clear_existing:
        for subdir in SUBDIRS:
            sd = os.path.join(invoice_dir, subdir)
            if os.path.isdir(sd):
                for old_fn in os.listdir(sd):
                    old_path = os.path.join(sd, old_fn)
                    if os.path.isfile(old_path):
                        os.remove(old_path)
        # 清除旧的餐饮子目录（已从SUBDIRS移除，但旧行程可能还有）
        old_dining = os.path.join(invoice_dir, "餐饮")
        if os.path.isdir(old_dining):
            for old_fn in os.listdir(old_dining):
                old_path = os.path.join(old_dining, old_fn)
                if os.path.isfile(old_path):
                    os.remove(old_path)
            try:
                os.rmdir(old_dining)
                print(f"   🧹 已清除旧餐饮子目录")
            except OSError:
                print(f"   ⚠️ 旧餐饮子目录非空，未删除")
        # 清除旧清单
        old_list = os.path.join(invoice_dir, "发票文件清单.md")
        if os.path.exists(old_list):
            os.remove(old_list)
        print(f"   🧹 已清空旧发票附件")
    copied = 0
    for inv in matched:
        if inv['category'] == '餐饮':
            continue  # 餐饮类文件不放入行程，由 copy_dining_to_monthly() 处理
        dest_dir = os.path.join(invoice_dir, inv['subdir'])
        dest = os.path.join(dest_dir, inv['filename'])
        if os.path.exists(dest):
            print(f"   ⏭️ 跳过已存在: {inv['filename']}")
            continue
        shutil.copy2(inv['src_path'], dest)
        copied += 1
        print(f"   📋 复制: {inv['filename']} → {inv['subdir']}/")
    print(f"✅ 复制 {copied} 张发票到行程附件")
    return copied


def copy_dining_to_monthly(year, month):
    """将整个月份的餐饮类发票复制到月度餐饮目录。
    目录结构: {TRIP_ROOT}/{year} 年/{month} 月/餐饮/
    V1.0.61: 扫描整个月份（不依赖行程 matched），确保所有餐饮发票都被复制"""
    # 构造月份文件夹名
    month_str = f"{int(month):02d}"
    month_folder = f"{year}-{month_str}"
    month_path = os.path.join(DONE_DIR, month_folder)

    year_dir = os.path.join(TRIP_ROOT, f"{year} 年")
    month_dir = os.path.join(year_dir, f"{int(month)} 月")
    dining_dir = os.path.join(month_dir, "餐饮")

    # 清空重拷
    if os.path.isdir(dining_dir):
        for old_fn in os.listdir(dining_dir):
            old_path = os.path.join(dining_dir, old_fn)
            if os.path.isfile(old_path):
                os.remove(old_path)
        print(f"   🧹 已清空 {int(month)} 月/餐饮/ 目录")

    if not os.path.isdir(month_path):
        print(f"   ℹ️ 03 已完成 中无 {month_folder} 目录")
        return 0

    # 扫描该月份所有餐饮发票
    dining_items = []
    for fname in sorted(os.listdir(month_path)):
        m = STANDARD_NAME_RE.match(fname)
        if m and m.group(2) == '餐饮':
            dining_items.append({
                'filename': fname,
                'src_path': os.path.join(month_path, fname),
            })

    if not dining_items:
        print(f"   ℹ️ {int(month)} 月无餐饮类发票")
        return 0

    os.makedirs(dining_dir, exist_ok=True)
    copied = 0
    for inv in dining_items:
        dest = os.path.join(dining_dir, inv['filename'])
        shutil.copy2(inv['src_path'], dest)
        copied += 1
        print(f"   📋 复制餐饮: {inv['filename']} → {int(month)} 月/餐饮/")
    print(f"✅ 复制 {copied} 张餐饮发票到 {int(month)} 月/餐饮/")
    return copied


def gen_invoice_list_md(matched, trip_dir, folder_name, month_str):
    """生成发票文件清单.md（不含餐饮，餐饮单独放月度目录）"""
    invoice_dir = os.path.join(trip_dir, "02-发票文件")

    # 过滤掉餐饮类（不列入行程发票清单）
    matched = [inv for inv in matched if inv['category'] != '餐饮']
    dining_count = len([inv for inv in matched if inv['category'] == '餐饮'])  # 始终为0，保留变量名兼容

    # 按子目录分组
    by_subdir = defaultdict(list)
    total_reimburse = 0
    total_all = 0
    count_reimburse = 0
    count_all = len(matched)
    for inv in matched:
        by_subdir[inv['subdir']].append(inv)
        amt = float(inv['amount'])
        total_all += amt
        if inv['is_reimburse']:
            total_reimburse += amt
            count_reimburse += 1

    md = f"# 发票文件清单 — {folder_name.split('_', 1)[1] if '_' in folder_name else folder_name}\n\n"

    # 概览
    md += f"## 概览\n\n"
    md += f"| 项目 | 数量 | 金额 |\n|------|------|------|\n"
    md += f"| 发票总数 | {count_all} | ¥{total_all:,.2f} |\n"
    md += f"| 正式发票(可报销) | {count_reimburse} | ¥{total_reimburse:,.2f} |\n"
    md += f"| 辅助文件(行程单/结账单) | {count_all - count_reimburse} | ¥{total_all - total_reimburse:,.2f} |\n\n"

    # 各子目录明细
    for subdir in SUBDIRS:
        items = by_subdir.get(subdir, [])
        if not items:
            continue
        subdir_total = sum(float(i['amount']) for i in items)
        subdir_reimburse = sum(float(i['amount']) for i in items if i['is_reimburse'])
        md += f"## {subdir}（{len(items)}张，¥{subdir_total:,.2f}）\n\n"
        md += f"| 日期 | 类别 | 金额 | 发票号/备注 | 文件名 |\n|------|------|------|------|------|\n"
        for i in sorted(items, key=lambda x: x['date']):
            remark = i['route'] if i['route'] else i['suffix']
            md += f"| {i['date']} | {i['category']} | ¥{float(i['amount']):,.2f} | {remark} | {i['filename']} |\n"
        md += "\n"

    md += f"\n> 📁 附件目录: [[个人行程与报销/02 行程/2026 年/{month_str}/{folder_name}/02-发票文件|02-发票文件]]\n"
    md += f"> 📝 行程详情: [[个人行程与报销/02 行程/2026 年/{month_str}/{folder_name}/01-行程详情|01-行程详情]]\n"
    md += f"> 🍽️ 餐饮发票不放入行程，按月归档至 [[个人行程与报销/02 行程/2026 年/{month_str}/餐饮|{month_str}/餐饮]]\n"

    md_path = os.path.join(invoice_dir, "发票文件清单.md")
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f"✅ 生成发票文件清单: 发票文件清单.md")
    return md_path, count_reimburse, total_reimburse


def update_trip_overview(trip_id, start_date, end_date, route_list, folder_name, month_str, count_reimburse, total_reimburse):
    """更新行程总览.md"""
    year_dir = os.path.join(TRIP_ROOT, f"2026 年")
    overview_path = os.path.join(year_dir, "行程总览.md")

    # 如果总览不存在，创建
    if not os.path.exists(overview_path):
        md = "# 2026年行程总览\n\n## 出差一览\n\n"
        md += "| 出差编号 | 日期 | 路线 | 发票数 | 报销金额 | 状态 | 链接 |\n"
        md += "|----------|------|------|--------|----------|------|------|\n"
    else:
        with open(overview_path, 'r', encoding='utf-8') as f:
            md = f.read()

    route_str = '-'.join(route_list)
    # 添加新行
    new_row = f"| 出差{trip_id} | {start_date}～{end_date} | {route_str} | {count_reimburse}张 | ¥{total_reimburse:,.2f} | 文件整理中 | [[{month_str}/{folder_name}/01-行程详情|出差{trip_id}]] | [[个人行程与报销/02 行程/2026 年/{month_str}/{folder_name}/02-发票文件/发票文件清单|发票文件清单]] |\n"

    # 查找表格并插入
    lines = md.split('\n')
    table_start = -1
    table_end = -1
    for i, line in enumerate(lines):
        if '| 出差编号 |' in line:
            table_start = i
        if table_start >= 0 and table_end < 0 and line.strip() == '' and i > table_start + 2:
            table_end = i
            break

    if table_start >= 0:
        # 插入到表格最后（在空行前）
        if table_end < 0:
            table_end = len(lines)
        lines.insert(table_end, new_row)
    else:
        # 没找到表格，追加
        if not md.strip().endswith('|----------|'):
            md += "\n## 出差一览\n\n"
            md += "| 出差编号 | 日期 | 路线 | 发票数 | 报销金额 | 状态 | 链接 |\n"
            md += "|----------|------|------|--------|----------|------|------|\n"
            md += new_row
        else:
            md += new_row

        with open(overview_path, 'w', encoding='utf-8') as f:
            f.write(md)
        print(f"✅ 更新行程总览: 行程总览.md")
        return

    md = '\n'.join(lines)
    with open(overview_path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f"✅ 更新行程总览: 行程总览.md")


def check_invoice_completeness(matched, route_list, start_date, end_date):
    """检查发票完整性"""
    issues = []

    # 检查交通发票
    transport = [i for i in matched if i['subdir'] == '机票高铁']
    if len(route_list) > 2 and len(transport) == 0:
        issues.append("⚠️ 无机票/高铁发票")

    # 检查住宿发票
    accommodation = [i for i in matched if i['subdir'] == '住宿']
    days = (datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days
    if days > 1 and len(accommodation) == 0:
        issues.append(f"⚠️ 无住宿发票（{days}天出差应有住宿）")

    # 检查城际交通数量
    # 简单判断：N个城市至少需要N-1段交通
    city_count = len(set(route_list))
    if city_count > 2 and len(transport) < city_count - 1:
        issues.append(f"⚠️ 交通发票偏少（{city_count}个城市，仅{len(transport)}张交通发票）")

    return issues


def main():
    # 版本检查（自动更新）
    try:
        import importlib.util
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, "config.py")
        vm_path = os.path.join(script_dir, "version_manager.py")
        if os.path.exists(config_path) and os.path.exists(vm_path):
            vm_spec = importlib.util.spec_from_file_location("version_manager", vm_path)
            if vm_spec:
                vm = importlib.util.module_from_spec(vm_spec)
                vm_spec.loader.exec_module(vm)
                vm.check_and_update(config_path, auto=True, silent=True)
    except Exception:
        pass

    if not ensure_configured():
        return

    args = parse_args()
    start_date = args.start_date
    end_date = args.end_date
    route_list = args.route.split(',')
    year = args.year
    month = args.month or start_date[5:7]
    month = int(month)  # 统一转为整数，避免 "06" vs "6" 不一致
    month_str = f"{month} 月"

    year_dir = os.path.join(TRIP_ROOT, f"{year} 年")

    # 去重检查：同日期范围已存在则复用
    existing = find_existing_trip(start_date, end_date)
    if existing:
        trip_dir, folder_name, trip_id = existing
        print(f"📌 行程自动整理 - 出差{trip_id}（复用已有目录）")
        print(f"   日期: {start_date}～{end_date}")
        print(f"   路线: {'-'.join(route_list)}")
        print(f"   ⏭️  已存在: {folder_name}")
    else:
        # 确定出差编号
        if args.trip_id:
            trip_id = args.trip_id
        else:
            trip_id = get_next_trip_id(year_dir)

        print(f"🧳 行程自动整理 - 出差{trip_id}")
        print(f"   日期: {start_date}～{end_date}")
        print(f"   路线: {'-'.join(route_list)}")

        # 1. 创建行程文件夹
        trip_dir, folder_name = create_trip_folder(trip_id, start_date, end_date, route_list, year, month)

        # 2. 生成行程详情MD
        gen_trip_detail_md(trip_id, start_date, end_date, route_list, trip_dir, folder_name)

    # 3. 扫描03已完成中的匹配发票
    print(f"\n🔍 扫描03已完成中 {start_date}～{end_date} 的发票...")
    matched = scan_done_invoices(start_date, end_date)

    # 4. 复制发票到行程附件目录（复用时清空旧文件重新复制）
    if matched:
        copy_invoices_to_trip(matched, trip_dir, clear_existing=existing is not None)

    # 4a. 餐饮类发票复制到月度餐饮目录（扫描整个月份，不依赖行程匹配）
    dining_count = 0
    if matched:
        dining_count += copy_dining_to_monthly(year, month)
        # V1.0.61: 跨月行程也复制结束月的餐饮发票
        end_month = int(end_date[5:7])
        if end_month != month:
            dining_count += copy_dining_to_monthly(year, end_month)

    # 5. 生成发票文件清单MD
    md_path, count_reimburse, total_reimburse = gen_invoice_list_md(
        matched, trip_dir, folder_name, month_str
    )

    # 6. 更新行程总览
    update_trip_overview(
        trip_id, start_date, end_date, route_list, folder_name, month_str,
        count_reimburse, total_reimburse
    )

    # 7. 检查发票完整性
    issues = check_invoice_completeness(matched, route_list, start_date, end_date)
    if issues:
        print(f"\n⚠️ 发票完整性检查:")
        for issue in issues:
            print(f"   {issue}")
        print(f"   💡 发票未齐全，报销单暂不生成")
    else:
        print(f"\n✅ 发票完整性检查通过")
        # 复制报销单模板到 03 报销单 目录
        if os.path.exists(TEMPLATE_XLSX):
            reimb_year_dir = os.path.join(REIMBURSEMENT_ROOT, f"{year} 年", month_str)
            os.makedirs(reimb_year_dir, exist_ok=True)
            dest = os.path.join(reimb_year_dir, f"出差{trip_id}-报销单.xlsx")
            shutil.copy2(TEMPLATE_XLSX, dest)
            print(f"✅ 复制报销单模板到: 03 报销单/{year} 年/{month_str}/出差{trip_id}-报销单.xlsx")
        else:
            print(f"   💡 未配置报销单模板 (REIMBURSEMENT_TEMPLATE)，跳过报销单生成")

    # 汇总
    print(f"\n{'='*60}")
    print(f"📊 行程整理汇总")
    print(f"{'='*60}")
    print(f"   出差编号: 出差{trip_id}")
    print(f"   行程日期: {start_date}～{end_date}")
    print(f"   途经城市: {'-'.join(route_list)}")
    print(f"   匹配发票: {len(matched)}张（正式发票{count_reimburse}张）")
    if dining_count:
        print(f"   其中餐饮: {dining_count}张（已归档至 {month_str}/餐饮/）")
    print(f"   报销金额: ¥{total_reimburse:,.2f}")
    if issues:
        print(f"   发票状态: ⚠️ 未齐全")
    else:
        print(f"   发票状态: ✅ 齐全")
    print(f"\n✅ 行程整理完成。")


if __name__ == "__main__":
    main()
