#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
个人行程与报销 Skill 部署工具

功能：
  1. 将项目源码部署到 ~/.workbuddy/skills/invoice-trip-organizer/
  2. 版本对比：仅当源码版本 > 已部署版本时执行更新
  3. 更新前自动备份到 .backup/<version>_<timestamp>/
  4. 仅更新 Skill 文件，绝不触碰用户数据（发票、行程、台账、config.py）
  5. --upgrade：从 GitHub 自动拉取最新版本并部署

使用方式：
  python3 deploy.py              # 检查并部署（从本地源码）
  python3 deploy.py --force      # 强制重新部署（忽略版本对比）
  python3 deploy.py --status     # 仅查看版本状态，不执行部署
  python3 deploy.py --backup     # 仅创建备份，不更新
  python3 deploy.py --upgrade    # 从 GitHub 拉取最新版本并自动部署
  python3 deploy.py --check-update  # 仅检查是否有新版本可用

版本号格式：Semantic Versioning（如 1.0.x）
"""

import os
import sys
import shutil
import re
import datetime
import json
import urllib.request
import urllib.error

# ============================================================
# 路径常量
# ============================================================

# 项目源码根目录（本文件位于 scripts/invoice-trip-organizer/deploy.py）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_SCRIPTS = os.path.join(PROJECT_ROOT, "scripts", "invoice-trip-organizer")
PROJECT_VERSION_FILE = os.path.join(PROJECT_SCRIPTS, "VERSION")
PROJECT_CHANGELOG = os.path.join(PROJECT_SCRIPTS, "CHANGELOG.md")

# 部署目标路径
DEPLOY_TARGET = os.path.expanduser("~/.workbuddy/skills/invoice-trip-organizer")
DEPLOY_SCRIPTS = os.path.join(DEPLOY_TARGET, "scripts")
DEPLOY_VERSION_FILE = os.path.join(DEPLOY_SCRIPTS, "VERSION")

# 需要部署的脚本文件（从 scripts/invoice-trip-organizer/ 复制到 scripts/）
SCRIPT_FILES = [
    "version_manager.py",
    "invoice_auto_organizer.py",
    "trip_auto_organizer.py",
    "download_invoices.py",
    "email_manager.py",
    "upload_files.py",
    "import_trips.py",
    "setup.py",
    "init.py",
    "audit_03_done.py",
    "release_check.py",
    "config_template.py",
    "deploy.py",
    "VERSION",
    "CHANGELOG.md",
]

# 绝对不能覆盖的文件（用户个人配置）
PROTECTED_FILES = [
    "config.py",
]

# 需要部署的顶层文件（从项目根目录复制）
TOP_LEVEL_FILES = [
    "SKILL.md",
]

# ============================================================
# 远程仓库配置（用于 --upgrade）
# ============================================================

GITHUB_REPO = "https://github.com/linson1786-cmd/nobusy-invoice-trip-organizer.git"
# 仓库中脚本所在路径（相对于仓库根目录）
REPO_SCRIPTS_PATH = os.path.join("scripts", "invoice-trip-organizer")


# ============================================================
# 版本解析（Semantic Versioning）
# ============================================================

def parse_version(v_str):
    """解析语义化版本号为三元组 (major, minor, patch)
    支持 '1.0.0' / 'v1.0.0' 格式
    """
    if not v_str:
        return (0, 0, 0)
    v_str = v_str.strip().lower().lstrip('v')
    parts = v_str.split('.')
    try:
        result = []
        for p in parts[:3]:
            result.append(int(p))
        while len(result) < 3:
            result.append(0)
        return tuple(result)
    except (ValueError, TypeError):
        return (0, 0, 0)


def format_version(v_tuple):
    """格式化版本元组为 'x.y.z' 格式"""
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


# ============================================================
# 版本读取
# ============================================================

def get_source_version():
    """读取项目源码版本"""
    if os.path.exists(PROJECT_VERSION_FILE):
        with open(PROJECT_VERSION_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return "0.0.0"


def get_deployed_version():
    """读取已部署版本"""
    if os.path.exists(DEPLOY_VERSION_FILE):
        with open(DEPLOY_VERSION_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None  # 未部署


# ============================================================
# 备份机制
# ============================================================

def create_backup():
    """更新前备份当前已部署的文件"""
    if not os.path.exists(DEPLOY_TARGET):
        return None, "目标目录不存在，无需备份"

    deployed_v = get_deployed_version() or "unknown"
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(DEPLOY_SCRIPTS, ".backup", f"{deployed_v}_{timestamp}")

    os.makedirs(backup_dir, exist_ok=True)

    # 备份脚本文件
    for fname in SCRIPT_FILES:
        src = os.path.join(DEPLOY_SCRIPTS, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(backup_dir, fname))

    # 备份顶层文件
    for fname in TOP_LEVEL_FILES:
        src = os.path.join(DEPLOY_TARGET, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(backup_dir, fname))

    # 也备份 config.py（用户配置）
    config_path = os.path.join(DEPLOY_SCRIPTS, "config.py")
    if os.path.exists(config_path):
        shutil.copy2(config_path, os.path.join(backup_dir, "config.py"))

    return backup_dir, f"备份到 {backup_dir}"


# ============================================================
# 本地部署逻辑（从本地源码到部署目录）
# ============================================================

def deploy(force=False):
    """执行部署（从本地 PROJECT_ROOT 复制到 DEPLOY_TARGET）"""
    source_v = get_source_version()
    deployed_v = get_deployed_version()

    print(f"\n{'='*50}")
    print(f"  个人行程与报销 Skill 部署工具")
    print(f"{'='*50}")
    print(f"  源码版本:   {source_v}")
    print(f"  已部署版本: {deployed_v or '未部署'}")
    print(f"{'='*50}")

    # 版本对比
    if not force and deployed_v is not None:
        cmp = compare_version(deployed_v, source_v)
        if cmp >= 0:
            print(f"\n  已是最新版本，无需部署")
            return True, "已是最新版本"

    # 创建备份
    if deployed_v is not None and os.path.exists(DEPLOY_TARGET):
        backup_dir, msg = create_backup()
        print(f"  备份: {msg}")
    else:
        print(f"  首次部署，无需备份")

    # 创建目录
    os.makedirs(DEPLOY_TARGET, exist_ok=True)
    os.makedirs(DEPLOY_SCRIPTS, exist_ok=True)

    # 复制脚本文件
    updated = []
    failed = []

    for fname in SCRIPT_FILES:
        src = os.path.join(PROJECT_SCRIPTS, fname)
        dst = os.path.join(DEPLOY_SCRIPTS, fname)

        if not os.path.exists(src):
            # deploy.py 自身可能不在源码中（首次运行）
            if fname == "deploy.py":
                continue
            failed.append(f"{fname} (源文件不存在)")
            continue

        try:
            shutil.copy2(src, dst)
            updated.append(fname)
        except Exception as e:
            failed.append(f"{fname}: {e}")

    # 复制顶层文件
    for fname in TOP_LEVEL_FILES:
        src = os.path.join(PROJECT_ROOT, fname)
        dst = os.path.join(DEPLOY_TARGET, fname)

        if not os.path.exists(src):
            failed.append(f"{fname} (源文件不存在)")
            continue

        try:
            shutil.copy2(src, dst)
            updated.append(fname)
        except Exception as e:
            failed.append(f"{fname}: {e}")

    # 确保不覆盖用户 config.py
    config_dst = os.path.join(DEPLOY_SCRIPTS, "config.py")
    config_template_src = os.path.join(PROJECT_SCRIPTS, "config_template.py")
    if not os.path.exists(config_dst) and os.path.exists(config_template_src):
        # 首次安装：从模板创建 config.py
        shutil.copy2(config_template_src, config_dst)
        updated.append("config.py (从模板创建)")

    # 输出结果
    print(f"\n  部署完成:")
    print(f"  - 已更新 {len(updated)} 个文件")
    for f in updated:
        print(f"    > {f}")

    if failed:
        print(f"\n  - 失败 {len(failed)} 个:")
        for f in failed:
            print(f"    ! {f}")

    print(f"\n  部署路径: {DEPLOY_TARGET}")
    print(f"  当前版本: {source_v}")
    print(f"  用户数据: config.py / 发票 / 行程 / 台账 (未受影响)")
    print(f"{'='*50}\n")

    if failed and not updated:
        return False, f"部署失败: {', '.join(failed[:3])}"
    elif failed:
        return True, f"部署成功（部分失败）: {', '.join(failed[:3])}"
    else:
        return True, f"部署成功: {len(updated)} 个文件"


def show_status():
    """显示版本状态"""
    source_v = get_source_version()
    deployed_v = get_deployed_version()

    print(f"\n  个人行程与报销 Skill 版本状态")
    print(f"  {'='*40}")
    print(f"  源码版本:   {source_v}")
    print(f"  已部署版本: {deployed_v or '未部署'}")

    if deployed_v is None:
        print(f"  状态: 未部署")
    else:
        cmp = compare_version(deployed_v, source_v)
        if cmp < 0:
            print(f"  状态: 需要更新 ({deployed_v} -> {source_v})")
        elif cmp > 0:
            print(f"  状态: 已部署版本高于源码（异常）")
        else:
            print(f"  状态: 已是最新")

    print(f"  项目路径:   {PROJECT_ROOT}")
    print(f"  部署路径:   {DEPLOY_TARGET}")
    print(f"  仓库地址:   {GITHUB_REPO}")
    print(f"  {'='*40}\n")


def backup_only():
    """仅创建备份"""
    backup_dir, msg = create_backup()
    if backup_dir:
        print(f"  备份完成: {msg}")
    else:
        print(f"  {msg}")


# ============================================================
# 远程升级功能（从 GitHub 拉取）
# ============================================================

def _run_git(args, cwd=None):
    """执行 git 命令，返回 (returncode, stdout, stderr)"""
    import subprocess
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", "git 命令未找到，请先安装 git"
    except subprocess.TimeoutExpired:
        return -1, "", "git 命令超时"


def check_remote_update():
    """检查 GitHub 远程仓库是否有新版本可用

    策略：同时尝试 tag 和 VERSION 文件，取最大值。
    避免「代码已推送但忘打 tag」时检查不到更新。
    """
    deployed_v = get_deployed_version()

    print(f"\n  检查远程更新...")
    print(f"  已部署版本: {deployed_v or '未部署'}")
    print(f"  仓库地址:   {GITHUB_REPO}")
    print(f"  {'='*40}")

    tag_version = None    # 从 git tag 获取的版本
    file_version = None   # 从 VERSION 文件获取的版本

    # 方法1：尝试通过 git ls-remote 获取最新 tag
    rc, stdout, stderr = _run_git(["ls-remote", "--tags", "--sort=-v:refname", GITHUB_REPO])
    if rc == 0 and stdout:
        for line in stdout.split('\n'):
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                ref = parts[1]
                tag_name = ref.replace('refs/tags/', '').lstrip('vV')
                try:
                    parse_version(tag_name)
                    if not tag_version or compare_version(tag_name, tag_version) > 0:
                        tag_version = tag_name
                except Exception:
                    continue

    # 方法2（备用）：通过 GitHub API 获取 tags
    if not tag_version:
        api_url = GITHUB_REPO.replace('.git', '') + '/tags?per_page=10'
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "deploy-py/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                tags_data = json.loads(resp.read().decode('utf-8'))
                for tag_info in tags_data:
                    tag_name = tag_info.get("name", "").lstrip('vV')
                    try:
                        parse_version(tag_name)
                        if not tag_version or compare_version(tag_name, tag_version) > 0:
                            tag_version = tag_name
                    except Exception:
                        continue
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"  API 返回 404: 仓库不存在或为私有")
            elif e.code == 403:
                print(f"  API 速率限制或认证问题")
            else:
                print(f"  API 错误: HTTP {e.code}")
        except Exception as e:
            print(f"  API 请求失败: {e}")

    # 方法3：直接读取仓库中的 VERSION 文件（raw.githubusercontent.com）
    # 始终执行，不依赖 tag 是否获取成功
    raw_url = "https://raw.githubusercontent.com/linson1786-cmd/nobusy-invoice-trip-organizer/main/scripts/invoice-trip-organizer/VERSION"
    try:
        req = urllib.request.Request(raw_url, headers={"User-Agent": "deploy-py/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            version_content = resp.read().decode('utf-8').strip()
            parse_version(version_content)
            file_version = version_content
    except Exception as e:
        print(f"  读取远程 VERSION 失败: {e}")

    # 取 tag 和 VERSION 文件中的最大值
    latest_remote = None
    if tag_version and file_version:
        latest_remote = tag_version if compare_version(tag_version, file_version) >= 0 else file_version
        if compare_version(file_version, tag_version) > 0:
            print(f"  注意: VERSION 文件({file_version}) 比 最新tag({tag_version}) 新，以 VERSION 文件为准")
    elif tag_version:
        latest_remote = tag_version
    elif file_version:
        latest_remote = file_version

    # 输出结果
    if latest_remote:
        print(f"  最新远程版本: {latest_remote}")

        if deployed_v is None:
            print(f"  状态: 尚未部署，可安装 {latest_remote}")
            return True, f"可安装: {latest_remote}", latest_remote

        cmp = compare_version(deployed_v, latest_remote)
        if cmp < 0:
            print(f"  状态: 有新版本可用! ({deployed_v} -> {latest_remote})")
            return True, f"有新版本: {deployed_v} -> {latest_remote}", latest_remote
        elif cmp > 0:
            print(f"  状态: 本地版本高于远程（可能是开发版）")
            return False, "本地已是最新(开发版)", None
        else:
            print(f"  状态: 已是最新版本")
            return False, "已是最新版本", None

    print(f"  无法获取远程版本信息（请检查网络连接和仓库权限）")
    return False, "无法获取远程版本信息", None


def _do_deploy_from(source_root, source_scripts_dir, target_label=""):
    """
    从指定源目录部署文件到 DEPLOY_TARGET 的内部实现。
    source_root: SKILL.md 所在的根目录
    source_scripts_dir: 脚本文件所在的目录（含 VERSION, *.py 等）
    target_label: 日志中显示的来源标识
    """
    # 读取新版本号
    src_ver_file = os.path.join(source_scripts_dir, "VERSION")
    new_version = "unknown"
    if os.path.exists(src_ver_file):
        with open(src_ver_file, 'r', encoding='utf-8') as f:
            new_version = f.read().strip()

    # 备份
    deployed_v = get_deployed_version()
    if deployed_v and os.path.exists(DEPLOY_TARGET):
        backup_dir, backup_msg = create_backup()
        print(f"  备份: {backup_msg}")
    else:
        print(f"  首次安装，无需备份")

    # 创建目录
    os.makedirs(DEPLOY_TARGET, exist_ok=True)
    os.makedirs(DEPLOY_SCRIPTS, exist_ok=True)

    # 复制脚本文件
    updated = []
    failed = []

    for fname in SCRIPT_FILES:
        src = os.path.join(source_scripts_dir, fname)
        dst = os.path.join(DEPLOY_SCRIPTS, fname)

        if not os.path.exists(src):
            if fname == "deploy.py":
                # deploy.py 可能在升级场景中不存在于远程
                continue
            failed.append(f"{fname} (源文件不存在)")
            continue

        try:
            shutil.copy2(src, dst)
            updated.append(fname)
        except Exception as e:
            failed.append(f"{fname}: {e}")

    # 复制顶层文件
    for fname in TOP_LEVEL_FILES:
        src = os.path.join(source_root, fname)
        dst = os.path.join(DEPLOY_TARGET, fname)

        if not os.path.exists(src):
            failed.append(f"{fname} (源文件不存在)")
            continue

        try:
            shutil.copy2(src, dst)
            updated.append(fname)
        except Exception as e:
            failed.append(f"{fname}: {e}")

    # 保护用户 config.py：如果部署目录没有 config.py 但源码有 config_template.py，从模板创建
    config_dst = os.path.join(DEPLOY_SCRIPTS, "config.py")
    config_template_src = os.path.join(source_scripts_dir, "config_template.py")
    if not os.path.exists(config_dst) and os.path.exists(config_template_src):
        shutil.copy2(config_template_src, config_dst)
        updated.append("config.py (从模板创建)")

    # 输出结果
    action = f"升级({target_label})" if target_label else "部署"
    print(f"\n  {action}完成:")
    print(f"  - 已更新 {len(updated)} 个文件")
    for f in updated:
        print(f"    > {f}")

    if failed:
        print(f"\n  - 失败 {len(failed)} 个:")
        for f in failed:
            print(f"    ! {f}")

    print(f"\n  部署路径: {DEPLOY_TARGET}")
    print(f"  当前版本: {new_version}")
    print(f"  用户数据: config.py / 发票 / 行程 / 台账 (未受影响)")
    print(f"{'='*50}\n")

    old_ver = deployed_v or "未安装"

    if failed and not updated:
        return False, f"{action}失败: {', '.join(failed[:3])}"
    elif failed:
        return True, f"{action}成功（部分失败）: {', '.join(failed[:3])}"
    else:
        return True, f"{action}完成: {old_ver} -> {new_version}"


def upgrade(force=False):
    """从 GitHub 自动拉取最新版本并部署"""
    print(f"\n{'='*50}")
    print(f"  个人行程与报销 Skill - 在线升级")
    print(f"{'='*50}")

    # 第一步：检查远程是否有新版本
    has_update, update_msg, remote_version = check_remote_update()

    if not has_update and not force:
        print(f"\n  无需更新: {update_msg}")
        return True, update_msg

    if force and not remote_version:
        print(f"\n  强制模式：但无法确定远程版本")
        return False, "强制升级失败：无法获取远程版本"

    # 第二步：确认目标版本
    target_version = remote_version if remote_version else "latest"
    print(f"\n  目标版本: {target_version}")

    # 第三步：创建临时目录，克隆仓库
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="invoice_upgrade_")
    print(f"  下载中... (临时目录: {tmp_dir})")

    try:
        # 克隆仓库（浅克隆，只取最新）
        rc, stdout, stderr = _run_git(
            ["clone", "--depth", "1", GITHUB_REPO, tmp_dir]
        )
        clone_ok = (rc == 0)

        # git 失败时，尝试用 HTTP 下载 zip
        if not clone_ok:
            print(f"  git 克隆失败: {stderr}")
            print(f"  尝试通过 HTTP 下载 ZIP...")
            zip_url = GITHUB_REPO.replace('.git', '') + '/archive/refs/heads/main.zip'
            try:
                req = urllib.request.Request(zip_url, headers={"User-Agent": "deploy-py/1.0"})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    zip_data = resp.read()
                zip_path = os.path.join(tmp_dir, "repo.zip")
                import zipfile

                with open(zip_path, 'wb') as zf:
                    zf.write(zip_data)

                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(tmp_dir)

                # zip 解压后通常有一个根子目录（如 repo-main），找出来
                extracted_items = [d for d in os.listdir(tmp_dir) if d != "repo.zip"]
                if len(extracted_items) == 1:
                    actual_root = os.path.join(tmp_dir, extracted_items[0])
                    if os.path.isdir(actual_root) and os.path.exists(os.path.join(actual_root, "SKILL.md")):
                        # 把内容移到 tmp_dir 根
                        for item in os.listdir(actual_root):
                            shutil.move(os.path.join(actual_root, item), tmp_dir)
                        shutil.rmtree(actual_root)
                        clone_ok = True
                        print(f"  ZIP 下载成功")
            except Exception as e:
                print(f"  ZIP 下载也失败: {e}")

        if not clone_ok:
            return False, "无法从 GitHub 获取代码（git 和 HTTP 均失败）"

        print(f"  下载成功")

        # 第四步：定位源文件目录
        source_scripts_dir = os.path.join(tmp_dir, REPO_SCRIPTS_PATH)
        source_root = tmp_dir

        if not os.path.exists(os.path.join(source_scripts_dir, "VERSION")):
            print(f"  错误: 找不到脚本目录: {source_scripts_dir}")
            return False, "找不到有效的脚本文件"

        if not os.path.exists(os.path.join(source_root, "SKILL.md")):
            print(f"  错误: 找不到 SKILL.md")
            return False, "找不到 SKILL.md"

        print(f"  源目录: {source_scripts_dir}")

        # 第五步：执行部署
        return _do_deploy_from(source_root, source_scripts_dir, target_label=target_version)

    finally:
        # 清理临时目录
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="个人行程与报销 Skill 部署工具",
        epilog=(
            "示例:\n"
            "  python3 deploy.py                 # 从本地源码检查并部署\n"
            "  python3 deploy.py --upgrade        # 从 GitHub 升级到最新版\n"
            "  python3 deploy.py --check-update   # 检查是否有新版本\n"
            "  python3 deploy.py --status         # 查看版本状态\n"
            "  python3 deploy.py --force          # 强制重新部署\n"
            "  python3 deploy.py --backup         # 仅创建备份\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--force", action="store_true", help="强制重新部署（忽略版本对比）")
    parser.add_argument("--status", action="store_true", help="仅查看版本状态，不执行部署")
    parser.add_argument("--backup", action="store_true", help="仅创建备份，不更新")
    parser.add_argument("--upgrade", action="store_true", help="从 GitHub 拉取最新版本并自动部署")
    parser.add_argument("--check-update", action="store_true", help="检查远程仓库是否有新版本可用")

    args = parser.parse_args()

    if args.upgrade:
        success, msg = upgrade(force=args.force)
        if not success:
            sys.exit(1)
    elif args.check_update:
        check_remote_update()
    elif args.status:
        show_status()
    elif args.backup:
        backup_only()
    else:
        success, msg = deploy(force=args.force)
        if not success:
            sys.exit(1)
