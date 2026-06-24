#!/usr/bin/env python3
"""
邮箱账户管理器
- 多邮箱账户存储（JSON）
- macOS osascript 原生选择/注册界面
- 记录上次使用的邮箱
- 支持 163/QQ/126/自定义 邮箱服务商
"""

import json
import os
import uuid
import platform
import subprocess
import sys
from datetime import datetime, timedelta

# ===== 常量 =====
DATA_DIR = os.path.expanduser("~/.invoice-trip")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "email_accounts.json")

PROVIDERS = {
    "163": {
        "name": "网易163邮箱",
        "imap_server": "imap.163.com",
        "imap_port": 993,
        "guide": (
            "获取163邮箱授权码：\n"
            "1. 登录 mail.163.com\n"
            "2. 设置 → POP3/SMTP/IMAP\n"
            "3. 开启「IMAP/SMTP服务」\n"
            "4. 点击「新增授权码」→ 按提示发送短信\n"
            "5. 复制生成的授权码（非登录密码！）"
        ),
    },
    "qq": {
        "name": "QQ邮箱",
        "imap_server": "imap.qq.com",
        "imap_port": 993,
        "guide": (
            "获取QQ邮箱授权码：\n"
            "1. 登录 mail.qq.com\n"
            "2. 设置 → 账户 → POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务\n"
            "3. 开启「IMAP/SMTP服务」\n"
            "4. 按提示发送短信 → 生成授权码\n"
            "5. 复制生成的授权码（非QQ密码！）"
        ),
    },
    "126": {
        "name": "网易126邮箱",
        "imap_server": "imap.126.com",
        "imap_port": 993,
        "guide": (
            "获取126邮箱授权码：\n"
            "1. 登录 mail.126.com\n"
            "2. 设置 → POP3/SMTP/IMAP\n"
            "3. 开启「IMAP/SMTP服务」\n"
            "4. 点击「新增授权码」→ 按提示发送短信\n"
            "5. 复制生成的授权码（非登录密码！）"
        ),
    },
    "custom": {
        "name": "自定义邮箱",
        "imap_server": "",
        "imap_port": 993,
        "guide": "请手动填写 IMAP 服务器地址和端口",
    },
}


# ============================================================
# JSON 存储
# ============================================================

def load_accounts():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(ACCOUNTS_FILE):
        return {"accounts": [], "last_used_id": None}
    try:
        # 兼容旧文件：修正权限为仅所有者可读写
        os.chmod(ACCOUNTS_FILE, 0o600)
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("accounts", [])
            data.setdefault("last_used_id", None)
            return data
    except (json.JSONDecodeError, Exception):
        return {"accounts": [], "last_used_id": None}


def save_accounts(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # 凭据文件权限保护：仅所有者可读写
    os.chmod(ACCOUNTS_FILE, 0o600)


def add_account(acc):
    data = load_accounts()
    acc["id"] = str(uuid.uuid4())[:8]
    acc["created_at"] = datetime.now().isoformat()
    data["accounts"].append(acc)
    save_accounts(data)
    return acc["id"]


def delete_account(acc_id):
    data = load_accounts()
    data["accounts"] = [a for a in data["accounts"] if a.get("id") != acc_id]
    if data["last_used_id"] == acc_id:
        data["last_used_id"] = None
    save_accounts(data)


def set_last_used(acc_id):
    data = load_accounts()
    data["last_used_id"] = acc_id
    save_accounts(data)


def get_account(acc_id):
    data = load_accounts()
    for a in data["accounts"]:
        if a.get("id") == acc_id:
            return a
    return None


def get_last_used():
    data = load_accounts()
    lid = data.get("last_used_id")
    if lid:
        return get_account(lid)
    return None


# ============================================================
# macOS osascript UI
# ============================================================

def run_osascript(script, timeout=120):
    """运行 AppleScript，返回 (stdout, success)"""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip(), result.returncode == 0
    except subprocess.TimeoutExpired:
        return "", False
    except FileNotFoundError:
        return "", False


def escape_applescript(s):
    """转义字符串用于 AppleScript"""
    return s.replace("\\", "\\\\").replace('"', '\\"')


# ---- 选择邮箱（macOS 用 tkinter，终端用交互输入） ----
def pick_account_tkinter(accounts, last_used_id):
    """tkinter 回退：终端选择"""
    print("\n=== 已登记的邮箱账户 ===")
    for i, a in enumerate(accounts, 1):
        marker = "⭐ (上次使用)" if a.get("id") == last_used_id else ""
        print(f"  [{i}] {a['name']} ({a['email']}) {marker}")
    print(f"  [0] 新增邮箱账户")
    print(f"  [Q] 退出")

    default_idx = 1
    if last_used_id:
        for i, a in enumerate(accounts, 1):
            if a.get("id") == last_used_id:
                default_idx = i
                break

    choice = input(f"\n请选择 [默认={default_idx}]: ").strip()
    if choice.lower() == "q":
        return None
    if choice == "0":
        return "ADD_NEW"
    try:
        idx = int(choice) - 1
    except ValueError:
        idx = default_idx - 1

    if 0 <= idx < len(accounts):
        return accounts[idx]
    return accounts[default_idx - 1]


# ---- 注册邮箱 ----

def register_account_macos():
    """弹出表单让用户填写邮箱信息"""
    # Step 1: 选择服务商
    provider_labels = [f"{k} - {v['name']}" for k, v in PROVIDERS.items()]
    label_str = ", ".join(f'"{escape_applescript(l)}"' for l in provider_labels)

    script = f'''
    set theList to {{{label_str}}}
    set theChoice to choose from list theList with title "新增邮箱" with prompt "请选择邮箱服务商：" default items {{item 1 of theList}}
    if theChoice is false then return "CANCELLED"
    return item 1 of theChoice
    '''
    result, success = run_osascript(script)
    if not success or result == "CANCELLED":
        return None

    # 解析 provider key
    provider_key = None
    for k, v in PROVIDERS.items():
        if result.startswith(k):
            provider_key = k
            break
    if not provider_key:
        return None

    provider = PROVIDERS[provider_key]
    imap_server = provider.get("imap_server", "imap.example.com")
    imap_port = provider.get("imap_port", 993)
    default_name = provider["name"]

    # Step 2: tkinter 单窗口三字段表单
    import tkinter as tk
    from tkinter import ttk
    import tkinter.font as tkf

    result = {"cancelled": True}

    def on_save():
        result["email"] = entry_email.get().strip()
        result["auth"] = entry_auth.get().strip()
        result["name"] = entry_name.get().strip()
        result["cancelled"] = False
        root.destroy()

    def on_cancel():
        result["cancelled"] = True
        root.destroy()

    root = tk.Tk()
    root.title(f"新增邮箱 - {default_name}")
    root.resizable(False, False)

    # 居中显示
    root.update_idletasks()
    w, h = 480, 360
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    frm = ttk.Frame(root, padding=16)
    frm.pack(fill="both", expand=True)

    # 标题
    ttk.Label(frm, text=f"新增邮箱 — {default_name}", font=("", 14, "bold")).pack(anchor="w", pady=(0, 8))

    # 指引文字
    guide_text = (
        f"获取授权码指引：\n"
        f"{provider['guide']}"
    )
    ttk.Label(frm, text=guide_text, wraplength=440, justify="left",
              foreground="#555555").pack(anchor="w", pady=(0, 12))

    # 统一输入框字体，避免 macOS ttk.Entry 高度不一致
    entry_font = tkf.Font(family=".AppleSystemUIFont", size=13)
    entry_opts = {"font": entry_font, "relief": "solid", "borderwidth": 1,
                  "highlightthickness": 0}

    # 邮箱地址
    ttk.Label(frm, text="邮箱地址：").pack(anchor="w")
    entry_email = tk.Entry(frm, width=44, **entry_opts)
    entry_email.pack(fill="x", ipady=4, pady=(0, 8))
    entry_email.focus_set()

    # 授权码（隐藏输入）
    ttk.Label(frm, text="授权码（非登录密码）：").pack(anchor="w")
    entry_auth = tk.Entry(frm, width=44, show="•", **entry_opts)
    entry_auth.pack(fill="x", ipady=4, pady=(0, 8))

    # 显示名称
    ttk.Label(frm, text="显示名称：").pack(anchor="w")
    entry_name = tk.Entry(frm, width=44, **entry_opts)
    entry_name.pack(fill="x", ipady=4, pady=(0, 12))
    entry_name.insert(0, default_name)

    # 按钮
    btn_frame = ttk.Frame(frm)
    btn_frame.pack(fill="x")
    ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side="right", padx=(8, 0))
    ttk.Button(btn_frame, text="保存", command=on_save).pack(side="right")

    # 绑定回车和 ESC
    root.bind("<Return>", lambda e: on_save())
    root.bind("<Escape>", lambda e: on_cancel())

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()

    if result["cancelled"]:
        return None

    email_addr = result["email"]
    auth_code = result["auth"]
    display_name = result["name"]

    if not email_addr:
        # 回退到 osascript 弹警告太复杂，直接返回 None
        return None
    if not auth_code:
        return None
    if not display_name:
        display_name = default_name

    # Step 3: 如果是自定义，填写 IMAP 服务器（仍用 AppleScript，仅自定义触发）
    if provider_key == "custom":
        script_imap = f'''
        set dialogResult to display dialog "IMAP 服务器地址：" default answer "" with title "自定义邮箱 - IMAP 配置" buttons {{"取消", "下一步"}} default button "下一步"
        if button returned of dialogResult is "取消" then return "CANCELLED"
        return text returned of dialogResult
        '''
        imap_server, success = run_osascript(script_imap)
        if not success or imap_server == "CANCELLED":
            return None

        script_port = '''
        set dialogResult to display dialog "IMAP 端口：" default answer "993" with title "自定义邮箱 - IMAP 配置" buttons {"取消", "完成"} default button "完成"
        if button returned of dialogResult is "取消" then return "CANCELLED"
        return text returned of dialogResult
        '''
        port_str, success = run_osascript(script_port)
        if not success or port_str == "CANCELLED":
            return None
        try:
            imap_port = int(port_str)
        except ValueError:
            imap_port = 993

    return {
        "name": display_name,
        "email": email_addr,
        "auth_code": auth_code,
        "imap_server": imap_server,
        "imap_port": imap_port,
        "provider": provider_key,
    }


def register_account_tkinter():
    """终端交互注册"""
    print("\n=== 新增邮箱账户 ===\n")

    print("支持的服务商：")
    keys = list(PROVIDERS.keys())
    for i, k in enumerate(keys, 1):
        print(f"  [{i}] {PROVIDERS[k]['name']}")
    print()

    choice = input(f"请选择 [1-{len(keys)}]: ").strip()
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(keys):
            print("选择无效，已取消")
            return None
    except ValueError:
        print("选择无效，已取消")
        return None

    provider_key = keys[idx]
    provider = PROVIDERS[provider_key]

    print(f"\n{provider['guide']}\n")

    email_addr = input("邮箱地址: ").strip()
    if not email_addr:
        print("邮箱地址不能为空，已取消")
        return None

    auth_code = input("授权码（非登录密码）: ").strip()
    if not auth_code:
        print("授权码不能为空，已取消")
        return None

    imap_server = provider.get("imap_server", "")
    imap_port = provider.get("imap_port", 993)

    if provider_key == "custom":
        imap_server = input("IMAP 服务器地址: ").strip()
        port_str = input("IMAP 端口 [993]: ").strip()
        imap_port = int(port_str) if port_str else 993

    display_name = input(f"显示名称 [{provider['name']}]: ").strip()
    if not display_name:
        display_name = provider["name"]

    return {
        "name": display_name,
        "email": email_addr,
        "auth_code": auth_code,
        "imap_server": imap_server,
        "imap_port": imap_port,
        "provider": provider_key,
    }


# ---- 删除确认 ----

def delete_account_macos(acc):
    name = escape_applescript(acc["name"])
    email_addr = escape_applescript(acc["email"])
    script = f'''
    set dialogResult to display dialog "确定删除邮箱账户？\\n\\n{name} ({email_addr})\\n\\n此操作不可撤销。" with title "删除邮箱" buttons {{"取消", "删除"}} default button "取消" with icon caution
    if button returned of dialogResult is "删除" then return "YES"
    return "NO"
    '''
    result, _ = run_osascript(script)
    return result == "YES"


def delete_account_tkinter(acc):
    ans = input(f"\n确定删除 {acc['name']} ({acc['email']})? [y/N]: ").strip().lower()
    return ans == "y"


def delete_account_ui(acc):
    system = platform.system()
    if system == "Darwin":
        return delete_account_macos(acc)
    else:
        return delete_account_tkinter(acc)


# ---- 管理界面（选择/新增/删除） ----

def manage_accounts_macos(accounts, last_used_id):
    """tkinter 管理界面：单窗口显示所有账户 + 新增按钮"""
    import tkinter as tk
    from tkinter import ttk

    result = {"cancelled": True, "action": None, "account": None}

    def on_select():
        sel = radio_var.get()
        if sel == "add":
            result["action"] = "ADD_NEW"
            result["cancelled"] = False
        elif sel.startswith("acc:"):
            acc_id = sel[4:]
            for a in accounts:
                if a.get("id") == acc_id:
                    result["account"] = a
                    result["cancelled"] = False
                    break
        root.destroy()

    def on_cancel():
        result["cancelled"] = True
        root.destroy()

    root = tk.Tk()
    root.title("选择邮箱")
    root.resizable(False, False)

    # 动态计算高度：标题 + 指引 + 每个账户40px + 新增行 + 按钮
    h = 120 + len(accounts) * 36 + 60
    w = 500

    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    frm = ttk.Frame(root, padding=16)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text="请选择下载发票的邮箱", font=("", 13, "bold")).pack(anchor="w", pady=(0, 12))

    radio_var = tk.StringVar()
    default_val = None

    # 已有账户列表
    for a in accounts:
        val = f"acc:{a['id']}"
        label = f"{a['name']} ({a['email']})"
        if a.get("id") == last_used_id:
            label = f"⭐ {label}（上次使用）"
            default_val = val
        ttk.Radiobutton(frm, text=label, variable=radio_var, value=val).pack(anchor="w", pady=2)

    # 分隔线
    ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=8)

    # 新增选项
    ttk.Radiobutton(frm, text="➕ 新增邮箱账户", variable=radio_var, value="add").pack(anchor="w", pady=2)

    # 设置默认选中上次使用的
    if default_val:
        radio_var.set(default_val)

    # 按钮
    btn_frame = ttk.Frame(frm)
    btn_frame.pack(fill="x", pady=(12, 0))
    ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side="right", padx=(8, 0))
    ttk.Button(btn_frame, text="选择", command=on_select).pack(side="right")

    root.bind("<Return>", lambda e: on_select())
    root.bind("<Escape>", lambda e: on_cancel())
    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()

    if result["cancelled"]:
        return None

    if result["action"] == "ADD_NEW":
        return "ADD_NEW"

    return result["account"]


# ---- 获取授权码指引窗口 ----

def show_auth_guide_macos(provider_key):
    """显示获取授权码的指引"""
    provider = PROVIDERS.get(provider_key)
    if not provider:
        return
    guide = escape_applescript(provider["guide"])
    script = f'''
    display dialog "{guide}" with title "获取授权码指引 - {provider['name']}" buttons {{"知道了"}} default button "知道了"
    '''
    run_osascript(script)


# ---- 时间范围选择 ----

# 预设选项，默认选中"近90天"
DATE_PRESETS = [
    ("近7天", 7),
    ("近30天", 30),
    ("近90天（默认）", 90),
    ("今年以来", None),   # None 表示用今年 1-1
    ("自定义时间段", -1),
]


def calc_preset_date(preset_days):
    """根据预设天数计算起始日期"""
    if preset_days is None:
        # 今年以来
        today = datetime.now()
        return datetime(today.year, 1, 1)
    end = datetime.now()
    start = end - timedelta(days=preset_days)
    return start


def pick_date_range_macos():
    """macOS 原生弹窗选择时间范围"""
    labels = []
    for label, _ in DATE_PRESETS:
        labels.append(label)

    label_str = ", ".join(f'"{escape_applescript(l)}"' for l in labels)
    script = f'''
    set theList to {{{label_str}}}
    set theChoice to choose from list theList with title "选择时间范围" with prompt "下载哪个时间段的邮件发票？" default items {{item 3 of theList}}
    if theChoice is false then return "CANCELLED"
    return item 1 of theChoice
    '''
    result, success = run_osascript(script)
    if not success or result == "CANCELLED":
        return None, None

    # 找到选中的 preset
    chosen_preset = None
    for label, days in DATE_PRESETS:
        if label == result:
            chosen_preset = (label, days)
            break

    if not chosen_preset:
        return None, None

    if chosen_preset[1] == -1:
        # 自定义时间段 → 让用户输入起止日期
        return pick_custom_range_macos()
    else:
        start = calc_preset_date(chosen_preset[1])
        return start, datetime.now()


def pick_custom_range_macos():
    """自定义日期范围输入"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    three_months_ago = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

    # 输入开始日期
    script_start = f'''
    set dialogResult to display dialog "开始日期（含）：" & return & return & "格式：YYYY-MM-DD" default answer "{three_months_ago}" with title "自定义时间范围" buttons {{"取消", "下一步"}} default button "下一步"
    if button returned of dialogResult is "取消" then return "CANCELLED"
    return text returned of dialogResult
    '''
    start_str, success = run_osascript(script_start)
    if not success or start_str == "CANCELLED":
        return None, None

    try:
        start_date = datetime.strptime(start_str.strip(), "%Y-%m-%d")
    except ValueError:
        # 弹窗提示格式错误，使用默认90天
        script_err = '''
        display alert "日期格式错误" message "请使用 YYYY-MM-DD 格式，例如 2026-01-01" as warning
        '''
        run_osascript(script_err)
        return None, None

    # 输入结束日期
    script_end = f'''
    set dialogResult to display dialog "结束日期（含）：" & return & return & "格式：YYYY-MM-DD" default answer "{today_str}" with title "自定义时间范围" buttons {{"取消", "确认"}} default button "确认"
    if button returned of dialogResult is "取消" then return "CANCELLED"
    return text returned of dialogResult
    '''
    end_str, success = run_osascript(script_end)
    if not success or end_str == "CANCELLED":
        return None, None

    try:
        end_date = datetime.strptime(end_str.strip(), "%Y-%m-%d")
    except ValueError:
        script_err = '''
        display alert "日期格式错误" message "请使用 YYYY-MM-DD 格式，例如 2026-06-23" as warning
        '''
        run_osascript(script_err)
        return None, None

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    return start_date, end_date


def pick_date_range_tkinter():
    """终端选择时间范围"""
    print("\n=== 选择邮件时间范围 ===\n")
    for i, (label, _) in enumerate(DATE_PRESETS, 1):
        print(f"  [{i}] {label}")
    print(f"  [Q] 退出")

    choice = input(f"\n请选择 [默认=3]: ").strip()
    if choice.lower() == "q":
        return None, None

    try:
        idx = int(choice) - 1 if choice else 2  # 默认第3个：近90天
    except ValueError:
        idx = 2  # 默认近90天

    if idx < 0 or idx >= len(DATE_PRESETS):
        idx = 2

    _, preset_days = DATE_PRESETS[idx]

    if preset_days == -1:
        # 自定义范围
        today_str = datetime.now().strftime("%Y-%m-%d")
        start_str = input(f"开始日期 [{today_str}] 格式 YYYY-MM-DD: ").strip()
        end_str = input(f"结束日期 [{today_str}] 格式 YYYY-MM-DD: ").strip()
        try:
            start = datetime.strptime(start_str, "%Y-%m-%d") if start_str else datetime.now() - timedelta(days=90)
            end = datetime.strptime(end_str, "%Y-%m-%d") if end_str else datetime.now()
            if start > end:
                start, end = end, start
            return start, end
        except ValueError:
            print("日期格式错误，使用默认近90天")
            return datetime.now() - timedelta(days=90), datetime.now()
    else:
        start = calc_preset_date(preset_days)
        return start, datetime.now()


def pick_date_range(auto_pick=True):
    """
    选择邮件下载时间范围
    auto_pick=True: 直接使用默认近90天，不弹窗
    返回 (start_date, end_date) datetime 对象，或 (None, None) 表示取消
    """
    if auto_pick:
        start = calc_preset_date(90)
        end = datetime.now()
        print(f"📅 默认范围: {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}（近90天）")
        return start, end
    system = platform.system()
    if system == "Darwin":
        return pick_date_range_macos()
    else:
        return pick_date_range_tkinter()



# ============================================================
# 主流程
# ============================================================

def select_or_register_account(auto_pick=True):
    """
    主入口：选择邮箱账户
    auto_pick=True: 有 last_used 时直接返回，不弹窗
    返回 account dict 或 None（用户取消）
    """
    data = load_accounts()
    accounts = data["accounts"]
    last_used_id = data.get("last_used_id")

    system = platform.system()

    # 已有账户 + 有上次使用记录 + 自动模式 → 直接返回
    if accounts and last_used_id and auto_pick:
        acc = get_account(last_used_id)
        if acc:
            print(f"✅ 自动使用: {acc['name']} ({acc['email']})")
            return acc

    while True:
        # 无账户 → 直接进入注册
        if not accounts:
            print("📭 尚未登记邮箱账户，请先注册")
            if system == "Darwin":
                new_acc = register_account_macos()
            else:
                new_acc = register_account_tkinter()

            if not new_acc:
                print("❌ 已取消")
                return None

            acc_id = add_account(new_acc)
            new_acc["id"] = acc_id
            set_last_used(acc_id)
            print(f"✅ 已保存: {new_acc['name']} ({new_acc['email']})")
            return new_acc

        # 有账户 → 弹出选择界面
        if system == "Darwin":
            chosen = manage_accounts_macos(accounts, last_used_id)
        else:
            chosen = pick_account_tkinter(accounts, last_used_id)

        if chosen is None:
            # 用户取消
            return None

        if chosen == "ADD_NEW":
            # 新增账户
            if system == "Darwin":
                new_acc = register_account_macos()
            else:
                new_acc = register_account_tkinter()

            if not new_acc:
                continue  # 取消注册，回到选择界面

            acc_id = add_account(new_acc)
            new_acc["id"] = acc_id
            set_last_used(acc_id)
            print(f"✅ 已保存: {new_acc['name']} ({new_acc['email']})")
            return new_acc

        # 用户选择了某个账户
        if isinstance(chosen, dict):
            set_last_used(chosen["id"])
            return chosen

        return None


# ============================================================
# 命令行入口（独立运行）
# ============================================================

def cmd_list():
    """列出所有账户"""
    data = load_accounts()
    accounts = data["accounts"]
    last_used = data.get("last_used_id")
    if not accounts:
        print("暂无已登记的邮箱账户")
        return
    for a in accounts:
        marker = " ⭐" if a.get("id") == last_used else ""
        print(f"  [{a.get('id', '?')}] {a['name']} ({a['email']}) - {a.get('imap_server', '?')}:{a.get('imap_port', '?')}{marker}")


def cmd_add():
    """新增账户"""
    system = platform.system()
    if system == "Darwin":
        new_acc = register_account_macos()
    else:
        new_acc = register_account_tkinter()
    if new_acc:
        add_account(new_acc)
        print(f"✅ 已添加: {new_acc['name']} ({new_acc['email']})")


def cmd_delete(acc_id):
    """删除账户"""
    acc = get_account(acc_id)
    if not acc:
        print(f"❌ 未找到账户: {acc_id}")
        return
    if delete_account_ui(acc):
        delete_account(acc_id)
        print(f"✅ 已删除: {acc['name']} ({acc['email']})")
    else:
        print("已取消")


def cmd_guide(provider_key):
    """显示授权码指引"""
    system = platform.system()
    if system == "Darwin":
        show_auth_guide_macos(provider_key)
    else:
        provider = PROVIDERS.get(provider_key)
        if provider:
            print(provider["guide"])


def main():
    if len(sys.argv) < 2:
        # 无参数：进入交互选择流程
        acc = select_or_register_account()
        if acc:
            print(f"\n✅ 已选择: {acc['name']} ({acc['email']})")
            print(f"   IMAP: {acc['imap_server']}:{acc['imap_port']}")
        else:
            print("已取消")
        return

    cmd = sys.argv[1].lower().strip()
    if cmd == "list":
        cmd_list()
    elif cmd == "add":
        cmd_add()
    elif cmd == "delete" and len(sys.argv) > 2:
        cmd_delete(sys.argv[2])
    elif cmd == "guide" and len(sys.argv) > 2:
        cmd_guide(sys.argv[2])
    else:
        print("用法:")
        print("  python3 email_manager.py            # 交互选择/注册")
        print("  python3 email_manager.py list       # 列出所有账户")
        print("  python3 email_manager.py add        # 新增账户")
        print("  python3 email_manager.py delete ID  # 删除账户")
        print("  python3 email_manager.py guide 163  # 查看授权码指引")


if __name__ == "__main__":
    main()
