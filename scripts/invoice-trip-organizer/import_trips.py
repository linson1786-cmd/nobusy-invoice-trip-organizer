#!/usr/bin/env python3
"""
导入行程 - 批量导入行程数据
弹出文本输入窗口，粘贴行程数据（Tab分隔），自动创建行程文件夹

数据格式（支持多种日期格式）：
  开始日期	结束日期	行程
  2026-01-04	2026-01-09	广州-上海-南通-杭州-成都-重庆-广州
  2026/3/11	2026/3/14	广州-中山-深圳-上海-苏州-上海-广州

去重规则：以开始日期+结束日期为准，已存在则跳过
"""
import os
import sys
import re
import platform
import importlib.util
from datetime import datetime

# ===== 加载配置 =====
_script_dir = os.path.dirname(os.path.abspath(__file__))
_config_path = os.path.join(_script_dir, "config.py")


def load_config():
    """加载 config.py"""
    if os.path.exists(_config_path):
        spec = importlib.util.spec_from_file_location("config", _config_path)
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        return config
    return None


# ============================================================
# 文本输入窗口
# ============================================================

def show_input_dialog():
    """弹出多行文本输入窗口，返回用户输入的文本"""
    system = platform.system()
    if system == 'Darwin':
        return show_input_dialog_macos()
    else:
        return show_input_dialog_tkinter()


def show_input_dialog_macos():
    """macOS: 优先用 tkinter（支持多行粘贴），回退到 osascript"""
    try:
        return show_input_dialog_tkinter()
    except Exception:
        return None


def show_input_dialog_tkinter():
    """tkinter 多行文本输入窗口"""
    try:
        import tkinter as tk
        from tkinter import scrolledtext
    except ImportError:
        print('错误: 无法加载 tkinter', flush=True)
        print('  macOS: brew install python-tk', flush=True)
        print('  Ubuntu: sudo apt install python3-tk', flush=True)
        return None

    result = {"text": None, "submitted": False}

    root = tk.Tk()
    root.title("导入行程数据")
    root.geometry("680x420")
    root.attributes('-topmost', True)

    # 说明标签
    label_text = (
        "粘贴行程数据（Tab 分隔：开始日期  结束日期  行程路线）\n"
        "支持格式：2026-01-04 或 2026/3/11    可包含表头行"
    )
    label = tk.Label(root, text=label_text, font=("Arial", 11), justify=tk.LEFT)
    label.pack(anchor='w', padx=10, pady=(8, 4))

    # 多行文本输入区
    text_area = scrolledtext.ScrolledText(
        root, wrap=tk.WORD, font=("Menlo", 12), width=80, height=15
    )
    text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

    # 焦点放到文本区
    text_area.focus_set()

    # 按钮区
    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=(4, 8))

    def on_submit():
        content = text_area.get("1.0", tk.END).strip()
        if not content:
            return
        result["text"] = content
        result["submitted"] = True
        root.destroy()

    def on_cancel():
        root.destroy()

    # Enter 提交（Ctrl+Return）
    root.bind('<Control-Return>', lambda e: on_submit())
    root.bind('<Escape>', lambda e: on_cancel())

    submit_btn = tk.Button(
        btn_frame, text="提 交", command=on_submit,
        width=12, font=("Arial", 11)
    )
    submit_btn.pack(side=tk.LEFT, padx=8)

    cancel_btn = tk.Button(
        btn_frame, text="取 消", command=on_cancel,
        width=12, font=("Arial", 11)
    )
    cancel_btn.pack(side=tk.LEFT, padx=8)

    root.mainloop()

    if not result["submitted"]:
        return None
    return result["text"]


# ============================================================
# 行程数据解析
# ============================================================

def normalize_date(date_str):
    """将各种日期格式统一为 YYYY-MM-DD"""
    date_str = date_str.strip()
    # YYYY-MM-DD
    m = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})', date_str)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    # YYYY/M/D
    m = re.match(r'(\d{4})/(\d{1,2})/(\d{1,2})', date_str)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    # YYYY.M.D
    m = re.match(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', date_str)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


def parse_trips(text):
    """
    解析粘贴的行程数据，返回 [(start_date, end_date, route_list), ...]
    支持格式：
      - Tab 分隔
      - 多个空格分隔
      - 包含表头行（自动跳过）
      - 包含空行（自动跳过）
    """
    trips = []
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue

        # 跳过表头行
        if '开始日期' in line and '结束日期' in line:
            continue

        # 尝试 Tab 分隔
        parts = line.split('\t')
        if len(parts) < 3:
            # 回退：2个以上连续空格分隔
            parts = re.split(r'\s{2,}', line)
        if len(parts) < 3:
            continue

        start_raw = parts[0].strip()
        end_raw = parts[1].strip()
        route_raw = parts[2].strip()

        if not route_raw:
            continue

        # 解析日期
        start_date = normalize_date(start_raw)
        end_date = normalize_date(end_raw)

        if not start_date or not end_date:
            continue

        # 解析路线（按 - 分隔城市）
        route_list = [c.strip() for c in route_raw.split('-') if c.strip()]
        if len(route_list) < 2:
            continue

        trips.append((start_date, end_date, route_list))

    return trips


# ============================================================
# 去重：扫描已有行程
# ============================================================

def get_existing_trips(trip_root):
    """
    扫描已有行程文件夹，返回 {(start_date, end_date), ...}
    文件夹格式：出差N-YYYY-MM-DD～YYYY-MM-DD_城市-城市
    """
    existing = set()
    if not os.path.isdir(trip_root):
        return existing

    # 匹配两种分隔符：～ (全角波浪线) 和 ~ (半角)
    folder_re = re.compile(
        r'出差\d+-(\d{4}-\d{2}-\d{2})[～~](\d{4}-\d{2}-\d{2})'
    )

    for year_name in os.listdir(trip_root):
        year_dir = os.path.join(trip_root, year_name)
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
                if m:
                    existing.add((m.group(1), m.group(2)))

    return existing


# ============================================================
# 主流程
# ============================================================

def main():
    # 版本检查（自动更新）
    try:
        config_path = os.path.join(_script_dir, "config.py")
        vm_path = os.path.join(_script_dir, "version_manager.py")
        if os.path.exists(config_path) and os.path.exists(vm_path):
            vm_spec = importlib.util.spec_from_file_location("version_manager", vm_path)
            if vm_spec:
                vm = importlib.util.module_from_spec(vm_spec)
                vm_spec.loader.exec_module(vm)
                vm.check_and_update(config_path, auto=True, silent=True)
    except Exception:
        pass

    config = load_config()
    if not config:
        print('错误: 未找到 config.py，请先运行「初始化设置」', flush=True)
        sys.exit(1)

    trip_root = os.path.expanduser(getattr(config, 'TRIP_ROOT', ''))
    if not trip_root:
        print('错误: config.py 中未配置 TRIP_ROOT', flush=True)
        sys.exit(1)

    print('=' * 50, flush=True)
    print('导入行程数据', flush=True)
    print(f'行程根目录: {trip_root}', flush=True)
    print('=' * 50, flush=True)
    print()
    print('正在打开输入窗口...', flush=True)

    # 1. 弹出输入窗口
    text = show_input_dialog()
    if not text:
        print('用户取消了输入，停止执行', flush=True)
        sys.exit(0)

    # 2. 解析行程数据
    trips = parse_trips(text)
    if not trips:
        print('未解析到有效行程数据，请检查格式', flush=True)
        sys.exit(0)

    print(f'解析到 {len(trips)} 条行程:', flush=True)
    for start, end, route in trips:
        print(f'  {start} ~ {end}  {"-".join(route)}', flush=True)
    print()

    # 3. 获取已有行程，去重
    existing = get_existing_trips(trip_root)

    new_trips = []
    skipped = []
    for start, end, route in trips:
        if (start, end) in existing:
            skipped.append((start, end, route))
        else:
            new_trips.append((start, end, route))

    if skipped:
        print(f'⏭️  跳过 {len(skipped)} 条已存在行程:', flush=True)
        for start, end, route in skipped:
            print(f'  {start} ~ {end}  {"-".join(route)}', flush=True)
        print()

    if not new_trips:
        print('所有行程已存在，无需新增', flush=True)
        sys.exit(0)

    print(f'📌 将新增 {len(new_trips)} 条行程', flush=True)
    print()

    # 4. 导入 trip_auto_organizer 模块
    trip_ao_path = os.path.join(_script_dir, "trip_auto_organizer.py")
    if not os.path.exists(trip_ao_path):
        print('错误: 未找到 trip_auto_organizer.py', flush=True)
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("trip_auto_organizer", trip_ao_path)
    trip_ao = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trip_ao)

    # 5. 逐条创建行程
    success_count = 0
    failed_count = 0

    for start_date, end_date, route_list in new_trips:
        year = start_date[:4]
        month = int(start_date[5:7])
        year_dir = os.path.join(trip_root, f"{year} 年")

        # 每次重新获取下一个出差编号（前面创建的会影响编号）
        trip_id = trip_ao.get_next_trip_id(year_dir)

        print(f'🧳 创建出差{trip_id}: {start_date}～{end_date} {"-".join(route_list)}', flush=True)

        try:
            # 创建行程文件夹
            trip_dir, folder_name = trip_ao.create_trip_folder(
                trip_id, start_date, end_date, route_list, year, month
            )

            # 生成行程详情 MD
            trip_ao.gen_trip_detail_md(
                trip_id, start_date, end_date, route_list, trip_dir, folder_name
            )

            # 扫描匹配发票
            matched = trip_ao.scan_done_invoices(start_date, end_date)
            if matched:
                trip_ao.copy_invoices_to_trip(matched, trip_dir)

            # 生成发票文件清单
            month_str = f"{month} 月"
            _, count_reimburse, total_reimburse = trip_ao.gen_invoice_list_md(
                matched, trip_dir, folder_name, month_str
            )

            # 更新行程总览
            trip_ao.update_trip_overview(
                trip_id, start_date, end_date, route_list, folder_name, month_str,
                count_reimburse, total_reimburse
            )

            success_count += 1
            print(f'  ✅ 完成', flush=True)
        except Exception as e:
            failed_count += 1
            print(f'  ❌ 失败: {e}', flush=True)
        print()

    # 6. 汇总
    print('=' * 50, flush=True)
    print(f'导入完成: 新增 {success_count} 条, 跳过 {len(skipped)} 条已存在'
          + (f', 失败 {failed_count} 条' if failed_count else ''), flush=True)
    print('=' * 50, flush=True)


if __name__ == "__main__":
    main()
