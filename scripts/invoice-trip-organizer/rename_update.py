#!/usr/bin/env python3
"""
批量更新文件名 - 升级后数据迁移工具

功能:
  1. 扫描 03 已完成/ 所有文件
  2. 用最新 CATEGORY_RULES 重新识别类别，若与文件名中类别不同则更新
  3. 从文件内容提取购买方名称 → 生成简称，若无则追加
  4. 同步更新行程目录(02 行程与员工报销单/)中的副本
  5. 支持 --dry-run 预览模式（只显示变更，不实际重命名）
  6. 支持 --check 检测模式（静默检测，输出 JSON，供升级流程调用）
  7. 迁移完成后自动更新 config.py 的 LAST_MIGRATION_VERSION

使用场景:
  - 升级到含新分类规则的版本后，重新识别已有文件分类
  - 升级到含购买方简称命名规则的版本后，批量更新历史文件
  - 升级流程（deploy.py / version_manager.py）自动调用检测

用法:
  python3 rename_update.py --dry-run     # 预览变更
  python3 rename_update.py               # 执行重命名
  python3 rename_update.py --check       # 静默检测，输出 JSON
"""

import os, re, sys, shutil, json
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from invoice_auto_organizer import (
    extract_pdf_text, extract_buyer_name_from_text, shorten_company_name,
    classify_with_subtype, _extract_text_for_existing_invoice,
    STANDARD_NAME_RE, VALID_CATEGORIES, MAJOR_CITIES,
    DONE_DIR, TRIP_ROOT
)


def parse_route_and_buyer(group4):
    """从正则 group(4) 中分离路线和购买方简称

    group(4) 格式: route_start[-route_end][_buyer_short]
    例:
      "广州-上海_乐纯生物" → ("广州-上海", "乐纯生物")
      "广州-上海"          → ("广州-上海", None)
      "乐纯生物"           → (None, "乐纯生物")  # 无路线时纯购买方
      None                → (None, None)
    """
    if not group4:
        return None, None

    # 尝试匹配 route[-route][_buyer] 结构
    m = re.match(
        r'^([^-_]+(?:-[^-_]+)?)(?:_([\u4e00-\u9fa5]{2,10}))?$', group4
    )
    if m:
        route_part = m.group(1) if m.group(1) else None
        buyer_part = m.group(2) if m.group(2) else None
        if route_part:
            if '-' in route_part:
                # 含"-"，是路线
                return route_part, buyer_part
            elif route_part in MAJOR_CITIES:
                # 是已知城市，是路线
                return route_part, buyer_part
            elif buyer_part:
                # route_part 不是路线但有 buyer_part，说明 route_part 是路线（非常规城市）
                return route_part, buyer_part
            else:
                # 没有 buyer_part，route_part 不含"-"且非已知城市
                # 更可能是购买方简称而非路线（如"乐纯生物"、"世成"）
                return None, route_part
        return None, buyer_part

    return group4, None


def build_new_filename(fn, new_cat=None, buyer_short=None):
    """构建更新后的文件名

    参数:
      fn          原文件名
      new_cat     新类别（如需重分类），None 表示不改变类别
      buyer_short 购买方简称（如需追加），None 表示不追加

    返回:
      新文件名，或 None（无需更新 / 无法解析）
    """
    m = STANDARD_NAME_RE.match(fn)
    if not m:
        return None

    date = m.group(1)
    cat = m.group(2)
    amount = m.group(3)
    group4 = m.group(4)  # route + optional buyer
    suffix = m.group(5)  # 发票号后4位
    op_date = m.group(6)  # MMDD
    status = m.group(7)  # WB/YB
    seq = m.group(8)     # NNN
    ext = m.group(9)

    # 确定最终类别
    final_cat = new_cat if new_cat else cat

    # 分离路线和已有购买方
    route, existing_buyer = parse_route_and_buyer(group4)

    # 确定最终购买方
    final_buyer = existing_buyer if existing_buyer else buyer_short

    # 构建中间部分: 路线 + 购买方
    middle_parts = []
    if route:
        middle_parts.append(route)
    if final_buyer:
        middle_parts.append(final_buyer)
    middle = '_'.join(middle_parts) if middle_parts else ''

    # 组装新文件名
    parts = [f"{date}_{final_cat}_{amount}"]
    if middle:
        parts.append(middle)
    if suffix:
        parts.append(suffix)
    if op_date and status:
        parts.append(f"{op_date}_{status}")
    if seq:
        parts.append(seq)

    new_fn = '_'.join(parts) + ext

    # 如果没有变化，返回 None
    if new_fn == fn:
        return None

    return new_fn


def find_trip_copies(old_filename, trip_root):
    """在行程目录中查找指定文件名的所有副本

    返回副本文件路径列表
    """
    copies = []
    if not os.path.isdir(trip_root):
        return copies

    for year_dir in os.listdir(trip_root):
        year_path = os.path.join(trip_root, year_dir)
        if not os.path.isdir(year_path):
            continue
        for month_dir in os.listdir(year_path):
            month_path = os.path.join(year_path, month_dir)
            if not os.path.isdir(month_path):
                continue
            for trip_folder in os.listdir(month_path):
                trip_path = os.path.join(month_path, trip_folder)
                if not os.path.isdir(trip_path):
                    continue
                invoice_dir = os.path.join(trip_path, "02-发票文件")
                if not os.path.isdir(invoice_dir):
                    continue
                for subdir in os.listdir(invoice_dir):
                    subdir_path = os.path.join(invoice_dir, subdir)
                    if not os.path.isdir(subdir_path):
                        continue
                    candidate = os.path.join(subdir_path, old_filename)
                    if os.path.exists(candidate):
                        copies.append(candidate)

    return copies


def scan_and_rename(dry_run=False, check=False):
    """扫描 03 已完成，重新识别类别 + 追加购买方简称，更新文件名

    参数:
      dry_run: 预览模式，不实际修改文件
      check: 检测模式，静默运行，不打印详细报告，返回 stats 供程序化调用
    """
    if not os.path.isdir(DONE_DIR):
        if not check:
            print(f"❌ 03 已完成目录不存在: {DONE_DIR}")
        return {'total': 0, 'renamed': 0, 'needs_migration': False}

    stats = {
        'total': 0,
        # 类别重分类
        'cat_changed': 0,
        'cat_kept': 0,
        'cat_skip_other': 0,  # 检测为"其他"但不降级
        # 购买方
        'buyer_added': 0,
        'buyer_already': 0,
        'buyer_none': 0,
        # 执行
        'renamed': 0,
        'parse_fail': 0,
        'trip_updated': 0,
    }
    cat_change_detail = {}  # {old_cat → {new_cat: count}}
    rename_log = []

    if not check:
        print(f"{'🔍 [预览模式]' if dry_run else '🔄 [执行模式]'} 升级数据迁移（类别重分类 + 购买方简称）")
        print(f"📁 扫描目录: {DONE_DIR}")
        print(f"{'='*60}\n")

    for month_dir_name in sorted(os.listdir(DONE_DIR)):
        month_dir = os.path.join(DONE_DIR, month_dir_name)
        if not os.path.isdir(month_dir) or month_dir_name.startswith('.'):
            continue

        for fn in sorted(os.listdir(month_dir)):
            if fn.startswith('.') or fn == '台账.md':
                continue

            fpath = os.path.join(month_dir, fn)
            ext = os.path.splitext(fn)[1].lower()
            stats['total'] += 1

            # 1. 匹配标准文件名
            m = STANDARD_NAME_RE.match(fn)
            if not m:
                stats['parse_fail'] += 1
                continue

            current_cat = m.group(2)
            group4 = m.group(4)
            _, existing_buyer = parse_route_and_buyer(group4)

            # 2. 提取文件文本
            text = _extract_text_for_existing_invoice(fpath) or ''

            # 3. 重新识别类别
            detected_cat = classify_with_subtype(text, fn)
            new_cat = None
            if detected_cat != current_cat:
                if detected_cat == "其他":
                    # 不降级：不从具体类别改为"其他"（可能是文本提取不完整）
                    stats['cat_skip_other'] += 1
                else:
                    new_cat = detected_cat
                    stats['cat_changed'] += 1
                    cat_change_detail.setdefault(current_cat, {})
                    cat_change_detail[current_cat][detected_cat] = \
                        cat_change_detail.get(current_cat, {}).get(detected_cat, 0) + 1
            else:
                stats['cat_kept'] += 1

            # 4. 提取购买方简称
            buyer_short = None
            if not existing_buyer:
                buyer_name = extract_buyer_name_from_text(text)
                if buyer_name:
                    buyer_short = shorten_company_name(buyer_name)
                    if buyer_short:
                        stats['buyer_added'] += 1
                if not buyer_short:
                    stats['buyer_none'] += 1
            else:
                stats['buyer_already'] += 1

            # 5. 构建新文件名
            new_fn = build_new_filename(fn, new_cat=new_cat, buyer_short=buyer_short)
            if not new_fn:
                continue

            new_fpath = os.path.join(month_dir, new_fn)

            # 检查目标文件是否已存在
            if os.path.exists(new_fpath):
                print(f"⚠️ 跳过(目标已存在): {fn} → {new_fn}")
                continue

            # 记录变更
            changes = []
            if new_cat:
                changes.append(f"类别: {current_cat} → {new_cat}")
            if buyer_short and not existing_buyer:
                changes.append(f"购买方: +{buyer_short}")

            rename_log.append({
                'old_name': fn,
                'new_name': new_fn,
                'changes': changes,
                'src_path': fpath,
                'dst_path': new_fpath,
            })

            if not dry_run:
                # 6. 重命名 03 已完成中的文件
                os.rename(fpath, new_fpath)
                stats['renamed'] += 1

                # 7. 同步更新行程目录中的副本
                trip_copies = find_trip_copies(fn, TRIP_ROOT)
                for trip_copy_path in trip_copies:
                    trip_copy_dir = os.path.dirname(trip_copy_path)
                    new_trip_path = os.path.join(trip_copy_dir, new_fn)
                    if os.path.exists(trip_copy_path):
                        os.rename(trip_copy_path, new_trip_path)
                        stats['trip_updated'] += 1
            else:
                stats['renamed'] += 1  # 预览模式也计数

    # ===== 输出报告 =====
    stats['needs_migration'] = stats['renamed'] > 0

    if check:
        return stats

    print(f"\n{'='*60}")
    print(f"📊 更新汇总\n")
    print(f"   扫描文件总数:       {stats['total']}")
    print(f"   格式不匹配(跳过):   {stats['parse_fail']}")
    print()
    print(f"   ── 类别重分类 ──")
    print(f"   类别需更新:         {stats['cat_changed']}")
    print(f"   类别不变:           {stats['cat_kept']}")
    print(f"   不降级为其他(跳过): {stats['cat_skip_other']}")
    print()
    print(f"   ── 购买方简称 ──")
    print(f"   已含购买方(跳过):   {stats['buyer_already']}")
    print(f"   可追加购买方:       {stats['buyer_added']}")
    print(f"   无购买方(跳过):     {stats['buyer_none']}")
    print()
    print(f"   {'将更新' if dry_run else '已更新'}:              {stats['renamed']}")
    print(f"   行程副本{'将更新' if dry_run else '已更新'}:      {stats['trip_updated']}")

    if cat_change_detail:
        print(f"\n   ── 类别变更明细 ──")
        for old_cat, targets in sorted(cat_change_detail.items()):
            for new_cat, cnt in sorted(targets.items()):
                print(f"     {old_cat} → {new_cat}: {cnt} 个")

    if rename_log:
        print(f"\n{'='*60}")
        print(f"📝 {'预览' if dry_run else '实际'}变更明细\n")
        for item in rename_log:
            print(f"   {item['old_name']}")
            print(f"   → {item['new_name']}")
            for ch in item['changes']:
                print(f"     {ch}")
            print()

    if dry_run:
        print(f"{'='*60}")
        print("💡 这是预览模式，未实际修改文件。")
        print("   确认无误后运行: python3 rename_update.py")
    else:
        print(f"\n{'='*60}")
        print("✅ 更新完成！")
        # 迁移完成后更新 LAST_MIGRATION_VERSION
        update_migration_version()
        if stats['renamed'] > 0:
            print("💡 建议运行发票整理以更新台账: 对我说「发票整理」")

    return stats


def update_migration_version():
    """迁移完成后，更新 config.py 中的 LAST_MIGRATION_VERSION 为当前 SKILL_VERSION"""
    config_path = os.path.join(SCRIPT_DIR, 'config.py')
    if not os.path.exists(config_path):
        return

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return

    # 读取当前版本
    try:
        from config import SKILL_VERSION
    except ImportError:
        return

    if 'LAST_MIGRATION_VERSION' in content:
        new_content = re.sub(
            r'^LAST_MIGRATION_VERSION\s*=\s*"[^"]*"',
            f'LAST_MIGRATION_VERSION = "{SKILL_VERSION}"',
            content,
            flags=re.MULTILINE
        )
    else:
        # 追加配置项
        new_content = content + f'\n# ========== 数据迁移版本（由 rename_update.py 自动更新）==========\nLAST_MIGRATION_VERSION = "{SKILL_VERSION}"\n'

    if new_content != content:
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
        except Exception:
            pass


def check_migration_needed():
    """检测是否需要数据迁移

    比较 SKILL_VERSION 和 LAST_MIGRATION_VERSION：
      - SKILL_VERSION > LAST_MIGRATION_VERSION → 可能需要迁移
      - 否则 → 不需要

    返回: (need_check: bool, current_version: str, migration_version: str)
    """
    try:
        from config import SKILL_VERSION, LAST_MIGRATION_VERSION
    except ImportError:
        return False, "0.0.0", "0.0.0"

    def parse_v(v):
        try:
            return tuple(int(x) for x in v.strip().split('.')[:3])
        except (ValueError, AttributeError):
            return (0, 0, 0)

    need = parse_v(SKILL_VERSION) > parse_v(LAST_MIGRATION_VERSION)
    return need, SKILL_VERSION, LAST_MIGRATION_VERSION


if __name__ == '__main__':
    check_mode = '--check' in sys.argv
    dry_run = '--dry-run' in sys.argv or '-n' in sys.argv

    if check_mode:
        # 检测模式：静默运行 dry-run，输出 JSON
        stats = scan_and_rename(dry_run=True, check=True)
        need, cur_v, mig_v = check_migration_needed()
        result = {
            'needs_migration': stats.get('needs_migration', False),
            'changes': stats.get('renamed', 0),
            'skill_version': cur_v,
            'last_migration_version': mig_v,
            'migration_check_needed': need,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        scan_and_rename(dry_run=dry_run)
