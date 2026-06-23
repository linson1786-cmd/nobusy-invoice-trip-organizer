#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill 发布前检查。

默认执行本地离线检查，不访问邮箱、OA、真实发票或 GitHub。
用法：
  python3 release_check.py
  python3 release_check.py --allow-dirty
"""

from __future__ import annotations

import argparse
import hashlib
import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
VERSION_FILE = SCRIPT_DIR / "VERSION"
CODEX_SKILL_DIR = Path.home() / ".codex" / "skills" / "invoice-trip-organizer"
WORKBUDDY_SKILL_DIR = Path.home() / ".workbuddy" / "skills" / "invoice-trip-organizer"
CODEX_SOURCE_SKILL = PROJECT_ROOT / "codex" / "SKILL.md"


FORBIDDEN_TRACKED_SUFFIXES = {
    ".pdf",
    ".ofd",
    ".xlsx",
    ".xls",
    ".csv",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
}

FORBIDDEN_TRACKED_NAMES = {
    "config.py",
    ".env",
    ".DS_Store",
}

FORBIDDEN_TEXT_PATTERNS = [
    "NoBusy-Demo",
    "Co_Operation",
    "郭茂林",
]


def run(cmd: list[str], cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)


def ok(message: str) -> None:
    print(f"✅ {message}")


def fail(message: str) -> None:
    print(f"❌ {message}")


def warn(message: str) -> None:
    print(f"⚠️ {message}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_version() -> bool:
    passed = True
    version = read(VERSION_FILE).strip()
    expected = version
    checks = {
        "SKILL.md": PROJECT_ROOT / "SKILL.md",
        "README.md": PROJECT_ROOT / "README.md",
        "CHANGELOG.md": PROJECT_ROOT / "CHANGELOG.md",
        "codex/SKILL.md": CODEX_SOURCE_SKILL,
        "scripts/invoice-trip-organizer/CHANGELOG.md": SCRIPT_DIR / "CHANGELOG.md",
    }
    for label, path in checks.items():
        if not path.exists():
            fail(f"缺少文件：{label}")
            passed = False
            continue
        text = read(path).strip()
        if path.name == "VERSION":
            if text != version:
                fail(f"{label} 版本不一致：{text} != {version}")
                passed = False
        elif expected not in text:
            fail(f"{label} 未包含当前版本 {expected}")
            passed = False
    if passed:
        ok(f"版本一致：{version}")
    return passed


def check_python_compile() -> bool:
    passed = True
    for path in sorted(SCRIPT_DIR.glob("*.py")):
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            fail(f"Python 编译失败：{path.name}: {exc.msg}")
            passed = False
    if passed:
        ok("Python 脚本编译通过")
    return passed


def check_tracked_files() -> bool:
    result = run(["git", "ls-files"])
    if result.returncode != 0:
        fail("无法读取 Git 跟踪文件")
        return False

    passed = True
    for raw in result.stdout.splitlines():
        path = Path(raw)
        if path.name in FORBIDDEN_TRACKED_NAMES:
            fail(f"禁止跟踪文件：{raw}")
            passed = False
        if len(path.parts) == 2 and path.parts[0] == "scripts":
            fail(f"根层 scripts 旧副本不得发布：{raw}")
            passed = False
        if path.suffix.lower() in FORBIDDEN_TRACKED_SUFFIXES:
            fail(f"禁止跟踪数据/归档文件：{raw}")
            passed = False
        if "项目记忆" in path.parts:
            fail(f"内部项目记忆不得发布：{raw}")
            passed = False
    if passed:
        ok("Git 跟踪文件无敏感配置、数据文件或归档包")
    return passed


def check_required_resources() -> bool:
    required = [
        PROJECT_ROOT / "docs" / "SOP-发票文件命名标准.md",
        CODEX_SOURCE_SKILL,
    ]
    passed = True
    for path in required:
        if not path.exists():
            fail(f"缺少初始化所需资源：{path.relative_to(PROJECT_ROOT)}")
            passed = False
    if passed:
        ok("初始化所需资源存在")
    return passed


def check_forbidden_text() -> bool:
    passed = True
    targets = [
        PROJECT_ROOT / "SKILL.md",
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "SECURITY.md",
        SCRIPT_DIR / "invoice_auto_organizer.py",
        SCRIPT_DIR / "trip_auto_organizer.py",
        SCRIPT_DIR / "config_template.py",
        SCRIPT_DIR / "setup.py",
    ]
    for path in targets:
        text = read(path)
        for pattern in FORBIDDEN_TEXT_PATTERNS:
            if pattern in text:
                fail(f"{path.relative_to(PROJECT_ROOT)} 含禁止发布文本：{pattern}")
                passed = False
    if passed:
        ok("发布文本未发现本机 demo、公司路径或旧姓名")
    return passed


def check_install_versions() -> bool:
    version = read(VERSION_FILE).strip()
    passed = True

    workbuddy_version_file = WORKBUDDY_SKILL_DIR / "scripts" / "VERSION"
    if workbuddy_version_file.exists():
        installed = read(workbuddy_version_file).strip()
        if installed != version:
            fail(f"WorkBuddy 安装版本不一致：{installed} != {version}")
            passed = False
        else:
            ok(f"WorkBuddy 安装版本一致：{installed}")
    else:
        warn("未发现 WorkBuddy 安装版本文件，跳过")

    codex_skill_file = CODEX_SKILL_DIR / "SKILL.md"
    if codex_skill_file.exists():
        text = read(codex_skill_file)
        if version not in text:
            fail(f"Codex Skill 未包含当前版本：{version}")
            passed = False
        else:
            ok("Codex Skill 版本引用一致")
    else:
        warn("未发现 Codex Skill 安装目录，跳过")

    return passed


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_workbuddy_script_sync() -> bool:
    deployed_scripts = WORKBUDDY_SKILL_DIR / "scripts"
    if not deployed_scripts.exists():
        warn("未发现 WorkBuddy scripts 目录，跳过源码/安装一致性检查")
        return True

    passed = True
    for source in sorted(SCRIPT_DIR.glob("*")):
        if source.name == "config.py" or source.is_dir():
            continue
        target = deployed_scripts / source.name
        if not target.exists():
            fail(f"WorkBuddy 安装目录缺少脚本：{source.name}")
            passed = False
            continue
        if sha256(source) != sha256(target):
            fail(f"WorkBuddy 安装脚本与源码不一致：{source.name}")
            passed = False
    if passed:
        ok("WorkBuddy 安装脚本与源码一致")
    return passed


def check_stdin_trip_import() -> bool:
    demo_root = Path("/private/tmp/invoice-trip-release-stdin-check")
    if demo_root.exists():
        shutil.rmtree(demo_root)

    init_result = run([
        "python3",
        str(SCRIPT_DIR / "setup.py"),
        "init",
        "--base-dir",
        str(demo_root),
    ])
    if init_result.returncode != 0:
        fail("stdin 验证前初始化失败")
        print(init_result.stdout.strip())
        print(init_result.stderr.strip())
        return False

    workspace_scripts = demo_root / "个人行程与报销" / "scripts"
    input_text = "开始日期\t结束日期\t行程\n2026-01-04\t2026-01-06\t广州-上海-广州\n"
    result = subprocess.run(
        ["python3", "import_trips.py"],
        cwd=str(workspace_scripts),
        input=input_text,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        fail("stdin 管道导入执行失败")
        print(result.stdout.strip())
        print(result.stderr.strip())
        return False
    if "✅ 从管道接收到行程数据" not in result.stdout or "导入完成: 新增 1 条" not in result.stdout:
        fail("stdin 管道导入输出不符合预期")
        print(result.stdout.strip())
        print(result.stderr.strip())
        return False
    ok("stdin 管道导入端到端验证通过")
    return True


def check_trigger_stdin_ignored() -> bool:
    """确认 WorkBuddy 触发词不会被误判为有效 stdin 行程数据。"""
    code = (
        "import importlib.util;"
        f"spec=importlib.util.spec_from_file_location('it', {str(SCRIPT_DIR / 'import_trips.py')!r});"
        "m=importlib.util.module_from_spec(spec);"
        "spec.loader.exec_module(m);"
        "raise SystemExit(0 if (not m.is_valid_trip_input('新增行程') and m.is_valid_trip_input('开始日期\\t结束日期\\t行程\\n2026-01-04\\t2026-01-06\\t广州-上海-广州\\n')) else 1)"
    )
    result = subprocess.run(["python3", "-c", code], text=True, capture_output=True)
    if result.returncode == 0:
        ok("触发词 stdin 会被忽略，有效行程 stdin 会被接收")
        return True
    fail("触发词 stdin 判定逻辑异常")
    print(result.stdout.strip())
    print(result.stderr.strip())
    return False


def check_codex_validate() -> bool:
    validator = Path.home() / ".codex" / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"
    if not validator.exists() or not CODEX_SKILL_DIR.exists():
        warn("Codex quick_validate 不可用，跳过")
        return True
    result = run(["python3", str(validator), str(CODEX_SKILL_DIR)])
    if result.returncode == 0:
        ok("Codex quick_validate 通过")
        return True
    fail("Codex quick_validate 未通过")
    print(result.stdout.strip())
    print(result.stderr.strip())
    return False


def check_git_clean(allow_dirty: bool) -> bool:
    result = run(["git", "status", "--porcelain"])
    if result.returncode != 0:
        fail("无法读取 Git 状态")
        return False
    if result.stdout.strip():
        if allow_dirty:
            warn("工作区有未提交变更，本次按 --allow-dirty 放行")
            return True
        fail("工作区有未提交变更；正式发布前必须提交或清理")
        print(result.stdout.strip())
        return False
    ok("Git 工作区干净")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="invoice-trip-organizer 发布检查")
    parser.add_argument("--allow-dirty", action="store_true", help="允许工作区存在未提交变更")
    args = parser.parse_args()

    checks = [
        check_version(),
        check_python_compile(),
        check_tracked_files(),
        check_required_resources(),
        check_forbidden_text(),
        check_install_versions(),
        check_workbuddy_script_sync(),
        check_codex_validate(),
        check_trigger_stdin_ignored(),
        check_stdin_trip_import(),
        check_git_clean(args.allow_dirty),
    ]
    if all(checks):
        print("\n✅ 发布检查通过")
        return 0
    print("\n❌ 发布检查未通过")
    return 1


if __name__ == "__main__":
    sys.exit(main())
