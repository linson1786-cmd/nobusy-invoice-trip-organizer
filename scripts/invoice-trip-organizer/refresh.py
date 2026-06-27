#!/usr/bin/env python3
"""
刷新 - 升级后一键更新所有数据

功能:
  Phase 0c: 版本核查 — 升级后首次刷新时，把 03 已完成文件移回 01 待分类重新识别
  Phase 1: 数据迁移 — 重新识别 03 已完成中所有文件的类别和购买方简称 (rename_update.py)
  Phase 2: 行程刷新 — 重新扫描所有已有行程，从 03 已完成重新匹配发票
           - 清空旧发票附件，重新复制
           - 餐饮发票归档到月度餐饮目录
           - 重新生成发票清单、行程详情、行程总览
  Phase 3: 台账重生成 — 重新扫描 03 已完成生成台账

触发方式: 用户说"刷新"
用法:
  python3 refresh.py           # 执行刷新
  python3 refresh.py --dry-run # 预览（不修改文件）
"""

import os, re, sys, importlib.util
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)


def _load_module(name, path):
    """动态加载 Python 模块"""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ===== 加载 config =====
_config_path = os.path.join(SCRIPT_DIR, "config.py")
if not os.path.exists(_config_path):
    print("错误: 未找到 config.py，请先运行「初始化设置」")
    sys.exit(1)

config = _load_module("config", _config_path)

# ===== 加载 trip_auto_organizer =====
_trip_ao_path = os.path.join(SCRIPT_DIR, "trip_auto_organizer.py")
trip_ao = _load_module("trip_auto_organizer", _trip_ao_path)

# ===== 加载 rename_update =====
_ru_path = os.path.join(SCRIPT_DIR, "rename_update.py")
rename_update = _load_module("rename_update", _ru_path)

# ===== 加载 invoice_auto_organizer =====
_inv_ao_path = os.path.join(SCRIPT_DIR, "invoice_auto_organizer.py")
invoice_ao = _load_module("invoice_auto_organizer", _inv_ao_path)


def scan_all_trips(trip_root):
    """扫描所有已有行程，返回按日期排序的列表"""
    trips = []
    folder_re = re.compile(r'出差(\d+)-(\d{4}-\d{2}-\d{2})[～~](\d{4}-\d{2}-\d{2})_(.+)')

    for year_name in sorted(os.listdir(trip_root)):
        year_dir = os.path.join(trip_root, year_name)
        if not os.path.isdir(year_dir):
            continue
        for month_name in sorted(os.listdir(year_dir)):
            month_dir = os.path.join(year_dir, month_name)
            if not os.path.isdir(month_dir):
                continue
            for folder_name in sorted(os.listdir(month_dir)):
                full_path = os.path.join(month_dir, folder_name)
                if not os.path.isdir(full_path):
                    continue
                m = folder_re.match(folder_name)
                if not m:
                    continue
                trip_id = int(m.group(1))
                start_date = m.group(2)
                end_date = m.group(3)
                route_str = m.group(4)
                route_list = route_str.split('-')
                year = year_name.replace(' 年', '')
                month = int(month_name.replace(' 月', ''))
                trips.append({
                    'trip_id': trip_id,
                    'start_date': start_date,
                    'end_date': end_date,
                    'route_list': route_list,
                    'route_str': route_str,
                    'trip_dir': full_path,
                    'folder_name': folder_name,
                    'year': year,
                    'month': month,
                    'month_str': month_name,
                })

    # 按开始日期排序
    trips.sort(key=lambda t: t['start_date'])
    return trips


def delete_overview(trip_root):
    """删除行程总览（避免刷新时产生重复行）"""
    overview_path = os.path.join(trip_root, "2026 年", "行程总览.md")
    if os.path.exists(overview_path):
        os.remove(overview_path)
        print(f"   清除旧行程总览（将重新生成）")


def update_refresh_version():
    """刷新完成后，更新 config.py 中的 LAST_REFRESH_VERSION 为当前 SKILL_VERSION"""
    config_path = os.path.join(SCRIPT_DIR, 'config.py')
    if not os.path.exists(config_path):
        return

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return

    skill_ver = getattr(config, 'SKILL_VERSION', '')
    if not skill_ver:
        return

    if 'LAST_REFRESH_VERSION' in content:
        new_content = re.sub(
            r'^LAST_REFRESH_VERSION\s*=\s*"[^"]*"',
            f'LAST_REFRESH_VERSION = "{skill_ver}"',
            content,
            flags=re.MULTILINE
        )
    else:
        new_content = content + f'\n# ========== 刷新版本（由 refresh.py 自动更新）==========\nLAST_REFRESH_VERSION = "{skill_ver}"\n'

    if new_content != content:
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
        except Exception:
            pass


def main():
    dry_run = '--dry-run' in sys.argv or '-n' in sys.argv

    # 版本检查（自动更新）
    try:
        vm_path = os.path.join(SCRIPT_DIR, "version_manager.py")
        if os.path.exists(_config_path) and os.path.exists(vm_path):
            vm = _load_module("version_manager", vm_path)
            vm.check_and_update(_config_path, auto=True, silent=True)
    except Exception:
        pass

    trip_root = os.path.expanduser(getattr(config, 'TRIP_ROOT', ''))
    if not trip_root:
        print("错误: config.py 中未配置 TRIP_ROOT")
        sys.exit(1)

    skill_ver = getattr(config, 'SKILL_VERSION', '?')
    mig_ver = getattr(config, 'LAST_MIGRATION_VERSION', '?')

    print("=" * 60)
    print("刷新 — 升级后数据更新" + (" [预览模式]" if dry_run else ""))
    print(f"   Skill 版本: {skill_ver}")
    print(f"   上次迁移版本: {mig_ver}")
    print(f"   行程根目录: {trip_root}")
    print("=" * 60)
    print()

    # V1.0.36 Bug 6: 检测 02 待核实 是否有文件，提示用户先跑文件识别
    review_dir = os.path.join(getattr(config, 'BASE_ROOT', ''), '02 待核实')
    if os.path.isdir(review_dir):
        review_files = [f for f in os.listdir(review_dir)
                        if not f.startswith('.') and os.path.isfile(os.path.join(review_dir, f))]
        if review_files:
            print(f"⚠️  02 待核实/ 中有 {len(review_files)} 个文件未处理！")
            print(f"   刷新命令只更新台账和行程总览，不会重新识别 02 待核实 中的文件。")
            print(f"   如需重新识别这些文件，请先运行「文件识别」命令。")
            print(f"   示例文件: {review_files[0][:50]}{'...' if len(review_files[0])>50 else ''}")
            print()

    # ===== Phase 0: 目录名迁移 =====
    print("[Phase 0] 目录名迁移检查")
    print("-" * 50)
    try:
        mig_changed, mig_msg = rename_update.migrate_directory_name(dry_run=dry_run)
        print(f"   {mig_msg}")
        if mig_changed and not dry_run:
            print("   ⚠️  目录已重命名，请重新运行刷新以使用新路径")
            print("=" * 60)
            return
    except Exception as e:
        print(f"   目录迁移检查失败: {e}")
    print()

    # ===== Phase 0b: 行程/报销单拆分迁移 =====
    print("[Phase 0b] 行程/报销单目录拆分迁移检查")
    print("-" * 50)
    try:
        split_changed, split_msg = rename_update.migrate_trip_reimbursement_split(dry_run=dry_run)
        print(f"   {split_msg}")
        if split_changed and not dry_run:
            print("   ⚠️  目录已拆分，请重新运行刷新以使用新路径")
            print("=" * 60)
            return
    except Exception as e:
        print(f"   行程/报销单拆分迁移检查失败: {e}")
    print()

    # ===== Phase 0c: 版本核查 — 升级后重新识别 03 已完成 =====
    print("[Phase 0c] 版本核查（升级后重新识别 03 已完成）")
    print("-" * 50)

    last_refresh_ver = getattr(config, 'LAST_REFRESH_VERSION', '0.0.0')
    print(f"   Skill 版本: {skill_ver} | 上次刷新版本: {last_refresh_ver}")

    need_reprocess = False
    try:
        # 简单版本比较（语义化版本字符串直接比较不够精确，但对我们的场景足够了）
        # 用 tuple(int) 比较
        def _parse_ver(v):
            try:
                return tuple(int(x) for x in v.split('.'))
            except Exception:
                return (0, 0, 0)
        need_reprocess = _parse_ver(skill_ver) > _parse_ver(last_refresh_ver)
    except Exception:
        need_reprocess = skill_ver != last_refresh_ver

    if need_reprocess and not dry_run:
        print(f"   检测到版本升级 ({last_refresh_ver} → {skill_ver})，重新识别 03 已完成...")
        moved = invoice_ao.reprocess_done_files()
        if moved > 0:
            print(f"   正在重新分类...")
            try:
                success, review, dup_deleted, _ = invoice_ao.process_inbox()
                print(f"   ✅ 重新分类完成: 归档 {len(success)} | 退回 {len(review)} | 去重 {dup_deleted}")
            except Exception as e:
                print(f"   ⚠️ 重新分类失败: {e}")
        else:
            print(f"   03 已完成无文件，跳过")
        update_refresh_version()
    elif need_reprocess and dry_run:
        print(f"   [预览] 检测到版本升级，将重新识别 03 已完成")
    else:
        print(f"   版本未变化，跳过重新识别")

    print()

    # ===== Phase 1: 数据迁移 =====
    print("[Phase 1] 数据迁移（类别重分类 + 购买方简称）")
    print("-" * 50)

    need_migration, cur_v, last_mig_v = rename_update.check_migration_needed()

    if need_migration:
        print(f"   检测到版本升级: {last_mig_v} → {cur_v}，执行数据迁移...")
    else:
        print(f"   版本未变化（{cur_v}），仍执行数据检查...")

    print()

    if dry_run:
        mig_stats = rename_update.scan_and_rename(dry_run=True, check=False)
    else:
        mig_stats = rename_update.scan_and_rename(dry_run=False, check=False)

    migration_changed = mig_stats.get('renamed', 0) > 0
    print()

    # ===== Phase 2: 行程刷新 =====
    print("[Phase 2] 行程刷新（重新匹配发票 + 重生成文件）")
    print("-" * 50)

    trips = scan_all_trips(trip_root)
    print(f"   扫描到 {len(trips)} 条已有行程")
    print()

    if not dry_run:
        delete_overview(trip_root)

    success_count = 0
    failed_count = 0
    total_invoices = 0
    total_dining = 0

    for trip in trips:
        trip_id = trip['trip_id']
        start_date = trip['start_date']
        end_date = trip['end_date']
        route_list = trip['route_list']
        trip_dir = trip['trip_dir']
        folder_name = trip['folder_name']
        year = trip['year']
        month = trip['month']
        month_str = trip['month_str']

        print(f"   出差{trip_id}: {start_date}～{end_date} {'-'.join(route_list)}")

        try:
            # 1. 扫描匹配发票
            matched = trip_ao.scan_done_invoices(start_date, end_date)
            dining_count = len([inv for inv in matched if inv['category'] == '餐饮'])
            non_dining = len(matched) - dining_count
            total_invoices += non_dining
            total_dining += dining_count

            if dry_run:
                if matched:
                    print(f"      匹配 {len(matched)} 张（非餐饮 {non_dining}，餐饮 {dining_count}）")
                else:
                    print(f"      无匹配发票")
                print(f"      预览完成")
                success_count += 1
                continue

            # 2. 复制发票到行程（清空旧文件）
            if matched:
                trip_ao.copy_invoices_to_trip(matched, trip_dir, clear_existing=True)
                # 3. 餐饮发票归档到月度
                trip_ao.copy_dining_to_monthly(matched, year, month)

            # 4. 重新生成发票清单
            _, count_reimburse, total_reimburse = trip_ao.gen_invoice_list_md(
                matched, trip_dir, folder_name, month_str
            )

            # 5. 重新生成行程详情（更新格式/链接）
            trip_ao.gen_trip_detail_md(
                trip_id, start_date, end_date, route_list, trip_dir, folder_name
            )

            # 6. 更新行程总览
            trip_ao.update_trip_overview(
                trip_id, start_date, end_date, route_list, folder_name, month_str,
                count_reimburse, total_reimburse
            )

            if matched:
                print(f"      匹配 {len(matched)} 张（非餐饮 {non_dining}，餐饮 {dining_count}），报销 ¥{total_reimburse:,.2f}")
            else:
                print(f"      无匹配发票")
            print(f"      完成")
            success_count += 1
        except Exception as e:
            failed_count += 1
            print(f"      失败: {e}")
        print()

    # ===== Phase 3: 台账重生成 =====
    print("[Phase 3] 台账重生成")
    print("-" * 50)

    if not dry_run:
        try:
            invoice_ao.update_ledgers()
            print("   台账已重新生成")
        except Exception as e:
            print(f"   台账生成失败: {e}")
    else:
        print("   [预览模式] 跳过台账生成")

    print()

    # ===== 汇总 =====
    print("=" * 60)
    print("刷新汇总" + (" [预览模式]" if dry_run else ""))
    print("=" * 60)
    print(f"   数据迁移: {'有变更' if migration_changed else '无变更'}")
    print(f"   行程刷新: {success_count} 成功" + (f", {failed_count} 失败" if failed_count else ""))
    print(f"   匹配发票: {total_invoices} 张（非餐饮）")
    if total_dining:
        print(f"   餐饮发票: {total_dining} 张（归档至月度目录）")

    if not dry_run:
        # 更新迁移版本
        if migration_changed or need_migration:
            rename_update.update_migration_version()
            print(f"   迁移版本已更新: {skill_ver}")

    print()
    if dry_run:
        print("预览完成，未修改任何文件。")
        print("确认无误后运行: python3 refresh.py")
    else:
        print("刷新完成！所有数据已更新到最新规则。")
    print("=" * 60)


if __name__ == '__main__':
    main()
