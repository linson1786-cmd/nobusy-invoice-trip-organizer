#!/usr/bin/env python3
"""
个人行程与报销 - 初始化脚本
首次使用时运行: python3 init.py

功能:
1. 检查 config.py 是否存在，不存在则从 config_template.py 复制
2. 根据 config.py 中的路径创建目录结构
3. 检查 Python 依赖是否已安装
4. 打印配置摘要
"""

import os
import sys

# 获取当前脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def check_config():
    """检查 config.py 是否存在"""
    config_path = os.path.join(SCRIPT_DIR, "config.py")
    template_path = os.path.join(SCRIPT_DIR, "config_template.py")

    if not os.path.exists(config_path):
        if os.path.exists(template_path):
            print("⚠️ 未找到 config.py")
            ans = input("   是否从 config_template.py 复制为 config.py？(y/n) ")
            if ans.strip().lower() == 'y':
                import shutil
                shutil.copy2(template_path, config_path)
                print(f"✅ 已创建 config.py，请编辑后重新运行 init.py")
                print(f"   需修改: EMAIL_ADDRESS, EMAIL_AUTH_CODE, OBSIDIAN_VAULT")
                return False
            else:
                print("   请手动复制 config_template.py → config.py 并填写配置")
                return False
        else:
            print("❌ 未找到 config_template.py，无法创建 config.py")
            return False
    else:
        print(f"✅ config.py 已存在")
        return True


def load_config():
    """加载 config.py"""
    config_path = os.path.join(SCRIPT_DIR, "config.py")
    if not os.path.exists(config_path):
        return None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("config", config_path)
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        return config
    except Exception as e:
        print(f"❌ 读取 config.py 失败: {e}")
        return None


def create_dirs(config):
    """根据配置创建目录结构"""
    print("\n📁 创建目录结构...")

    # 发票整理目录
    invoice_root = getattr(config, 'INVOICE_ROOT', None)
    if not invoice_root:
        print("   ❌ config.py 中未找到 INVOICE_ROOT")
        return False

    dirs_to_create = [
        invoice_root,
        os.path.join(invoice_root, "01 待分类"),
        os.path.join(invoice_root, "02 待核实"),
        os.path.join(invoice_root, "03 已完成"),
    ]

    # 行程目录
    trip_root = getattr(config, 'TRIP_ROOT', None)
    if trip_root:
        dirs_to_create.append(trip_root)
        # 创建 2026 年 (示例)
        for year in ['2026']:
            year_dir = os.path.join(trip_root, f"{year} 年")
            dirs_to_create.append(year_dir)
            for month in range(1, 13):
                dirs_to_create.append(os.path.join(year_dir, f"{month} 月"))

    created = 0
    for d in dirs_to_create:
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
            print(f"   ✅ 创建: {d}")
            created += 1
        else:
            print(f"   ⏩ 已存在: {d}")

    print(f"\n   共创建 {created} 个新目录")
    return True


def check_dependencies():
    """检查 Python 依赖"""
    print("\n📦 检查 Python 依赖...")
    deps = [
        ("pdfminer.six", "pdfminer.six"),
        ("fitz (PyMuPDF)", "pymupdf"),
        ("fpdf2", "fpdf"),
        ("Pillow", "PIL"),
        ("pytesseract", "pytesseract"),
    ]

    missing = []
    for name, pip_name in deps:
        try:
            if name == "fitz (PyMuPDF)":
                import fitz
            elif name == "pdfminer.six":
                from pdfminer.high_level import extract_text
            else:
                __import__(pip_name)
            print(f"   ✅ {name}")
        except ImportError:
            print(f"   ❌ {name} (pip install {pip_name})")
            missing.append(pip_name)

    if missing:
        print(f"\n⚠️ 缺少依赖，请运行:")
        print(f"   pip install {' '.join(missing)}")
        return False
    else:
        print(f"\n✅ 所有依赖已安装")
        return True


def print_summary(config):
    """打印配置摘要"""
    print("\n📋 配置摘要:")
    print(f"   Obsidian Vault: {getattr(config, 'OBSIDIAN_VAULT', 'N/A')}")
    print(f"   发票根目录:   {getattr(config, 'INVOICE_ROOT', 'N/A')}")
    print(f"   行程根目录:   {getattr(config, 'TRIP_ROOT', 'N/A')}")
    print(f"   邮箱地址:     {getattr(config, 'EMAIL_ADDRESS', 'N/A')}")
    template = getattr(config, 'REIMBURSEMENT_TEMPLATE', '')
    print(f"   报销单模板:   {'已配置' if template else '未配置 (不影响核心功能)'}")


def main():
    print("="*50)
    print("个人行程与报销 - 初始化")
    print("="*50)

    # 0. 版本检查（自动更新）
    config_path = os.path.join(SCRIPT_DIR, "config.py")
    if os.path.exists(config_path):
        try:
            import importlib.util
            vm_spec = importlib.util.spec_from_file_location("version_manager", os.path.join(SCRIPT_DIR, "version_manager.py"))
            if vm_spec:
                vm = importlib.util.module_from_spec(vm_spec)
                vm_spec.loader.exec_module(vm)
                need_update, msg = vm.check_and_update(config_path, auto=True, silent=False)
                if need_update:
                    print(f"\n📦 版本更新: {msg}\n")
        except Exception:
            pass

    # 1. 检查 config.py
    if not check_config():
        sys.exit(1)

    # 2. 加载配置
    config = load_config()
    if not config:
        sys.exit(1)

    # 3. 创建目录
    if not create_dirs(config):
        sys.exit(1)

    # 4. 检查依赖
    check_dependencies()

    # 5. 打印摘要
    print_summary(config)

    print("\n" + "="*50)
    print("✅ 初始化完成!")
    print("\n下一步:")
    print("  1. 编辑 config.py，填写你的邮箱和路径")
    print("  2. 把发票文件放入 01 待分类/ 目录")
    print("  3. 运行: python3 invoice_auto_organizer.py")
    print("="*50)


if __name__ == "__main__":
    main()
