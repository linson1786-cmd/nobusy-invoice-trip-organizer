#!/usr/bin/env python3
"""
发票下载脚本 - 多邮箱 + 时间范围选择版
- 弹出界面选择/注册邮箱账户
- 支持 163/QQ/126/自定义 邮箱
- 选择时间范围（近7天/30天/90天/今年/自定义）
- 默认选中上次使用的邮箱 + 近90天
"""

import imaplib
import email as emaillib
import os
import sys
import re
from email.header import decode_header
from datetime import datetime, timedelta

# ===== 导入邮箱管理器 =====
try:
    from email_manager import select_or_register_account, pick_date_range
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from email_manager import select_or_register_account, pick_date_range

# ===== 从 config.py 读取下载目录 =====
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(_SCRIPT_DIR, "..", "email_attachments")  # fallback

try:
    import importlib.util
    _config_path = os.path.join(_SCRIPT_DIR, "config.py")
    if os.path.exists(_config_path):
        spec = importlib.util.spec_from_file_location("config", _config_path)
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        # 优先使用 EMAIL_DOWNLOAD_DIR，否则用 INVOICE_ROOT/01 待分类
        custom_dir = getattr(config, 'EMAIL_DOWNLOAD_DIR', None)
        if custom_dir:
            DOWNLOAD_DIR = os.path.join(_SCRIPT_DIR, "..", custom_dir)
        else:
            invoice_root = getattr(config, 'INVOICE_ROOT', None)
            if invoice_root:
                DOWNLOAD_DIR = os.path.join(invoice_root, "01 待分类")
except Exception:
    pass


def decode_str(s):
    if s is None:
        return ""
    parts = decode_header(str(s))
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(charset or "utf-8", errors="replace"))
            except Exception:
                result.append(part.decode("utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def is_invoice_filename(filename, subject=""):
    """判断文件名是否像发票附件。
    规则：必须有发票类扩展名 + (文件名或邮件主题含发票关键词) + 不含黑名单关键词
    """
    if not filename:
        return False
    fname = filename.lower()

    # 必须有发票类扩展名
    exts = [".pdf", ".ofd", ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".xls", ".xlsx"]
    if not any(fname.endswith(ext) for ext in exts):
        return False

    # 黑名单：明确非发票的文件名关键词
    blacklist_kw = [
        "员工手册", "手册", "发货", "申请表", "申请单", "物料", "通知",
        "简历", "合同", "规章", "制度", "会议", "培训", "规程", "作业指导",
    ]
    if any(kw.lower() in fname for kw in blacklist_kw):
        return False

    # 白名单：发票/报销相关关键词
    invoice_kw = [
        "发票", "invoice", "fapiao", "receipt", "票据", "bill", "报销",
        "电子发票", "行程单", "结账单", "通行费", "etc", "滴滴", "住宿",
        "餐饮", "机票", "高铁", "打车", "通行", "收据", "tax", "toll",
        "通行证", "过路费", "停车费",
    ]

    # 文件名含白名单关键词 → 通过
    if any(kw in fname for kw in invoice_kw):
        return True

    # 文件名无关键词时，检查邮件主题
    subj = (subject or "").lower()
    if any(kw in subj for kw in invoice_kw):
        return True

    return False


def connect_and_login(account):
    imap_server = account["imap_server"]
    imap_port = account.get("imap_port", 993)
    email_addr = account["email"]
    auth_code = account["auth_code"]

    provider_name = account.get("provider", "").upper()
    print(f"🔌 连接 {provider_name} IMAP 服务器 ({imap_server}:{imap_port})...")
    mail = imaplib.IMAP4_SSL(imap_server, imap_port)
    print("✅ Socket 连接成功")
    resp, data = mail.login(email_addr, auth_code)
    if resp != "OK":
        raise Exception(f"登录失败：{data}")
    print("✅ 登录成功")
    return mail


def select_inbox(mail):
    resp, data = mail.select("INBOX")
    if resp != "OK":
        resp2, data2 = mail.select("&g0l6P3ux-")
        if resp2 != "OK":
            raise Exception(f"选择收件箱失败：{data}")
    print(f"📥 收件箱已选择（共 {data[0].decode()} 封邮件）")
    return True


def search_emails(mail, start_date):
    """搜索指定日期后的邮件"""
    date_str = start_date.strftime("%d-%b-%Y")
    print(f"🔍 搜索范围：{start_date.strftime('%Y-%m-%d')} 至今")

    resp, messages = mail.search(None, f'SINCE {date_str}')
    if resp != "OK":
        raise Exception(f"搜索失败：{messages}")

    ids = messages[0].split()
    print(f"📧 日期范围内共 {len(ids)} 封邮件，开始逐一检查含附件的邮件...")
    return ids


def has_invoice_attachment(part, subject=""):
    cd = part.get("Content-Disposition", "")
    ct = part.get("Content-Type", "")

    filename = None
    for header in [cd, ct]:
        m = re.search(r'filename\*?="?([^";]+)"?', header)
        if m:
            filename = decode_str(m.group(1))
        m2 = re.search(r"name=\"?([^\";]+)\"?", header)
        if m2 and not filename:
            filename = decode_str(m2.group(1))

    if not filename:
        return None

    if is_invoice_filename(filename, subject):
        return filename
    return None


def download_from_msg(msg_bytes, download_dir):
    msg = emaillib.message_from_bytes(msg_bytes)
    subject = decode_str(msg.get("Subject", "(无主题)"))
    date = msg.get("Date", "")

    downloaded = []
    for part in msg.walk():
        fname = has_invoice_attachment(part, subject)
        if fname:
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            base_path = os.path.join(download_dir, fname)
            base, ext = os.path.splitext(base_path)
            counter = 1
            out_path = base_path
            while os.path.exists(out_path):
                out_path = f"{base}_{counter}{ext}"
                counter += 1
            with open(out_path, "wb") as f:
                f.write(payload)
            downloaded.append({
                "filename": os.path.basename(out_path),
                "filepath": out_path,
                "subject": subject,
                "date": date,
            })
            print(f"  ✅ {os.path.basename(out_path)}  （主题：{subject[:40]}）")
    return downloaded


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

    # 默认弹窗选择邮箱，--auto 参数才自动使用上次邮箱
    auto_pick = "--auto" in sys.argv

    # ===== Step 1: 选择/注册邮箱 =====
    print("=" * 50)
    print("📮 邮箱发票下载")
    print("=" * 50)
    print()

    account = select_or_register_account(auto_pick=auto_pick)
    if account is None:
        print("❌ 未选择邮箱，退出")
        return

    print(f"\n已选择: {account['name']} ({account['email']})")

    # ===== Step 2: 选择时间范围 =====
    print()
    start_date, end_date = pick_date_range(auto_pick=auto_pick)
    if start_date is None:
        print("❌ 未选择时间范围，退出")
        return

    # ===== Step 3: 连接并下载 =====
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    print(f"\n📂 下载目录: {DOWNLOAD_DIR}")
    print(f"📅 搜索范围: {start_date.strftime('%Y-%m-%d')} ～ {end_date.strftime('%Y-%m-%d')}")
    print()

    try:
        mail = connect_and_login(account)
        select_inbox(mail)
        print()

        email_ids = search_emails(mail, start_date)

        # 搜索后，按邮件日期过滤到 end_date
        # IMAP SINCE 只能搜起始日，结束日需手动过滤
        all_files = []
        total_checked = 0
        for i, eid in enumerate(email_ids, 1):
            eid_str = eid.decode()
            resp, data = mail.fetch(eid_str, "(RFC822)")
            if resp != "OK":
                print(f"  ⚠️  [{i}] 获取失败，跳过")
                continue
            try:
                # 解析邮件日期
                msg = emaillib.message_from_bytes(data[0][1])
                msg_date_str = msg.get("Date", "")
                msg_date = None
                if msg_date_str:
                    try:
                        from email.utils import parsedate_to_datetime
                        msg_date = parsedate_to_datetime(msg_date_str)
                        # 转为 naive datetime 便于比较
                        msg_date = msg_date.replace(tzinfo=None)
                    except Exception:
                        pass

                # 过滤超出结束日期的邮件
                if msg_date and msg_date > end_date + timedelta(days=1):
                    continue

                total_checked += 1
                files = download_from_msg(data[0][1], DOWNLOAD_DIR)
                if files:
                    all_files.extend(files)
            except Exception as e:
                print(f"  ⚠️  [{i}] 处理出错：{e}")

        mail.logout()

        print(f"\n{'=' * 50}")
        print(f"📊 下载完成")
        print(f"   邮箱：{account['name']} ({account['email']})")
        print(f"   范围：{start_date.strftime('%Y-%m-%d')} ～ {end_date.strftime('%Y-%m-%d')}")
        print(f"   检查：{total_checked} 封邮件")
        print(f"   成功：{len(all_files)} 个发票附件")
        print(f"   路径：{DOWNLOAD_DIR}")

        if all_files:
            print(f"\n📄 文件列表：")
            for f in all_files:
                print(f"   - {f['filename']}")

        print("\n✅ 邮箱连接已关闭")
    except Exception as e:
        print(f"\n❌ 下载失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
