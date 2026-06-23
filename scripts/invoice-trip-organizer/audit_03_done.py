#!/usr/bin/env python3
"""全面排查03已完成文件，按SOP规则逐项检查：类别、金额、日期、路线、格式、去重等"""

import os, re, sys
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from invoice_auto_organizer import (
    extract_pdf_text, extract_invoice_number, classify, classify_with_subtype,
    extract_amount_from_text, extract_amount_from_filename,
    extract_route, extract_stay_date_from_text, extract_city_from_text,
    extract_seller_name_from_text, STANDARD_NAME_RE, MAJOR_CITIES, CATEGORY_RULES,
    VALID_CATEGORIES, DONE_DIR
)

# ===== 检查规则 =====

def check_all_files():
    """遍历03已完成所有文件，逐项检查"""
    issues = []
    invoice_num_map = {}  # 发票号→文件列表（去重检查）
    filename_map = {}     # (日期,类别,金额)→文件列表（重名检查）
    
    for month_dir_name in sorted(os.listdir(DONE_DIR)):
        month_dir = os.path.join(DONE_DIR, month_dir_name)
        if not os.path.isdir(month_dir) or month_dir_name.startswith('.'):
            continue
        
        for fn in sorted(os.listdir(month_dir)):
            if fn.startswith('.') or fn == '台账.md':
                continue
            fpath = os.path.join(month_dir, fn)
            ext = os.path.splitext(fn)[1].lower()
            
            # 1. 基本格式检查：是否符合STANDARD_NAME_RE
            m = STANDARD_NAME_RE.match(fn)
            if not m:
                issues.append(("格式不符", fn, fpath, f"文件名不匹配标准正则"))
                continue
            
            date = m.group(1)
            cat = m.group(2)
            amt_str = m.group(3)
            route = m.group(4) or ""
            suffix = m.group(5) or ""
            mmdd = m.group(6)
            wb_yb = m.group(7)
            seq = m.group(8)
            file_ext = m.group(9)
            
            # 解析金额
            try:
                amt_val = float(amt_str.replace(',', ''))
            except:
                issues.append(("金额格式", fn, fpath, f"金额'{amt_str}'无法转为数字"))
                continue
            
            # 2. 类别检查
            if cat not in VALID_CATEGORIES:
                issues.append(("类别无效", fn, fpath, f"类别'{cat}'不在有效列表中"))
            
            # 3. 提取文本内容做深度检查
            text = ""
            if ext == '.pdf':
                text = extract_pdf_text(fpath) or ""
            elif ext == '.ofd':
                # OFD不在03已完成（应已转PDF），但万一有
                text = ""
            elif ext in ('.jpg', '.jpeg', '.png', '.heic', '.bmp', '.tiff', '.tif', '.webp'):
                # 图片文件，OCR可能不可用
                text = ""
            
            # 4. 类别vs内容匹配检查
            if text:
                # 用文本重新分类，看是否与文件名类别一致
                re_classified = classify_with_subtype(text, fn)
                # 基础类别
                base_cat = classify(text, fn)
                if cat != re_classified:
                    # 可能是子类型差异，检查基础类别
                    if cat.split('(')[0] != base_cat:
                        issues.append(("类别错误", fn, fpath, 
                            f"文件名类别='{cat}', 文本推断类别='{re_classified}' (基础='{base_cat}')"))
                    # 子类型不同但基础类别相同 → 可能是命名时没加子类型
                    elif '(' not in cat and '(' in re_classified:
                        issues.append(("缺少子类型", fn, fpath, 
                            f"文件名类别='{cat}'(无子类型), 文本推断='{re_classified}'(有子类型)"))
            
            # 5. 金额检查：文件名金额 vs 文本提取的价税合计
            if text:
                extracted_amt = extract_amount_from_text(text)
                if extracted_amt:
                    try:
                        extracted_amt_float = float(extracted_amt.replace(',', ''))
                    except:
                        extracted_amt_float = None
                    if extracted_amt_float and extracted_amt_float > 0:
                        # 允许0.01误差（浮点精度）
                        if abs(extracted_amt_float - amt_val) > 0.01:
                            issues.append(("金额错误", fn, fpath, 
                                f"文件名金额={amt_val:.2f}, 文本提取价税合计={extracted_amt_float:.2f}"))
                        # 检查是否取了税额而非价税合计
                        tax_matches = re.findall(r'税额[^\d]*([\d,]+\.\d{2})', text)
                        for tm in tax_matches:
                            try:
                                tax_val = float(tm.replace(',', ''))
                                if abs(amt_val - tax_val) < 0.01 and amt_val != extracted_amt_float:
                                    issues.append(("金额取税额", fn, fpath, 
                                        f"文件名金额={amt_val:.2f}可能是税额而非价税合计={extracted_amt_float:.2f}"))
                            except:
                                pass
            
            # 6. 发票号检查（去重）
            inv_num_result = extract_invoice_number(text) if text else None
            if inv_num_result:
                inv_num, _ = inv_num_result
                if len(inv_num) >= 18 and inv_num.isdigit():
                    if inv_num not in invoice_num_map:
                        invoice_num_map[inv_num] = []
                    invoice_num_map[inv_num].append((fn, fpath))
            
            # 7. 日期检查
            # 7a. 机票类：文件名日期应该是行程日期而非开票日期
            if cat in ('机票', '机票(保险)') and text:
                # 检查备注行程日期
                trip_date_match = re.search(r'行程日期[：:]\s*(\d{4}[-/]\d{2}[-/]\d{2})', text)
                ctrip_match = re.search(r'携程订单[：:][^,]*,\s*(\d{4}/\d{2}/\d{2})', text)
                flight_date_match = re.search(r'航班日期[：:]\s*(\d{4}[-/]\d{2}[-/]\d{2})', text)
                # 开票日期
                issue_date_match = re.search(r'开票日期[：:]\s*(\d{4}[-/]\d{2}[-/]\d{2})', text)
                issue_date_match2 = re.search(r'(\d{4})年(\d{2})月(\d{2})日', text)
                
                best_trip_date = None
                if ctrip_match:
                    best_trip_date = ctrip_match.group(1).replace('/', '-')
                elif trip_date_match:
                    best_trip_date = trip_date_match.group(1).replace('/', '-')
                elif flight_date_match:
                    best_trip_date = flight_date_match.group(1).replace('/', '-')
                
                # 如果文件名日期=开票日期但有行程日期 → 可能日期错了
                if best_trip_date and best_trip_date != date:
                    # 检查开票日期
                    issue_date = None
                    if issue_date_match:
                        issue_date = issue_date_match.group(1).replace('/', '-')
                    elif issue_date_match2:
                        issue_date = f"{issue_date_match2.group(1)}-{issue_date_match2.group(2)}-{issue_date_match2.group(3)}"
                    
                    if issue_date and date == issue_date and date != best_trip_date:
                        issues.append(("机票日期应为行程日期", fn, fpath, 
                            f"文件名日期={date}(=开票日期), 行程日期={best_trip_date}"))
            
            # 7b. 高铁类：文件名日期应该是乘车日期而非开票日期
            if cat in ('高铁',) and text:
                # 检查乘车日期
                travel_date_match = re.search(r'(\d{4})年(\d{2})月(\d{2})日\s+\d{2}:\d{2}开', text)
                depart_time_match = re.search(r'出发时间[：:]\s*(\d{4}[-/]\d{2}[-/]\d{2})', text)
                issue_date_match2 = re.search(r'开票日期[：:][^\d]*(\d{4})年(\d{2})月(\d{2})日', text)
                
                travel_date = None
                if travel_date_match:
                    travel_date = f"{travel_date_match.group(1)}-{travel_date_match.group(2)}-{travel_date_match.group(3)}"
                elif depart_time_match:
                    travel_date = depart_time_match.group(1).replace('/', '-')
                
                issue_date = None
                if issue_date_match2:
                    issue_date = f"{issue_date_match2.group(1)}-{issue_date_match2.group(2)}-{issue_date_match2.group(3)}"
                
                if travel_date and travel_date != date:
                    if issue_date and date == issue_date:
                        issues.append(("高铁日期应为乘车日期", fn, fpath, 
                            f"文件名日期={date}(=开票日期), 乘车日期={travel_date}"))
            
            # 7c. 住宿类：文件名日期应该是入住日期而非开票日期
            if cat.split('(')[0] == '住宿' and text:
                stay_date, stay_source = extract_stay_date_from_text(text)
                if stay_date and stay_date != date:
                    # 检查是否文件名日期=开票日期
                    issue_date_match2 = re.search(r'开票日期[：:][^\d]*(\d{4})年(\d{2})月(\d{2})日', text)
                    if issue_date_match2:
                        issue_date = f"{issue_date_match2.group(1)}-{issue_date_match2.group(2)}-{issue_date_match2.group(3)}"
                        if date == issue_date:
                            issues.append(("住宿日期应为入住日期", fn, fpath, 
                                f"文件名日期={date}(=开票日期), 入住日期={stay_date}(来源={stay_source})"))
                    elif '打印日期' in text:
                        # 结账单用打印日期
                        issues.append(("住宿日期应为入住日期", fn, fpath, 
                            f"文件名日期={date}, 入住日期={stay_date}(来源={stay_source})"))
            
            # 8. 机票/高铁路线检查
            if cat in ('机票', '高铁') and '(' not in cat:
                # 机票/高铁(非保险/非服务费)应该有路线
                if text:
                    extracted_route = extract_route(text, cat)
                    if extracted_route and not route:
                        issues.append(("缺少路线", fn, fpath, 
                            f"机票/高铁应含出发-到达，文本提取路线='{extracted_route}'但文件名无路线"))
                    elif extracted_route and route and extracted_route != route:
                        # 路线可能格式不同（如城市名vs站名），不强制相同
                        pass  # 不报错，只提示
                elif not route and cat == '机票':
                    # 机票保险可以没有路线
                    pass
            
            # 9. 扩展名检查
            valid_exts = ['.pdf', '.jpg', '.jpeg', '.png', '.heic', '.bmp', '.tiff', '.tif', '.webp']
            if file_ext.lower() not in valid_exts:
                issues.append(("扩展名异常", fn, fpath, f"扩展名'{file_ext}'不在标准列表中"))
            
            # 10. 报销状态检查
            if wb_yb not in ('WB', 'YB'):
                issues.append(("报销状态异常", fn, fpath, f"报销状态'{wb_yb}'应为WB或YB"))
            
            # 11. 序号检查（3位数字）
            if seq:
                try:
                    seq_num = int(seq)
                    if seq_num < 1 or seq_num > 999:
                        issues.append(("序号异常", fn, fpath, f"序号'{seq}'应为1-999的3位数字"))
                except:
                    issues.append(("序号格式", fn, fpath, f"序号'{seq}'非数字"))
            
            # 12. 文件名日期vs目录月份一致性
            file_month = date[:7]  # YYYY-MM
            dir_month = month_dir_name  # 应为YYYY-MM格式
            if file_month != dir_month and cat.split('(')[0] != '住宿':
                # 住宿可能跨月（开票日期和入住日期不同月），不发错误
                # 机票/高铁也可能跨月（行程日期和开票日期不同月）
                # 其他类别日期=开票日期，应与目录月份一致
                if cat.split('(')[0] in ('餐饮', '滴滴打车', '高速费', '充电费', '礼品', '其他', '行程单', '结账单'):
                    issues.append(("日期与目录月份不一致", fn, fpath, 
                        f"文件名日期月份={file_month}, 目录月份={dir_month}"))
            
            # 13. 重名文件检查
            key = (date, cat, amt_val)
            if key not in filename_map:
                filename_map[key] = []
            filename_map[key].append((fn, fpath, route))
            
            # 14. 0.00金额检查（除结账单外不应为0）
            if amt_val == 0.00 and cat != '结账单' and '(' not in cat:
                issues.append(("金额为0", fn, fpath, f"金额0.00（非结账单类别不应为0）"))
    
    # 15. 发票号去重检查
    for inv_num, files in invoice_num_map.items():
        if len(files) > 1:
            issues.append(("发票号重复", files[0][0], files[0][1], 
                f"发票号{inv_num}出现{len(files)}次: {[f[0] for f in files]}"))
    
    # 16. 重名文件检查（同日期+类别+金额但无发票号区分）
    for key, files in filename_map.items():
        if len(files) > 1:
            # 检查是否都有发票号后4位或序号区分
            names = [f[0] for f in files]
            # 如果文件名完全相同 → 严重问题
            if len(set(names)) < len(names):
                issues.append(("文件名完全重复", files[0][0], files[0][1],
                    f"同日期类别金额有完全相同文件名: {names}"))
    
    return issues


def format_issues(issues):
    """格式化问题列表"""
    # 按问题类型分组
    by_type = {}
    for issue in issues:
        type_name = issue[0]
        if type_name not in by_type:
            by_type[type_name] = []
        by_type[type_name].append(issue)
    
    lines = []
    lines.append(f"# 03已完成文件全面排查报告")
    lines.append(f"")
    lines.append(f"## 问题汇总")
    lines.append(f"")
    total = len(issues)
    lines.append(f"共发现 **{total}** 个问题，按类型分布：")
    lines.append(f"")
    
    for type_name in sorted(by_type.keys()):
        count = len(by_type[type_name])
        lines.append(f"- **{type_name}**: {count} 个")
    
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    
    for type_name in sorted(by_type.keys()):
        lines.append(f"## {type_name} ({len(by_type[type_name])} 个)")
        lines.append(f"")
        for issue in by_type[type_name]:
            type_, fn, fpath, detail = issue
            # 只显示文件名和详细说明
            lines.append(f"- `{fn}` — {detail}")
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")
    
    # 修正建议
    lines.append(f"## 修正建议")
    lines.append(f"")
    
    # 类别错误修正
    cat_issues = by_type.get("类别错误", [])
    if cat_issues:
        lines.append(f"### 类别修正")
        lines.append(f"")
        for issue in cat_issues:
            fn, fpath, detail = issue[1], issue[2], issue[3]
            # 重新分类获取正确类别
            ext = os.path.splitext(fn)[1].lower()
            text = ""
            if ext == '.pdf':
                text = extract_pdf_text(fpath) or ""
            if text:
                new_cat = classify_with_subtype(text, fn)
                m = STANDARD_NAME_RE.match(fn)
                if m:
                    new_fn = fn.replace(m.group(2), new_cat)
                    lines.append(f"- `{fn}` → `{new_fn}`")
        lines.append(f"")
    
    # 金额错误修正
    amt_issues = by_type.get("金额错误", []) + by_type.get("金额取税额", [])
    if amt_issues:
        lines.append(f"### 金额修正")
        lines.append(f"")
        for issue in amt_issues:
            fn, fpath, detail = issue[1], issue[2], issue[3]
            ext = os.path.splitext(fn)[1].lower()
            text = ""
            if ext == '.pdf':
                text = extract_pdf_text(fpath) or ""
            if text:
                new_amt = extract_amount_from_text(text)
                if new_amt:
                    new_amt_float = float(new_amt.replace(',', ''))
                m = STANDARD_NAME_RE.match(fn)
                if m and new_amt_float:
                    new_fn = fn.replace(m.group(3), f"{new_amt_float:.2f}")
                    lines.append(f"- `{fn}` → `{new_fn}` (金额 {m.group(3)}→{new_amt_float:.2f})")
        lines.append(f"")
    
    # 日期修正
    date_issues = by_type.get("机票日期应为行程日期", []) + \
                  by_type.get("高铁日期应为乘车日期", []) + \
                  by_type.get("住宿日期应为入住日期", [])
    if date_issues:
        lines.append(f"### 日期修正")
        lines.append(f"")
        for issue in date_issues:
            fn, fpath, detail = issue[1], issue[2], issue[3]
            lines.append(f"- `{fn}` — {detail}")
        lines.append(f"")
    
    # 缺少路线
    route_issues = by_type.get("缺少路线", [])
    if route_issues:
        lines.append(f"### 缺少路线")
        lines.append(f"")
        for issue in route_issues:
            fn, fpath, detail = issue[1], issue[2], issue[3]
            ext = os.path.splitext(fn)[1].lower()
            text = ""
            if ext == '.pdf':
                text = extract_pdf_text(fpath) or ""
            if text:
                m = STANDARD_NAME_RE.match(fn)
                cat = m.group(2) if m else ""
                new_route = extract_route(text, cat) if m else ""
                if new_route and m:
                    # 在金额后插入路线
                    old_part = f"{m.group(3)}"
                    new_part = f"{m.group(3)}_{new_route}"
                    # 如果有suffix也要调整
                    if m.group(5):
                        old_part = f"{m.group(3)}_{m.group(5)}"
                        new_part = f"{m.group(3)}_{new_route}_{m.group(5)}"
                    # 更精确的替换：直接重组文件名
                    new_fn = f"{m.group(1)}_{m.group(2)}_{m.group(3)}_{new_route}"
                    if m.group(5):
                        new_fn += f"_{m.group(5)}"
                    new_fn += f"_{m.group(6)}_{m.group(7)}_{m.group(8)}.{m.group(9)}"
                    lines.append(f"- `{fn}` → `{new_fn}` (添加路线 {new_route})")
                else:
                    lines.append(f"- `{fn}` — {detail}")
        lines.append(f"")
    
    return '\n'.join(lines)


if __name__ == '__main__':
    print("🔍 开始全面排查03已完成文件...")
    issues = check_all_files()
    report = format_issues(issues)
    
    # 保存报告
    report_path = os.path.join(SCRIPT_DIR, "audit_report_03_done.md")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n✅ 排查完成，发现 {len(issues)} 个问题")
    print(f"📄 报告已保存: {report_path}")
    
    # 按类型统计
    by_type = {}
    for issue in issues:
        type_name = issue[0]
        by_type.setdefault(type_name, []).append(issue)
    
    print(f"\n问题分布:")
    for type_name in sorted(by_type.keys()):
        print(f"  {type_name}: {len(by_type[type_name])} 个")
