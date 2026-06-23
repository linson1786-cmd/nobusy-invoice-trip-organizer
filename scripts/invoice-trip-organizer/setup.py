#!/usr/bin/env python3
"""
个人行程与报销 - 初始化设置 & 重置
用法:
  python3 setup.py init    # 初始化设置：弹出文件夹选择窗口，创建目录架构
  python3 setup.py reset   # 重置：确认后删除目录架构，再跳到初始化设置
"""
import os
import sys
import shutil
import subprocess
import platform
import importlib.util
from datetime import datetime

# ===== 常量 =====
SKILL_NAME = "个人行程与报销"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_SCRIPTS_DIR = SCRIPT_DIR
SKILL_DOCS_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "docs")

# 需要复制到工作目录的脚本文件
SCRIPT_FILES = [
    "version_manager.py",
    "invoice_auto_organizer.py",
    "trip_auto_organizer.py",
    "download_invoices.py",
    "email_manager.py",
    "upload_files.py",
    "audit_03_done.py",
    "init.py",
    "setup.py",
    "config_template.py",
    "VERSION",
    "CHANGELOG.md",
]

# 需要复制到工作目录的文档
DOC_FILES = [
    ("SOP-发票文件命名标准.md", "SOP-发票文件命名标准.md"),
]


# ============================================================
# 对话框工具（macOS osascript 优先，tkinter 回退）
# ============================================================

def pick_folder_macos(prompt="选择文件夹"):
    """macOS: 使用 osascript 弹出原生文件夹选择窗口"""
    script = f'''
    set theFolder to choose folder with prompt "{prompt}"
    return POSIX path of theFolder
    '''
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            stderr_lower = (result.stderr or '').lower()
            if 'cancel' in stderr_lower or 'user canceled' in stderr_lower or '-128' in stderr_lower:
                return None
            # osascript 失败（非用户取消），打印错误并返回 None
            print(f"⚠️  osascript 弹窗失败: {result.stderr.strip() if result.stderr else '未知错误'}")
            return None
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        print("⚠️  选择文件夹超时")
        return None
    except FileNotFoundError:
        print("⚠️  osascript 不可用")
        return None


def pick_folder_tkinter(prompt="选择文件夹"):
    """跨平台回退: tkinter 文件夹选择"""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print('错误: 无法加载文件选择器')
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder = filedialog.askdirectory(title=prompt, parent=root)
    root.destroy()
    return folder if folder else None


def pick_folder(prompt="选择文件夹"):
    system = platform.system()
    if system == 'Darwin':
        return pick_folder_macos(prompt)
    else:
        return pick_folder_tkinter(prompt)


def confirm_dialog_macos(title, message, confirm_button="确认删除", cancel_button="取消"):
    """macOS: 使用 osascript 弹出确认对话框，返回 True/False"""
    # 转义双引号
    safe_title = title.replace('"', '\\"')
    safe_message = message.replace('"', '\\"').replace('\n', '\\n')
    script = f'''
    set theResponse to display dialog "{safe_message}" with title "{safe_title}" buttons {{"{cancel_button}", "{confirm_button}"}} default button "{cancel_button}" with icon caution
    if button returned of theResponse is "{confirm_button}" then
        return "confirmed"
    else
        return "cancelled"
    end if
    '''
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            stderr_lower = (result.stderr or '').lower()
            if 'cancel' in stderr_lower or 'user canceled' in stderr_lower or '-128' in stderr_lower:
                return False
            # osascript 失败（非用户取消），打印错误并返回 False
            print(f"⚠️  osascript 对话框失败: {result.stderr.strip() if result.stderr else '未知错误'}")
            return False
        return result.stdout.strip() == 'confirmed'
    except subprocess.TimeoutExpired:
        print("⚠️  对话框超时")
        return False
    except FileNotFoundError:
        print("⚠️  osascript 不可用")
        return False


def confirm_dialog_tkinter(title, message, confirm_button="确认删除", cancel_button="取消"):
    """跨平台回退: tkinter 确认对话框"""
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        print(f'\n{title}')
        print(message)
        ans = input(f'\n输入 yes 确认，其他取消: ')
        return ans.strip().lower() == 'yes'

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    # messagebox 不支持自定义按钮文字，用 askyesno
    result = messagebox.askyesno(title, message, icon='warning', parent=root)
    root.destroy()
    return result


def confirm_dialog(title, message, confirm_button="确认删除", cancel_button="取消"):
    system = platform.system()
    if system == 'Darwin':
        return confirm_dialog_macos(title, message, confirm_button, cancel_button)
    else:
        return confirm_dialog_tkinter(title, message, confirm_button, cancel_button)


# ============================================================
# 配置文件查找与生成
# ============================================================

def find_config():
    """查找 config.py，返回 (config_module, config_path) 或 (None, None)"""
    search_dirs = [
        SCRIPT_DIR,
        SKILL_SCRIPTS_DIR,
    ]
    for d in search_dirs:
        config_path = os.path.join(d, "config.py")
        if os.path.exists(config_path):
            try:
                spec = importlib.util.spec_from_file_location("config", config_path)
                config = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(config)
                return config, config_path
            except Exception:
                pass
    return None, None


def get_current_base_dir(config):
    """从 config 中推断 个人行程与报销 根目录"""
    # 优先用 OBSIDIAN_VAULT
    vault = getattr(config, 'OBSIDIAN_VAULT', None)
    if vault:
        vault = os.path.expanduser(vault)
        candidate = os.path.join(vault, SKILL_NAME)
        if os.path.exists(candidate):
            return candidate
        return candidate  # 即使不存在也返回（用于显示）

    # 回退: 从 BASE_ROOT 推断
    base_root = getattr(config, 'BASE_ROOT', None)
    if base_root:
        # BASE_ROOT = .../个人行程与报销/01 发票整理
        # 向上两级 = .../个人行程与报销
        return os.path.dirname(os.path.dirname(base_root))

    return None


def generate_config_py(vault_path, skill_version="1.0.0"):
    """生成 config.py 内容"""
    invoice_base = os.path.join(vault_path, SKILL_NAME, "01 发票整理")
    trip_base = os.path.join(vault_path, SKILL_NAME, "02 行程与个人报销单")

    content = f'''"""
配置文件 - 个人行程与报销
由 setup.py 自动生成
生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

首次使用:
  1. 填写 EMAIL_ADDRESS 和 EMAIL_AUTH_CODE（如需邮件下载功能）
  2. 把发票放入 01 待分类/，运行 invoice_auto_organizer.py
"""

# ========== Skill 版本（由版本管理器自动更新，请勿手动修改）==========
SKILL_VERSION = "{skill_version}"

# ========== 路径配置 ==========

# 项目根目录（个人行程与报销 的父目录）
OBSIDIAN_VAULT = "{vault_path}"

# 发票整理相对路径
INVOICE_BASE_REL = "个人行程与报销/01 发票整理"

# 行程与报销单相对路径
TRIP_BASE_REL = "个人行程与报销/02 行程与个人报销单"

# ===== 脚本实际使用的路径变量 =====

# 发票整理根目录（脚本用）
BASE_ROOT = "{invoice_base}"
INPUT_DIR = BASE_ROOT + "/01 待分类"
DONE_DIR = BASE_ROOT + "/03 已完成"
REVIEW_DIR = BASE_ROOT + "/02 待核实"
LOG_FILE = BASE_ROOT + "/.organizer_log.json"

# 行程根目录（trip脚本用）
INVOICE_ROOT = BASE_ROOT
TRIP_ROOT = "{trip_base}"

# 报销单 Excel 模板路径（如有模板则填写，否则留空）
REIMBURSEMENT_TEMPLATE = ""


# ========== 邮箱配置（按需填写） ==========

# 163 邮箱
EMAIL_ADDRESS = "your_email@163.com"
EMAIL_AUTH_CODE = "YOUR_AUTH_CODE"
IMAP_SERVER = "imap.163.com"
IMAP_PORT = 993

# QQ 邮箱（可选）
QQ_EMAIL_ADDRESS = ""
QQ_EMAIL_AUTH_CODE = ""

# 邮件附件下载目录
EMAIL_DOWNLOAD_DIR = "email_attachments"


# ========== 分类规则（一般无需修改） ==========

VALID_CATEGORIES = [
    "餐饮", "住宿", "机票", "高铁", "滴滴打车", "行程单", "高速费", "充电费", "礼品", "结账单", "其他",
    "机票(保险)", "滴滴打车(行程单)", "住宿(结账单)", "高速费(行程单)"
]

IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.heic', '.bmp', '.tiff', '.tif', '.webp']
PROCESSABLE_EXTENSIONS = ['.pdf'] + IMAGE_EXTENSIONS

CAT_TO_SUBDIR = {{
    "机票": "机票高铁", "机票(保险)": "机票高铁", "高铁": "机票高铁",
    "住宿": "住宿", "住宿(结账单)": "住宿",
    "餐饮": "餐饮",
    "滴滴打车": "打车", "滴滴打车(行程单)": "打车",
    "礼品": "礼品",
    "高速费": "其他", "高速费(行程单)": "其他",
    "充电费": "其他", "行程单": "其他", "结账单": "其他", "其他": "其他",
}}

SUBDIRS = ["机票高铁", "住宿", "餐饮", "打车", "礼品", "其他"]
NON_REIMBURSE = ["行程单", "滴滴打车(行程单)", "高速费(行程单)", "住宿(结账单)", "结账单"]

CATEGORY_RULES = [
    (["结账单", "水单"], "结账单"),
    (["行程单", "行程报销单", "出行记录", "出行行程"], "行程单"),
    (["住宿", "酒店", "华住", "全季", "入住", "房费", "离店"], "住宿"),
    (["蟹", "手信", "礼品", "礼盒", "水果", "玩具",
      "日用杂品", "日用品", "日化用品",
      "移动通信设备", "通讯器材"], "礼品"),
    (["高速", "通行费", "路桥费", "ETC"], "高速费"),
    (["充电", "蔚来", "NIO", "换电", "充电桩"], "充电费"),
    (["滴滴", "打车", "网约车", "交通运输服务", "客运服务费"], "滴滴打车"),
    (["火车票", "高铁", "车票", "铁路", "电子客票"], "高铁"),
    (["机票", "航空", "航班", "登机牌",
      "保险服务", "经纪代理服务"], "机票"),
    (["餐饮", "餐费", "餐厅", "饭店", "酒水"], "餐饮"),
]

SUBTYPE_RULES = [
    ("机票", ["保险服务", "保险"], "(保险)"),
    ("行程单", ["滴滴", "打车", "网约车"], "(行程单)"),
    ("行程单", ["高速", "通行费", "ETC"], "(行程单)"),
    ("结账单", ["酒店", "住宿", "入住", "离店"], "(结账单)"),
]

MAJOR_CITIES = [
    "上海", "北京", "广州", "深圳", "杭州", "成都", "重庆", "西安",
    "苏州", "南京", "武汉", "天津", "长沙",
    "昆明", "贵阳", "郑州", "合肥",
    "珠海", "中山", "佛山", "东莞",
]

FONT_PATH = "/Library/Fonts/Arial Unicode.ttf"

DEBUG = False
OCR_LANGUAGE = "chi_sim+eng"
'''
    return content


# ============================================================
# 初始化 MD 文件内容
# ============================================================

def get_log_md_content(section_name):
    today = datetime.now().strftime("%Y-%m-%d")
    return f"""# {section_name} 日志

> 本文件由脚本自动追加，记录每次处理日志。

## {today} 初始化

- 目录由 setup.py 创建
"""


def get_ledger_md_content():
    return """# 03 已完成 台账

> 本文件由 invoice_auto_organizer.py 自动维护，请勿手动编辑。

## 按月汇总

| 年月 | 发票数 | 报销金额 | 非报销金额 | 小计 |
|------|--------|----------|------------|------|
| — | 0 | ¥0.00 | ¥0.00 | ¥0.00 |

## 明细

| 序号 | 日期 | 类别 | 金额 | 文件名 | 备注 |
|------|------|------|------|--------|------|
"""


def get_total_ledger_md_content():
    return """# 总台账

> 本文件由 invoice_auto_organizer.py 自动维护，记录全局汇总。

## 按月汇总

| 年月 | 发票数 | 报销金额 | 非报销金额 | 小计 |
|------|--------|----------|------------|------|
| — | 0 | ¥0.00 | ¥0.00 | ¥0.00 |

## 按类别汇总

| 类别 | 发票数 | 金额 |
|------|--------|------|
| — | 0 | ¥0.00 |

## 总计

- 发票总数: 0
- 报销总额: ¥0.00
- 非报销总额: ¥0.00
"""


def get_trip_overview_md_content():
    return """# 2026 年行程总览

> 本文件由 trip_auto_organizer.py 自动维护，可手动补充行程信息。

## 行程列表

| 序号 | 出发日期 | 返回日期 | 出发地 | 目的地 | 事由 | 发票数 | 金额 | 报销单 |
|------|----------|----------|--------|--------|------|--------|------|--------|
| — | — | — | — | — | — | 0 | ¥0.00 | — |
"""


# ============================================================
# 初始化设置
# ============================================================

def do_init():
    """初始化设置：弹出文件夹选择窗口，创建目录架构"""
    print("=" * 50)
    print("初始化设置 - 个人行程与报销")
    print("=" * 50)
    print()
    print("请在弹出的窗口中选择「个人行程与报销」的父目录")
    print("（将在所选目录下创建「个人行程与报销/」子目录）")
    print()

    # 1. 选择文件夹
    vault_path = pick_folder("选择「个人行程与报销」的父目录")
    if not vault_path:
        print("未选择文件夹，初始化取消")
        return False

    vault_path = os.path.expanduser(vault_path)
    base_dir = os.path.join(vault_path, SKILL_NAME)

    print(f"选定目录: {vault_path}")
    print(f"将创建: {base_dir}")
    print()

    # 2. 检查是否已存在（非破坏性，无需确认）
    if os.path.exists(base_dir):
        print(f"ℹ️  目录已存在: {base_dir}")
        print("   → 保留已有文件，仅补充缺失项")
    print()

    # 3. 创建目录结构
    print("📁 创建目录结构...")
    current_year = datetime.now().year
    dirs_to_create = [
        base_dir,
        os.path.join(base_dir, "01 发票整理", "01 待分类"),
        os.path.join(base_dir, "01 发票整理", "02 待核实"),
        os.path.join(base_dir, "01 发票整理", "03 已完成"),
        os.path.join(base_dir, "02 行程与个人报销单"),
        os.path.join(base_dir, "02 行程与个人报销单", f"{current_year} 年"),
        os.path.join(base_dir, "scripts"),
    ]
    # 12 个月子目录
    for m in range(1, 13):
        dirs_to_create.append(
            os.path.join(base_dir, "02 行程与个人报销单", f"{current_year} 年", f"{m} 月")
        )

    created = 0
    for d in dirs_to_create:
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
            print(f"  ✅ 创建: {os.path.relpath(d, vault_path)}")
            created += 1
        else:
            print(f"  ⏩ 已存在: {os.path.relpath(d, vault_path)}")
    print(f"  共创建 {created} 个新目录")
    print()

    # 4. 创建初始化 MD 文件
    print("📝 创建初始化文件...")
    md_files = [
        (os.path.join(base_dir, "01 发票整理", "01 待分类", "日志.md"),
         get_log_md_content("01 待分类")),
        (os.path.join(base_dir, "01 发票整理", "02 待核实", "日志.md"),
         get_log_md_content("02 待核实")),
        (os.path.join(base_dir, "01 发票整理", "03 已完成", "台账.md"),
         get_ledger_md_content()),
        (os.path.join(base_dir, "总台账.md"),
         get_total_ledger_md_content()),
        (os.path.join(base_dir, "02 行程与个人报销单", f"{current_year} 年", "行程总览.md"),
         get_trip_overview_md_content()),
    ]
    for path, content in md_files:
        rel = os.path.relpath(path, vault_path)
        if not os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  ✅ 创建: {rel}")
        else:
            print(f"  ⏩ 已存在: {rel}")
    print()

    # 5. 复制脚本文件
    print("📋 复制脚本文件...")
    src_scripts_dir = SKILL_SCRIPTS_DIR if os.path.isdir(SKILL_SCRIPTS_DIR) else SCRIPT_DIR
    dst_scripts_dir = os.path.join(base_dir, "scripts")
    copied_scripts = 0
    for fname in SCRIPT_FILES:
        src = os.path.join(src_scripts_dir, fname)
        dst = os.path.join(dst_scripts_dir, fname)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  ✅ {fname}")
            copied_scripts += 1
        else:
            print(f"  ⚠️  源文件不存在: {fname}")
    print(f"  共复制 {copied_scripts} 个脚本")
    print()

    # 6. 复制 SOP 文档
    print("📋 复制 SOP 文档...")
    for src_name, dst_name in DOC_FILES:
        src = os.path.join(SKILL_DOCS_DIR, src_name)
        dst = os.path.join(base_dir, dst_name)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  ✅ {dst_name}")
        else:
            print(f"  ⚠️  源文件不存在: {src_name}")
    print()

    # 7. 生成 config.py
    print("⚙️  生成 config.py...")
    # 6.5. 生成 config.py（读取 Skill 最新版本号）
    # 读取 Skill VERSION 文件获取最新版本号
    skill_version = "V1.0"
    version_file = os.path.join(src_scripts_dir, "VERSION")
    if os.path.exists(version_file):
        with open(version_file, 'r', encoding='utf-8') as f:
            skill_version = f.read().strip() or "1.0.0"
    
    config_content = generate_config_py(vault_path, skill_version=skill_version)
    config_path = os.path.join(dst_scripts_dir, "config.py")
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(config_content)
    print(f"  ✅ {os.path.relpath(config_path, vault_path)}")

    # 同时写入 skill 目录（供 reset 查找）
    skill_config_path = os.path.join(SKILL_SCRIPTS_DIR, "config.py")
    if os.path.isdir(SKILL_SCRIPTS_DIR):
        with open(skill_config_path, 'w', encoding='utf-8') as f:
            f.write(config_content)
        print(f"  ✅ 同步到 skill 目录: {skill_config_path}")
    print()

    # 8. 完成
    print("=" * 50)
    print("✅ 初始化设置完成!")
    print()
    print("目录结构:")
    print(f"  {base_dir}/")
    print(f"  ├── 01 发票整理/")
    print(f"  │   ├── 01 待分类/     ← 放入新发票")
    print(f"  │   ├── 02 待核实/     ← 脚本无法识别的文件")
    print(f"  │   └── 03 已完成/     ← 已整理归档")
    print(f"  ├── 02 行程与个人报销单/{current_year} 年/")
    print(f"  ├── scripts/           ← 脚本和配置")
    print(f"  ├── SOP-发票文件命名标准.md")
    print(f"  └── 总台账.md")
    print()
    print("下一步:")
    print("  1. 把发票文件放入 01 待分类/")
    print("  2. 运行: python3 invoice_auto_organizer.py")
    print("  3. 或对我说「发票整理」")
    print("=" * 50)
    return True


# ============================================================
# 重置
# ============================================================

def do_reset():
    """重置：确认后删除目录架构，再跳到初始化设置"""
    print("=" * 50)
    print("重置 - 个人行程与报销")
    print("=" * 50)
    print()

    # 1. 查找当前 config.py
    config, config_path = find_config()
    if not config:
        print("⚠️  未找到 config.py，无法确定当前目录")
        print("   请先运行「初始化设置」")
        return False

    base_dir = get_current_base_dir(config)
    if not base_dir:
        print("⚠️  无法从 config.py 中确定目录路径")
        return False

    print(f"当前目录: {base_dir}")
    print()

    # 2. 检查目录是否存在
    if not os.path.exists(base_dir):
        print("⚠️  目录不存在，可能已被删除")
        print("   直接跳转到初始化设置...")
        print()
        return do_init()

    # 3. 统计目录内容
    file_count = 0
    dir_count = 0
    total_size = 0
    for root, dirs, files in os.walk(base_dir):
        dir_count += len(dirs)
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                total_size += os.path.getsize(fpath)
                file_count += 1
            except OSError:
                pass

    size_str = f"{total_size / 1024:.1f} KB" if total_size < 1024 * 1024 else f"{total_size / 1024 / 1024:.1f} MB"

    print(f"目录内容统计:")
    print(f"  子目录: {dir_count} 个")
    print(f"  文件: {file_count} 个")
    print(f"  总大小: {size_str}")
    print()

    # 4. 弹出确认对话框
    message = (
        f"⚠️ 警告：即将删除以下目录及其所有内容！\n\n"
        f"路径：{base_dir}\n\n"
        f"包含：{file_count} 个文件，{dir_count} 个子目录，{size_str}\n\n"
        f"此操作不可撤销！所有发票、行程、报销单将被永久删除。\n\n"
        f"确认要继续吗？"
    )

    confirmed = confirm_dialog(
        "重置确认 - 个人行程与报销",
        message,
        confirm_button="确认删除",
        cancel_button="取消"
    )

    if not confirmed:
        print("❌ 已取消，未执行任何操作")
        return False

    # 5. 执行删除
    print()
    print("🗑️  正在删除目录...")
    try:
        shutil.rmtree(base_dir)
        print(f"  ✅ 已删除: {base_dir}")
    except Exception as e:
        print(f"  ❌ 删除失败: {e}")
        print("  请手动删除该目录后重新运行")
        return False

    # 6. 清理 skill 目录中的 config.py
    skill_config_path = os.path.join(SKILL_SCRIPTS_DIR, "config.py")
    if os.path.exists(skill_config_path):
        try:
            os.remove(skill_config_path)
            print(f"  ✅ 已清理 skill 目录 config.py")
        except Exception:
            pass

    print()
    print("✅ 重置完成，目录已清空")
    print()

    # 7. 切换到安全目录（当前工作目录可能已被删除）
    try:
        os.chdir(os.path.expanduser("~"))
    except OSError:
        pass

    # 8. 询问是否立即进行初始化设置
    do_init_now = confirm_dialog(
        "重置完成 - 个人行程与报销",
        "重置完成，目录已清空。\n\n是否立即进行初始化设置？",
        confirm_button="初始化设置",
        cancel_button="暂时不用"
    )

    if do_init_now:
        print("→ 跳转到初始化设置...")
        print()
        return do_init()
    else:
        print("→ 未进行初始化设置。需要时可随时运行「初始化设置」。")
        return True


# ============================================================
# 主入口
# ============================================================

def main():
    # 版本检查（自动更新）
    # 如果存在 config.py，先检查是否需要更新
    config, config_path = find_config()
    if config and config_path and os.path.exists(config_path):
        try:
            sys.path.insert(0, os.path.dirname(config_path))
            import version_manager
            need_update, msg = version_manager.check_and_update(config_path, auto=True, silent=False)
            if need_update:
                print(f"\n📦 版本更新: {msg}\n")
                # 更新后重新加载 config
                config, config_path = find_config()
        except Exception as e:
            # 版本检查失败不影响主流程
            pass

    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 setup.py init    # 初始化设置")
        print("  python3 setup.py reset   # 重置（删除目录，可选重新初始化）")
        print("  python3 setup.py update  # 检查并更新到最新版本")
        sys.exit(1)

    mode = sys.argv[1].lower().strip()
    if mode == 'init':
        success = do_init()
        sys.exit(0 if success else 1)
    elif mode == 'reset':
        success = do_reset()
        sys.exit(0 if success else 1)
    elif mode == 'update':
        # 手动触发更新
        if not config or not config_path:
            print("⚠️  未找到 config.py，无法执行更新")
            print("   请先运行「初始化设置」")
            sys.exit(1)
        try:
            sys.path.insert(0, os.path.dirname(config_path))
            import version_manager
            success, msg = version_manager.auto_update(config_path, silent=False)
            print(f"\n{msg}")
            sys.exit(0 if success else 1)
        except Exception as e:
            print(f"❌ 更新失败: {e}")
            sys.exit(1)
    else:
        print(f"未知模式: {mode}")
        print("用法:")
        print("  python3 setup.py init    # 初始化设置")
        print("  python3 setup.py reset   # 重置")
        print("  python3 setup.py update  # 检查并更新到最新版本")
        sys.exit(1)


if __name__ == '__main__':
    main()
