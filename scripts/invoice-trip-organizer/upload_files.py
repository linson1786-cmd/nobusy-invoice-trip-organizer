#!/usr/bin/env python3
"""
上传文件到 01 待分类 目录
弹出文件选择窗口，选择文件后自动复制到 01 待分类/
"""
import os
import sys
import shutil
import subprocess
import platform
import importlib.util

# ===== 加载配置 =====
_script_dir = os.path.dirname(os.path.abspath(__file__))


def load_config():
    """加载 config.py（不存在则用 config_template.py）"""
    config_path = os.path.join(_script_dir, 'config.py')
    if not os.path.exists(config_path):
        config_path = os.path.join(_script_dir, 'config_template.py')
    spec = importlib.util.spec_from_file_location('config', config_path)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    return config


def get_target_dir(config):
    """获取 01 待分类 目录路径"""
    vault = os.path.expanduser(config.OBSIDIAN_VAULT)
    invoice_base = os.path.join(vault, config.INVOICE_BASE_REL)
    target = os.path.join(invoice_base, '01 待分类')
    return target


def pick_files_macos():
    """macOS: 使用 osascript 弹出原生文件选择窗口（支持多选）"""
    script = '''
    set theFiles to choose file of type {"public.item"} with multiple selections allowed with prompt "选择要上传的发票/附件文件"
    set output to ""
    repeat with f in theFiles
        set output to output & (POSIX path of f) & linefeed
    end repeat
    return output
    '''
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            if 'cancel' in (result.stderr or '').lower():
                print('用户取消了选择')
                return []
            # osascript 失败，回退到 tkinter
            return pick_files_tkinter()

        files = [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
        return files
    except subprocess.TimeoutExpired:
        print('选择超时')
        return []
    except FileNotFoundError:
        return pick_files_tkinter()


def pick_files_tkinter():
    """跨平台回退: 使用 tkinter 文件选择窗口"""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print('错误: 无法加载文件选择器。')
        print('  macOS: brew install python-tk')
        print('  Ubuntu: sudo apt install python3-tk')
        return []

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    files = filedialog.askopenfilenames(
        title='选择要上传的发票/附件文件',
        parent=root
    )

    root.destroy()
    return list(files) if files else []


def pick_files():
    """根据平台选择文件选择器"""
    system = platform.system()
    if system == 'Darwin':
        return pick_files_macos()
    else:
        return pick_files_tkinter()


def copy_files(files, target_dir):
    """复制文件到目标目录，自动处理重名"""
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)

    success = []
    failed = []

    for src in files:
        if not os.path.isfile(src):
            continue

        filename = os.path.basename(src)
        dst = os.path.join(target_dir, filename)

        # 处理重名: 追加 _1, _2, ...
        if os.path.exists(dst):
            name, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(dst):
                dst = os.path.join(target_dir, f'{name}_{counter}{ext}')
                counter += 1

        try:
            shutil.copy2(src, dst)
            success.append((src, dst))
        except Exception as e:
            failed.append((src, str(e)))

    return success, failed


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

    config = load_config()
    target_dir = get_target_dir(config)

    print('=' * 50)
    print('上传文件到 01 待分类')
    print(f'目标目录: {target_dir}')
    print('=' * 50)
    print()
    print('正在打开文件选择窗口...')

    files = pick_files()

    if not files:
        print('未选择任何文件')
        return

    print(f'已选择 {len(files)} 个文件:')
    for f in files:
        print(f'  - {os.path.basename(f)}')
    print()

    success, failed = copy_files(files, target_dir)

    print(f'上传完成: 成功 {len(success)} 个' +
          (f', 失败 {len(failed)} 个' if failed else ''))

    if success:
        print(f'\n文件已复制到: {target_dir}')

    if failed:
        print('\n失败文件:')
        for src, err in failed:
            print(f'  X {os.path.basename(src)}: {err}')

    if success:
        print('\n提示: 运行 invoice_auto_organizer.py 可自动整理发票')


if __name__ == '__main__':
    main()
