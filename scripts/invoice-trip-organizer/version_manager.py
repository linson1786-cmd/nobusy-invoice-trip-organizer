#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill 版本管理器 —— 支持自动更新，不影响用户数据

- 版本检查：对比用户当前版本与 Skill 最新版本
- 自动更新：仅更新脚本文件（.py / .md / VERSION），保留用户数据
- 配置合并：保留用户 config.py 中的自定义配置，更新版本号，新增项自动合并
- 备份策略：更新前自动备份到 .backup/<version>，支持回退

使用方式：
  from version_manager import check_and_update
  check_and_update(config_path)  # 在脚本入口调用即可

版本号格式：支持 V1.0 / V1.1 格式（如 V1.0、V1.1）或 Semantic Versioning（如 1.0.0）
"""

import os
import sys
import shutil
import re
import datetime

# ========== 路径常量 ==========
# Skill 脚本目录（即本文件所在目录）
SKILL_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(SKILL_SCRIPTS_DIR, "VERSION")
CHANGELOG_FILE = os.path.join(SKILL_SCRIPTS_DIR, "CHANGELOG.md")

# 需要更新的脚本文件（按重要性排序）
SCRIPT_FILES = [
    "version_manager.py",
    "invoice_auto_organizer.py",
    "trip_auto_organizer.py",
    "download_invoices.py",
    "email_manager.py",
    "upload_files.py",
    "setup.py",
    "init.py",
    "audit_03_done.py",
]

# 版本相关文档（也参与更新）
DOC_FILES = [
    "VERSION",
    "CHANGELOG.md",
]


# ========== 版本解析 ==========

def parse_version(v_str):
    """解析版本号字符串为三元组 (major, minor, patch)
    支持 'v1.0.0' 或 '1.0.0' 格式
    """
    if not v_str:
        return (0, 0, 0)
    v_str = v_str.strip().lower().lstrip('v')
    parts = v_str.split('.')
    try:
        return tuple(int(p) for p in parts[:3])
    except (ValueError, TypeError):
        return (0, 0, 0)


def format_version(v_tuple):
    """将三元组格式化为字符串 'x.y.z'"""
    return ".".join(str(n) for n in v_tuple)


def compare_version(v1, v2):
    """比较版本号：v1 < v2 返回 -1，= 返回 0，> 返回 1"""
    a = parse_version(v1)
    b = parse_version(v2)
    if a < b:
        return -1
    elif a > b:
        return 1
    return 0


# ========== 版本读取 ==========

def get_skill_version():
    """读取 Skill 最新版本（从 VERSION 文件）"""
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return "0.0.0"


def get_user_version(config_path):
    """从用户 config.py 读取 SKILL_VERSION
    如果 config.py 中没有 SKILL_VERSION 字段，返回 "0.0.0"
    """
    if not os.path.exists(config_path):
        return "0.0.0"
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        m = re.search(r'^SKILL_VERSION\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return "0.0.0"


# ========== 更新检查 ==========

def check_update(config_path):
    """检查是否需要更新

    返回: (need_update: bool, current: str, latest: str, changelog: str)
    """
    user_v = get_user_version(config_path)
    skill_v = get_skill_version()
    cmp = compare_version(user_v, skill_v)

    changelog = ""
    if cmp < 0:
        changelog = get_changelog_since(user_v)

    return (cmp < 0, user_v, skill_v, changelog)


def get_changelog_since(since_version):
    """获取从 since_version 到最新版本的变更日志摘要"""
    if not os.path.exists(CHANGELOG_FILE):
        return "暂无变更日志"

    try:
        with open(CHANGELOG_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return "暂无变更日志"

    lines = []
    collect = False
    for line in content.split('\n'):
        stripped = line.strip()
        # 以 "## x.y.z" 或 "## [x.y.z]" 开头的视为版本标题
        if stripped.startswith('## '):
            # 提取版本号，如 "## 1.0.0" 或 "## [1.0.0] - 2026-01-01"
            match = re.search(r'##\s*\[?v?([\d.]+)', stripped)
            if match:
                v = match.group(1)
                if compare_version(since_version, v) < 0:
                    collect = True
                else:
                    if collect:
                        break  # 已经收集到新版本，遇到旧版本停止
                    collect = False
        if collect:
            lines.append(line)

    return '\n'.join(lines) if lines else "暂无新版本变更日志"


# ========== 备份机制 ==========

def create_backup(user_scripts_dir, current_version):
    """更新前创建备份
    备份到 .backup/<version>/
    """
    backup_dir = os.path.join(user_scripts_dir, ".backup", current_version)
    if os.path.exists(backup_dir):
        # 如果备份已存在，加时间戳
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = f"{backup_dir}_{ts}"

    os.makedirs(backup_dir, exist_ok=True)

    # 备份所有脚本文件 + config.py
    for fname in SCRIPT_FILES + DOC_FILES:
        src = os.path.join(user_scripts_dir, fname)
        if os.path.exists(src):
            dst = os.path.join(backup_dir, fname)
            shutil.copy2(src, dst)

    # 也备份 config.py（如果存在）
    config_path = os.path.join(user_scripts_dir, "config.py")
    if os.path.exists(config_path):
        shutil.copy2(config_path, os.path.join(backup_dir, "config.py"))

    return backup_dir


# ========== 配置合并 ==========

def merge_config(user_config_path, skill_template_path=None):
    """合并用户 config.py 与 Skill 最新配置模板

    策略：
    1. 保留用户 config.py 中所有现有配置项的值
    2. 更新 SKILL_VERSION 到最新版本
    3. 如果 Skill 模板新增了配置项，自动追加到用户 config.py
    4. 如果 Skill 模板中某些配置项的注释有更新，保留用户值但更新注释（可选）
    """
    if not os.path.exists(user_config_path):
        return False, "用户 config.py 不存在"

    try:
        with open(user_config_path, 'r', encoding='utf-8') as f:
            user_content = f.read()
    except Exception as e:
        return False, f"读取用户 config.py 失败: {e}"

    # 提取用户现有配置项（简单 key = value 匹配）
    user_keys = set()
    for line in user_content.split('\n'):
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and '=' in stripped:
            # 提取变量名（取等号前第一个 token）
            key = stripped.split('=')[0].strip()
            if key and not key.startswith('__'):
                user_keys.add(key)

    # 更新 SKILL_VERSION
    latest_version = get_skill_version()
    if 'SKILL_VERSION' in user_content:
        user_content = re.sub(
            r'^SKILL_VERSION\s*=\s*"[^"]*"',
            f'SKILL_VERSION = "{latest_version}"',
            user_content,
            flags=re.MULTILINE
        )
    else:
        # 在文件开头添加版本标记
        user_content = f'# -*- Skill 版本 -*-\nSKILL_VERSION = "{latest_version}"\n\n' + user_content

    # 如果提供了模板，尝试合并新增配置项
    if skill_template_path and os.path.exists(skill_template_path):
        try:
            with open(skill_template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()

            # 解析模板中的配置项
            template_lines = template_content.split('\n')
            new_lines = []
            for line in template_lines:
                stripped = line.strip()
                if stripped and not stripped.startswith('#') and '=' in stripped:
                    key = stripped.split('=')[0].strip()
                    if key and key not in user_keys and not key.startswith('__'):
                        # 这是一个新配置项，连同前面的注释一起提取
                        # 简单实现：直接追加
                        new_lines.append(line)

            if new_lines:
                user_content += '\n\n# ===== 新版本新增配置项 =====\n'
                user_content += '\n'.join(new_lines) + '\n'
        except Exception:
            pass

    # 写回文件
    try:
        with open(user_config_path, 'w', encoding='utf-8') as f:
            f.write(user_content)
        return True, "config.py 已更新版本号"
    except Exception as e:
        return False, f"写入 config.py 失败: {e}"


# ========== 自动更新 ==========

def auto_update(config_path, user_scripts_dir=None, silent=False):
    """执行自动更新

    参数:
        config_path: 用户 config.py 的绝对路径
        user_scripts_dir: 用户脚本目录（默认从 config_path 推断）
        silent: 是否静默模式（不打印进度，只返回结果）

    返回: (success: bool, message: str)
    """
    if user_scripts_dir is None:
        user_scripts_dir = os.path.dirname(os.path.abspath(config_path))

    # 确保 Skill 目录和用户脚本目录有效
    if not os.path.exists(SKILL_SCRIPTS_DIR):
        return False, f"Skill 脚本目录不存在: {SKILL_SCRIPTS_DIR}"

    if not os.path.exists(user_scripts_dir):
        return False, f"用户脚本目录不存在: {user_scripts_dir}"

    current_v = get_user_version(config_path)
    latest_v = get_skill_version()

    if not silent:
        print(f"\n{'='*50}")
        print(f"🔄 Skill 版本更新")
        print(f"{'='*50}")
        print(f"当前版本: {current_v}")
        print(f"最新版本: {latest_v}")

    # 1. 创建备份
    try:
        backup_dir = create_backup(user_scripts_dir, current_v)
        if not silent:
            print(f"✅ 备份已创建: {backup_dir}")
    except Exception as e:
        if not silent:
            print(f"⚠️ 备份创建失败: {e}")
        return False, f"备份创建失败: {e}"

    # 2. 更新脚本文件
    updated = []
    failed = []

    for fname in SCRIPT_FILES + DOC_FILES:
        src = os.path.join(SKILL_SCRIPTS_DIR, fname)
        dst = os.path.join(user_scripts_dir, fname)
        if src == dst:
            # 源文件和目标文件相同（Skill 目录即用户目录），跳过
            continue
        if os.path.exists(src):
            try:
                shutil.copy2(src, dst)
                updated.append(fname)
            except Exception as e:
                failed.append(f"{fname}: {e}")
        elif os.path.exists(dst):
            # Skill 目录中不存在，但用户目录有（旧版本残留）——删除
            try:
                os.remove(dst)
            except Exception:
                pass

    # 3. 更新 docs/ 目录（如果 Skill 中有）
    skill_docs_dir = os.path.join(os.path.dirname(SKILL_SCRIPTS_DIR), "docs")
    user_docs_dir = os.path.join(os.path.dirname(user_scripts_dir), "docs")
    if os.path.exists(skill_docs_dir) and skill_docs_dir != user_docs_dir:
        try:
            if os.path.exists(user_docs_dir):
                shutil.rmtree(user_docs_dir)
            shutil.copytree(skill_docs_dir, user_docs_dir)
            updated.append("docs/")
        except Exception as e:
            failed.append(f"docs/: {e}")

    # 4. 合并用户 config.py（保留用户配置，更新版本号）
    template_path = os.path.join(SKILL_SCRIPTS_DIR, "config_template.py")
    ok, msg = merge_config(config_path, template_path)
    if ok:
        updated.append("config.py (合并)")
    else:
        failed.append(f"config.py: {msg}")

    # 5. 输出结果
    if not silent:
        print(f"\n{'='*50}")
        print(f"✅ 已更新 {len(updated)} 个文件")
        if updated:
            for f in updated:
                print(f"   - {f}")
        if failed:
            print(f"\n⚠️ 失败 {len(failed)} 个:")
            for f in failed:
                print(f"   - {f}")
        print(f"\n{'='*50}")

    if failed and not updated:
        return False, f"更新失败: {', '.join(failed[:3])}"
    elif failed:
        return True, f"更新成功（部分失败）: {', '.join(failed[:3])}"
    else:
        return True, f"更新成功: {len(updated)} 个文件"


def check_and_update(config_path, user_scripts_dir=None, auto=True, silent=False):
    """检查版本并自动更新（推荐入口函数）

    参数:
        config_path: 用户 config.py 的绝对路径
        user_scripts_dir: 用户脚本目录（默认从 config_path 推断）
        auto: 如果 True，检测到新版本时自动更新；False 则只提示
        silent: 是否静默模式

    返回: (need_update: bool, message: str)
    """
    need_update, current_v, latest_v, changelog = check_update(config_path)

    if not need_update:
        if not silent:
            print(f"✅ Skill 版本已是最新 ({current_v})")
        return False, f"当前版本 {current_v} 已是最新"

    if not silent:
        print(f"\n{'='*50}")
        print(f"🚀 发现新版本: {latest_v}（当前: {current_v}）")
        print(f"{'='*50}")
        if changelog:
            print("\n📋 变更日志:")
            print(changelog)
            print()

    if auto:
        success, msg = auto_update(config_path, user_scripts_dir, silent=silent)
        if success and not silent:
            print(f"✅ 自动更新完成: {msg}")
        elif not silent:
            print(f"⚠️ 自动更新失败: {msg}")
        return True, msg
    else:
        if not silent:
            print(f"💡 请运行 `python3 version_manager.py` 手动更新")
        return True, f"发现新版本 {latest_v}，请手动更新"


# ========== 命令行入口 ==========

if __name__ == "__main__":
    """命令行入口：python3 version_manager.py [config_path]"""
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        # 默认使用当前目录下的 config.py
        config_path = os.path.join(SKILL_SCRIPTS_DIR, "config.py")

    if not os.path.exists(config_path):
        print(f"❌ config.py 不存在: {config_path}")
        print("用法: python3 version_manager.py <config_path>")
        sys.exit(1)

    # 检查并自动更新
    need_update, current, latest, changelog = check_update(config_path)

    print(f"Skill 最新版本: {latest}")
    print(f"用户当前版本: {current}")
    print()

    if need_update:
        print(f"🚀 需要更新（{current} → {latest}）")
        if changelog:
            print("\n📋 变更日志:")
            print(changelog)
            print()
        print("开始自动更新...")
        print()
        success, msg = auto_update(config_path)
        print(f"\n结果: {msg}")
    else:
        print("✅ 已是最新版本，无需更新")
        print()
        print(f"📋 完整变更日志:\n{changelog}")
