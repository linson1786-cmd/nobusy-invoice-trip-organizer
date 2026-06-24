#!/usr/bin/env python3
"""
发票自动整理工具 - 持续监控模式
功能:
  1. 扫描 01 待分类/ → 自动识别分类 → 03 已完成/ 或 02 待核实/
  2. 扫描 02 待核实/ → 检测已手动重命名为标准格式的文件 → 自动归档到 03 已完成/
标准命名: YYYY-MM-DD_类别_金额.扩展名
设计:
  - 01 待分类: 新文件进来，脚本自动提取日期/金额/类别，符合→03，不符合→02
  - 02 待核实: 用户手动核实后，把文件名改成标准格式，脚本检测到自动归档
    判断"已核实"的标准 = 文件名符合 YYYY-MM-DD_类别_金额.扩展名 格式
"""
import os, re, sys, shutil, json, zipfile, xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pdfminer.high_level import extract_text as pdfminer_extract_text
import warnings
warnings.filterwarnings('ignore')
try:
    import fitz  # PyMuPDF, 用于OFD→PDF转换
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False
try:
    from fpdf import FPDF  # fpdf2, 用于XML→PDF转换
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False
try:
    from PIL import Image  # Pillow, 用于图片格式读取
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
try:
    import pytesseract  # OCR引擎, 用于图片发票文字识别
    # 检查tesseract是否实际可用
    try:
        pytesseract.get_tesseract_version()
        OCR_AVAILABLE = True
    except:
        OCR_AVAILABLE = False
except ImportError:
    OCR_AVAILABLE = False

# ===== 配置由 config.py 提供；未初始化时保持为空，运行前给出明确提示 =====
BASE_ROOT = ""
INPUT_DIR = ""
DONE_DIR = ""
REVIEW_DIR = ""
LOG_FILE = ""

VALID_CATEGORIES = ["餐饮", "住宿", "机票", "高铁", "滴滴打车", "行程单", "高速费", "充电费", "油电类", "礼品", "结账单", "其他",
                    "机票(保险)", "滴滴打车(行程单)", "住宿(结账单)", "高速费(行程单)"]
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.heic', '.bmp', '.tiff', '.tif', '.webp']
PROCESSABLE_EXTENSIONS = ['.pdf'] + IMAGE_EXTENSIONS
BUSINESS_FILE_EXTENSIONS = set(PROCESSABLE_EXTENSIONS + ['.ofd', '.xml'])

# ===== 尝试从 config.py 覆盖配置 =====
try:
    import importlib.util
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _config_path = os.path.join(_script_dir, "config.py")
    if os.path.exists(_config_path):
        spec = importlib.util.spec_from_file_location("config", _config_path)
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        # 覆盖所有大写变量
        _overridden = []
        for _attr in dir(config):
            if _attr.isupper():
                globals()[_attr] = getattr(config, _attr)
                _overridden.append(_attr)
        # 重建正则 (VALID_CATEGORIES 可能已被覆盖)
        STANDARD_NAME_RE = re.compile(
            r'^(\d{4}-\d{2}-\d{2})_(' + '|'.join(re.escape(c) for c in VALID_CATEGORIES) + r')_(\d+\.\d{2})'
            r'(?:_([^_\d]+(?:-[^_\d]+)?(?:_[\u4e00-\u9fa5]{2,10})?))?'   # Optional route/city + buyer
            r'(?:_(\d{1,4}))?'            # Optional suffix
            r'(?:_(\d{4})_(WB|YB))?'      # Optional status
            r'(?:_(\d{3}))?'              # Optional seq
            r'(\.\w+)$'
        )
        print(f"✅ 已从 config.py 读取配置 ({len(_overridden)} 项，INPUT_DIR={INPUT_DIR})")
    else:
        pass
except Exception as e:
    print(f"⚠️ 读取 config.py 失败: {e}")


def ensure_configured():
    """确认已完成初始化并存在有效路径配置。"""
    required = {
        "BASE_ROOT": BASE_ROOT,
        "INPUT_DIR": INPUT_DIR,
        "DONE_DIR": DONE_DIR,
        "REVIEW_DIR": REVIEW_DIR,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        print("❌ 未完成初始化：缺少路径配置 " + ", ".join(missing))
        print("请先运行：python3 setup.py init")
        return False
    return True


def is_business_file(path):
    """判断是否为待处理/已归档的发票业务文件，排除日志和台账。"""
    return (
        os.path.isfile(path)
        and not os.path.basename(path).startswith('.')
        and os.path.splitext(path)[1].lower() in BUSINESS_FILE_EXTENSIONS
    )

# 标准文件名正则 (确保在 config 覆盖后是最新版本)
STANDARD_NAME_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2})_(' + '|'.join(re.escape(c) for c in VALID_CATEGORIES) + r')_(\d+\.\d{2})'
    r'(?:_([^_\d]+(?:-[^_\d]+)?(?:_[\u4e00-\u9fa5]{2,10})?))?'   # Optional route/city + buyer: 出发地-到达地_购买方简称
    r'(?:_(\d{1,4}))?'            # Optional suffix: 发票号后4位或序号
    r'(?:_(\d{4})_(WB|YB))?'      # Optional status: 操作日期_报销状态(WB未报/YB已报)
    r'(?:_(\d{3}))?'              # Optional seq: 序号编号(3位数字)
    r'(\.\w+)$'
)

# 生成报销状态后缀: 当前日期MMDD + WB(未报)
def make_status_suffix():
    """返回当前日期的报销状态后缀，如 _0621_WB"""
    now = datetime.now()
    return f"_{now.month:02d}{now.day:02d}_WB"

def get_next_seq_number():
    """扫描03已完成目录，返回下一个可用序号（从文件末尾_NNN提取）"""
    max_seq = 0
    for month_dir_name in os.listdir(DONE_DIR):
        month_path = os.path.join(DONE_DIR, month_dir_name)
        if not os.path.isdir(month_path):
            continue
        for fname in os.listdir(month_path):
            # 新格式: ..._WB/YB_NNN.ext 或 ..._NNN.ext 末尾
            m = re.search(r'_(\d{3})\.\w+$', fname)
            if m:
                seq = int(m.group(1))
                if seq > max_seq:
                    max_seq = seq
            # 兼容旧格式: NNN_开头
            m2 = re.match(r'^(\d{3})_', fname)
            if m2:
                seq = int(m2.group(1))
                if seq > max_seq:
                    max_seq = seq
    return max_seq + 1

# ===== 分类规则（按 SOP-发票文件命名标准.md）=====
# 每条规则: (关键词列表, 基础类别)
# 子类型由 classify_with_subtype() 在基础类别基础上根据二次判定决定
# 如 config.py 已定义，此处不再重复定义
if 'CATEGORY_RULES' not in dir():
    CATEGORY_RULES = [
        (["结账单", "水单"], "结账单"),
        (["行程单", "行程报销单", "出行记录", "出行行程"], "行程单"),
        (["住宿", "酒店", "华住", "全季", "青之韵", "入住", "房费", "上海瓯江源", "离店"], "住宿"),
        (["蟹", "手信", "礼品", "新年", "淡水蟹", "淡水产品", "安琪",
          "日用杂品", "日用品", "日化用品", "礼盒", "水果", "玩具",
          "移动通信设备", "通讯器材", "通讯器材及配件"], "礼品"),
        (["高速", "通行费", "车辆通行", "路桥费", "收费站", "ETC", "高速费"], "高速费"),
        (["充电", "蔚来", "NIO", "换电", "充电桩", "充电费"], "充电费"),
        (["滴滴", "打车", "网约车", "交通运输服务", "客运服务费"], "滴滴打车"),
        (["火车票", "高铁", "车票", "C3775", "二等座", "铁路", "电子客票", "一等座"], "高铁"),
        (["机票", "航空", "航班", "登机牌", "CA ", "CZ ", "MU ", "HU ",
          "保险服务", "航意航延组合险标准计划", "经纪代理服务", "退票费"], "机票"),
        (["招待", "餐饮", "餐费", "就餐", "餐厅", "饭店", "酒家", "饮食", "菜品",
          "江鱼儿", "晶晶", "酒", "白酒", "洋酒", "红酒", "啤酒", "酒水"], "餐饮"),
    ]

# ===== 子类型判定规则 =====
# 在基础类别确定后，根据特定关键词决定是否追加子类型标签
# 如 config.py 已定义，此处不再重复定义
if 'SUBTYPE_RULES' not in dir():
    SUBTYPE_RULES = [
        # 机票类中出现保险关键词 → "机票(保险)"
        ("机票", ["保险服务", "航意航延组合险标准计划", "航意险", "保险"], "(保险)"),
        # 行程单类中出现滴滴关键词 → 归为"滴滴打车(行程单)"
        ("行程单", ["滴滴", "打车", "网约车", "交通运输服务", "客运服务费"], "(行程单)"),
        # 行程单类中出现高速关键词 → 归为"高速费(行程单)"
        ("行程单", ["高速", "通行费", "路桥费", "ETC", "车辆通行费"], "(行程单)"),
        # 结账单类中出现酒店/住宿关键词 → 归为"住宿(结账单)"
        ("结账单", ["酒店", "住宿", "入住", "离店", "华住", "全季", "房费"], "(结账单)"),
    ]

# ===== 提取函数 =====

def extract_pdf_text(filepath):
    try:
        return pdfminer_extract_text(filepath)
    except:
        return ""


def extract_image_text(filepath):
    """从图片文件中通过OCR提取文本内容，用于纸质发票拍照
    
    使用pytesseract(Pillow+Tesseract OCR)识别图片中的文字。
    支持中文+英文混合识别(lang='chi_sim+eng')。
    若OCR不可用或识别失败，返回空字符串（文件将移至02待核实）。
    """
    if not OCR_AVAILABLE or not PIL_AVAILABLE:
        return ""
    try:
        img = Image.open(filepath)
        # HEIC格式需要额外处理(有些PIL版本不支持直接读取)
        # 转换为RGB模式确保兼容性
        if img.mode not in ('RGB', 'L', '1'):
            img = img.convert('RGB')
        # 使用中文+英文混合识别
        text = pytesseract.image_to_string(img, lang='chi_sim+eng')
        return text.strip()
    except Exception as e:
        print(f"   ⚠️ OCR识别失败: {e}")
        return ""


def extract_ofd_text(filepath):
    """从OFD文件(ZIP包)中提取发票文本内容，用于日期/金额/类别提取
    
    OFD是ZIP格式，内嵌XML描述发票内容。TextCode标签包含可见文本，
    附件XML包含结构化数据(如铁路客票的rai命名空间)。
    """
    try:
        with zipfile.ZipFile(filepath) as z:
            all_xml = ''
            for name in z.namelist():
                if name.endswith('.xml'):
                    try:
                        content = z.read(name).decode('utf-8')
                        all_xml += content + '\n'
                    except:
                        pass
            
            # 提取TextCode可见文本（发票页面上的文字）
            texts = re.findall(r'<ofd:TextCode[^>]*>([^<]+)</ofd:TextCode>', all_xml)
            visible_text = ' '.join(t.strip() for t in texts)
            
            # 合并：可见文本 + 原始XML（用于结构化数据提取如JSHJ/rai等）
            combined = visible_text + '\n' + all_xml
            return combined
    except:
        return ""


def convert_ofd_to_pdf(ofd_path, pdf_path):
    """将OFD文件转换为PDF（使用PyMuPDF渲染页面为图像再嵌入PDF）
    
    注意：转换后的PDF是图像型，无文字层。脚本应在转换前先从OFD提取文本数据。
    """
    if not FITZ_AVAILABLE:
        return False
    try:
        doc = fitz.open(ofd_path, filetype='ofd')
        pdf_doc = fitz.open()
        
        for i in range(doc.page_count):
            page = doc[i]
            # 渲染页面为高清图像
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes('png')
            
            # 创建PDF页面并嵌入图像
            rect = page.rect
            scale = 3  # 放大3倍保证清晰度
            new_page = pdf_doc.new_page(width=rect.width * scale, height=rect.height * scale)
            new_page.insert_image(new_page.rect, stream=img_bytes)
        
        pdf_doc.save(pdf_path)
        pdf_doc.close()
        doc.close()
        return os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0
    except:
        return False


def extract_xml_text(filepath):
    """从XML发票文件中提取发票文本内容（用于日期/金额/类别提取）

    XML发票格式为<EInvoice>，包含结构化字段:
    - Header/EIid: 发票号码
    - EInvoiceData/SellerInformation/SellerName: 销方名称
    - EInvoiceData/BuyerInformation/BuyerName: 购方名称
    - EInvoiceData/BasicInformation/TotalTax-includedAmount: 价税合计
    - EInvoiceData/BasicInformation/RequestTime: 开票时间
    - EInvoiceData/IssuItemInformation/ItemName: 商品名称
    - TaxSupervisionInfo/InvoiceNumber: 发票号码
    - TaxSupervisionInfo/IssueTime: 开票日期
    """
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()

        # 构造纯文本用于classify()等函数的文本匹配
        text_parts = []

        # 递归提取所有文本节点
        for elem in root.iter():
            if elem.text and elem.text.strip():
                text_parts.append(elem.text.strip())
            if elem.tail and elem.tail.strip():
                text_parts.append(elem.tail.strip())

        combined = ' '.join(text_parts)
        return combined
    except:
        # XML解析失败时尝试读取原始文本
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except:
            try:
                with open(filepath, 'r', encoding='gbk') as f:
                    return f.read()
            except:
                return ""


def extract_xml_fields(filepath):
    """从XML发票提取结构化字段（用于PDF生成）

    返回dict包含: invoice_number, seller_name, buyer_name, amount, amount_cn,
                  issue_time, item_name, item_amount, tax_rate, tax_amount,
                  remark, tax_bureau_name
    """
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        fields = {}

        # 发票号码 (两个位置: Header/EIid 和 TaxSupervisionInfo/InvoiceNumber)
        eiid = root.find('.//Header/EIid')
        inv_num = root.find('.//TaxSupervisionInfo/InvoiceNumber')
        fields['invoice_number'] = (inv_num.text if inv_num is not None and inv_num.text
                                    else eiid.text if eiid is not None and eiid.text
                                    else '')

        # 销方信息
        seller = root.find('.//EInvoiceData/SellerInformation/SellerName')
        fields['seller_name'] = seller.text if seller is not None and seller.text else ''

        # 购方信息
        buyer = root.find('.//EInvoiceData/BuyerInformation/BuyerName')
        fields['buyer_name'] = buyer.text if buyer is not None and buyer.text else ''

        # 金额信息
        total = root.find('.//EInvoiceData/BasicInformation/TotalTax-includedAmount')
        fields['amount'] = total.text if total is not None and total.text else ''
        total_cn = root.find('.//EInvoiceData/BasicInformation/TotalTax-includedAmountInChinese')
        fields['amount_cn'] = total_cn.text if total_cn is not None and total_cn.text else ''

        # 开票日期/时间
        req_time = root.find('.//EInvoiceData/BasicInformation/RequestTime')
        issue_time = root.find('.//TaxSupervisionInfo/IssueTime')
        fields['issue_time'] = (req_time.text if req_time is not None and req_time.text
                                else issue_time.text if issue_time is not None and issue_time.text
                                else '')

        # 商品名称（可能有多个Item）
        items = root.findall('.//EInvoiceData/IssuItemInformation/ItemName')
        fields['item_name'] = '; '.join([i.text for i in items if i.text]) if items else ''

        # 商品金额
        item_amt = root.find('.//EInvoiceData/IssuItemInformation/Amount')
        fields['item_amount'] = item_amt.text if item_amt is not None and item_amt.text else ''

        # 税率
        tax_rate = root.find('.//EInvoiceData/IssuItemInformation/TaxRate')
        fields['tax_rate'] = tax_rate.text if tax_rate is not None and tax_rate.text else ''

        # 税额
        tax_am = root.find('.//EInvoiceData/IssuItemInformation/ComTaxAm')
        fields['tax_amount'] = tax_am.text if tax_am is not None and tax_am.text else ''

        # 备注
        remark = root.find('.//EInvoiceData/AdditionalInformation/Remark')
        fields['remark'] = remark.text if remark is not None and remark.text else ''

        # 税务机关
        bureau = root.find('.//TaxSupervisionInfo/TaxBureauName')
        fields['tax_bureau_name'] = bureau.text if bureau is not None and bureau.text else ''

        # 不含税金额
        no_tax = root.find('.//EInvoiceData/BasicInformation/TotalAmWithoutTax')
        fields['amount_no_tax'] = no_tax.text if no_tax is not None and no_tax.text else ''

        # 开票人
        drawer = root.find('.//EInvoiceData/BasicInformation/Drawer')
        fields['drawer'] = drawer.text if drawer is not None and drawer.text else ''

        return fields
    except:
        return {}


def convert_xml_to_pdf(xml_path, pdf_path):
    """将XML发票数据生成为PDF（使用fpdf2+Arial Unicode中文字体）

    生成的PDF包含发票核心信息，排版为简化版发票格式（信息摘要型）。
    """
    if not FPDF_AVAILABLE:
        return False

    fields = extract_xml_fields(xml_path)
    if not fields:
        return False

    # 中文字体路径
    chinese_font_path = '/Library/Fonts/Arial Unicode.ttf'
    if not os.path.exists(chinese_font_path):
        chinese_font_path = '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'
    if not os.path.exists(chinese_font_path):
        return False

    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # 注册中文字体
        pdf.add_font('CNFont', '', chinese_font_path)
        pdf.add_font('CNFont', 'B', chinese_font_path)

        # 标题
        pdf.set_font('CNFont', 'B', 14)
        pdf.cell(0, 10, '电子发票（XML格式自动转换）', new_x='LMARGIN', new_y='NEXT', align='C')
        pdf.ln(3)

        label_width = 45
        value_width = 145

        def add_row(label, value):
            pdf.set_font('CNFont', 'B', 9)
            pdf.cell(label_width, 7, label, border=1)
            pdf.set_font('CNFont', '', 9)
            safe_value = str(value) if value else ''
            pdf.cell(value_width, 7, safe_value, border=1, new_x='LMARGIN', new_y='NEXT')

        add_row('发票号码:', fields.get('invoice_number', ''))
        add_row('销方名称:', fields.get('seller_name', ''))
        add_row('购方名称:', fields.get('buyer_name', ''))
        add_row('开票日期:', fields.get('issue_time', ''))
        add_row('商品名称:', fields.get('item_name', ''))
        add_row('不含税金额:', fields.get('amount_no_tax', ''))
        add_row('税率:', fields.get('tax_rate', ''))
        add_row('税额:', fields.get('tax_amount', ''))
        add_row('价税合计:', fields.get('amount', ''))
        add_row('大写金额:', fields.get('amount_cn', ''))
        add_row('备注:', fields.get('remark', ''))
        add_row('税务机关:', fields.get('tax_bureau_name', ''))
        add_row('开票人:', fields.get('drawer', ''))

        pdf.ln(8)
        pdf.set_font('CNFont', '', 7)
        pdf.cell(0, 5, '此PDF由发票整理脚本从XML数据自动生成，为信息摘要型PDF，非官方版式。', new_x='LMARGIN', new_y='NEXT', align='C')

        pdf.output(pdf_path)
        return os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0
    except:
        return False


def extract_date_from_text(text):
    m = re.search(r'开票日期[：:]\s*(\d{4})\D+(\d{1,2})\D+(\d{1,2})', text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}"
    m = re.search(r'(\d{4})年\s*(\d{2})月\s*(\d{2})日', text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r'(\d{4})\D+(\d{2})\D+(\d{2})\D', text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}"
    return None


def extract_trip_date_for_jp(text):
    """机票类专用：提取行程日期（优先级高于开票日期）

    优先级:
    1. 携程订单行中的行程日期 (如 "携程订单:...,2025/12/23 上海-长春 CZ6542")
    2. 备注/行程日期字段
    3. 航班日期/出发日期
    4. 无行程日期时返回None，使用开票日期
    """
    # 1. 携程订单行中的行程日期
    m = re.search(r'携程订单[^,]*,(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})\s', text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}", "携程订单行程日期"

    # 2. 备注行程日期
    m = re.search(r'(备注|行程)[^的]*日期[：:\s]*(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})[日]?', text)
    if m:
        y, mo, d = int(m.group(2)), int(m.group(3)), int(m.group(4))
        if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}", "备注行程日期"

    # 3. 航班日期
    m = re.search(r'航班日期[：:\s]*(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})[日]?', text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}", "航班日期"

    # 4. 出发日期
    m = re.search(r'出发日期[：:\s]*(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})[日]?', text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}", "出发日期"

    return None, "无行程日期"


def extract_trip_date_for_gaotie(text):
    """高铁类专用：提取开车日期（优先级高于开票日期）

    优先级:
    1. OFD铁路客票 rai:TravelDate字段 (乘车日期)
    2. PDF "XXXX年XX月XX日 XX:XX开" 格式
    3. PDF 内联格式 车次+日期 (如 "G1639 2026年01月06日 18:41开")
    4. 乘车日期/出发时间字段
    5. 无开车日期时返回None，使用开票日期
    """
    # 1. rai:TravelDate (OFD铁路客票)
    m = re.search(r'TravelDate[^>]*>([^<]+)<', text)
    if m:
        dt = m.group(1).strip()
        dm = re.match(r'(\d{4})-(\d{2})-(\d{2})', dt)
        if dm:
            y, mo, d = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
            if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y}-{mo:02d}-{d:02d}", "rai:TravelDate"

    # 2. PDF "XXXX年XX月XX日 XX:XX开" 格式 (最常见)
    m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}:\d{2})开', text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}", f"开车日期({m.group(4)}开)"

    # 3. 内联格式: 车次+日期+时间开 (如 "G1639 2026年01月06日 18:41开")
    m = re.search(r'[A-Z]\d+\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}:\d{2})开', text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}", f"内联开车日期({m.group(4)}开)"

    # 4. 乘车日期字段
    m = re.search(r'乘车日期[：:\s]*(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})[日]?', text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}", "乘车日期"

    # 5. 出发时间字段 (包含日期)
    m = re.search(r'出发时间[：:\s]*(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})[日]?', text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}", "出发时间"

    return None, "无开车日期"


def extract_invoice_number(text):
    nums26 = re.findall(r'(?<!\d)2[56]\d{18}(?!\d)', text)
    if nums26:
        return nums26[0], "26-prefix"
    m = re.search(r'发票号码[：:\s]+(\d{8,20})', text)
    if m: return m.group(1), "text"
    return None


def extract_seller_name_from_text(text):
    """从PDF/OFD文本提取销售方名称（酒店主体名）
    
    PDF文本中"名称："出现两次：第一次=购方，第二次=销方
    返回销方名称字符串，找不到返回None
    """
    if not text:
        return None
    # 找所有"名称："位置
    positions = []
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if re.match(r'^名称[：:]', line.strip()):
            positions.append(i)
    
    # 销方名称在第二处"名称"之后
    if len(positions) >= 2:
        seller_pos = positions[1]
        # 名称后面可能有空行，找下一个非空行
        for j in range(seller_pos + 1, min(seller_pos + 5, len(lines))):
            content = lines[j].strip()
            if content and len(content) > 4 and not content.startswith('统一社会') and not content.startswith('9'):
                return content
    
    # 降级: 直接用"销售方名称"字段 (OFD/XML格式)
    m = re.search(r'销售方名称[：:\s]+(.+)', text)
    if m:
        return m.group(1).strip()
    
    # 再降级: "销方" + "名称" 模式
    m = re.search(r'销.*方.*名称[：:\s]*(.+)', text)
    if m:
        return m.group(1).strip()
    
    return None


def extract_buyer_name_from_text(text):
    """从PDF/OFD文本提取购买方（买方）名称
    
    PDF文本中"名称："出现两次：第一次=购方，第二次=销方
    返回购方名称字符串，找不到返回None
    """
    if not text:
        return None
    lines = text.split('\n')
    
    # 找所有"名称："位置
    positions = []
    for i, line in enumerate(lines):
        if re.match(r'^名称[：:]', line.strip()):
            after = ''
            if '：' in line:
                after = line.split('：', 1)[1].strip()
            elif ':' in line:
                after = line.split(':', 1)[1].strip()
            positions.append((i, after if after else None))
    
    # 第一处"名称"=购方
    if positions:
        buyer_pos, buyer_name = positions[0]
        if buyer_name and len(buyer_name) > 3:
            return buyer_name
        # 名称后内容在下一非空行
        for j in range(buyer_pos + 1, min(buyer_pos + 5, len(lines))):
            content = lines[j].strip()
            if content and len(content) > 3 and not content.startswith('统一社会') and not content.startswith('9') and not content.startswith('名称'):
                return content
    
    # 降级: "购买方名称：" / "购方名称："
    m = re.search(r'(?:购买方|购方)名称[：:\s]+(.+)', text)
    if m:
        name = m.group(1).strip()
        if len(name) > 3:
            return name
    
    return None


def shorten_company_name(name):
    """将公司全称转为简称
    
    例：
    - 上海乐纯生物技术股份有限公司 → 乐纯生物
    - 北京金达阳光科技有限公司 → 金达阳光
    - 中国石油化工股份有限公司 → 中石化
    """
    if not name:
        return ""
    
    s = name.strip()
    
    # 去除常见省市区前缀
    prefixes = ['中国', '北京', '上海', '广州', '深圳', '广东', '天津', '重庆',
                '浙江', '江苏', '四川', '山东', '湖北', '湖南', '福建', '安徽',
                '河南', '河北', '陕西', '辽宁', '吉林', '黑龙江', '云南', '贵州',
                '广西', '山西', '甘肃', '内蒙古', '新疆', '西藏', '宁夏', '青海',
                '海南', '江西']
    for p in prefixes:
        if s.startswith(p) and len(s) > len(p) + 2:
            s = s[len(p):]
            # 去除"省"/"市"后缀
            if s.startswith('省') or s.startswith('市'):
                s = s[1:]
            break
    
    # 去除常见公司类型后缀（从长到短匹配）
    suffixes = ['股份有限公司', '有限责任公司', '科技有限公司',
                '有限公司', '分公司', '公司', '集团']
    for suf in suffixes:
        if s.endswith(suf) and len(s) > len(suf) + 1:
            s = s[:-len(suf)]
            break
    
    # 去除常见尾部描述词
    tail_words = ['技术', '科技', '服务', '贸易', '工程', '实业',
                  '投资', '发展', '管理', '控股']
    for tw in tail_words:
        if s.endswith(tw) and len(s) > len(tw) + 1:
            s = s[:-len(tw)]
            break
    
    s = s.strip()
    
    # 结果太长(>6字)时取前4字
    if len(s) > 6:
        s = s[:4]
    
    # 结果为空或太短(<=1字)时，取原名前4字
    if len(s) <= 1:
        s = name[:4].strip()
    
    return s


# 主要城市列表（用于住宿发票与结账单的城市配对）
# 如 config.py 已定义，此处不再重复定义
if 'MAJOR_CITIES' not in dir():
    MAJOR_CITIES = ['上海','苏州','杭州','广州','成都','重庆','南京','北京','深圳',
                    '长春','无锡','常州','武汉','西安','天津','长沙','郑州','合肥',
                    '昆明','厦门','青岛','大连','宁波','中山']


def extract_city_from_text(text):
    """从发票文本提取城市关键词列表
    
    来源: seller_name中的城市 + 地址行中的城市 + 其他上下文中的城市
    住宿配对时用城市做辅助匹配，避免同金额跨城市误配
    """
    if not text:
        return []
    cities = []
    for city in MAJOR_CITIES:
        if city in text:
            cities.append(city)
    # 补充: seller_name中可能包含城市
    seller = extract_seller_name_from_text(text)
    if seller:
        for city in MAJOR_CITIES:
            if city in seller and city not in cities:
                cities.append(city)
    return cities


HOTEL_CITY_KEYWORDS = [
    "酒店", "宾馆", "住宿", "客栈", "旅店", "饭店", "公寓", "民宿",
    "华住", "全季", "汉庭", "如家", "亚朵", "维也纳", "锦江", "丽枫",
    "希尔顿", "万豪", "喜来登", "皇冠假日", "智选假日"
]


def _first_city_in_text(text):
    """返回文本中第一个城市名。"""
    if not text:
        return None
    for city in MAJOR_CITIES:
        if city in text:
            return city
    return None


def extract_lodging_city(text):
    """住宿类发票专用：提取酒店所在城市，用于文件名中的位置字段。

    优先级：
    1. 销售方名称中的城市；
    2. 包含酒店/住宿关键词的行；
    3. 地址/销售方地址字段；
    4. 全文城市关键词兜底。
    """
    if not text:
        return None

    seller = extract_seller_name_from_text(text)
    city = _first_city_in_text(seller)
    if city:
        return city

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if any(keyword in line for keyword in HOTEL_CITY_KEYWORDS):
            city = _first_city_in_text(line)
            if city:
                return city

    for pattern in [
        r'(?:销售方)?地址[：:\s]*(.+)',
        r'销方地址[：:\s]*(.+)',
        r'经营地址[：:\s]*(.+)',
    ]:
        for m in re.finditer(pattern, text):
            city = _first_city_in_text(m.group(1))
            if city:
                return city

    cities = extract_city_from_text(text)
    return cities[0] if cities else None


def extract_stay_date_from_text(text):
    """住宿发票专用：提取入住日期（优先级高于开票日期）
    
    住宿发票的开票日期可能延后数月，入住日期才是真实发生日期。
    提取优先级:
    1. 明确的入住日期字段 (如 "入住日期：2026年01月05日")
    2. 日期范围中的入住日期 (如 "2026/01/05-2026/01/06")
    3. 备注/项目描述中的入住日期
    4. 无入住日期时返回None，使用开票日期或配对推断
    """
    if not text:
        return None, "无文本"
    
    # 1. 明确入住日期字段
    m = re.search(r'入住日期[：:\s]*(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})', text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}", "入住日期字段"
    
    # 2. 日期范围 (入住-离店)
    m = re.search(r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})\s*[-—至到]\s*(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}", "入住日期范围"
    
    # 3. 日期范围 (只有月日)
    m = re.search(r'(\d{1,2})[/\-](\d{1,2})\s*[-—至到]\s*(\d{1,2})[/\-](\d{1,2})', text)
    if m:
        # 需要从开票日期推断年份
        issue_date = extract_date_from_text(text)
        if issue_date:
            year = int(issue_date[:4])
            mo, d = int(m.group(1)), int(m.group(2))
            # 入住日期的月份通常比开票日期早
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{year}-{mo:02d}-{d:02d}", "入住日期范围(月日)"
    
    # 4. 项目描述中的"XX天"前可能有日期
    m = re.search(r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})[^\d]*天', text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}", "项目描述日期"
    
    return None, "无入住日期"


def find_matching_invoice_for_checkout(checkout_text, amount, zs_invoice_index, indent="   "):
    """住宿(结账单)反向配对: 用结账单信息在03已完成中查找对应发票
    
    匹配维度: 金额+城市(优先) → 纯金额(降级)
    返回: (paired_date, paired_fn, paired_seller) 或 (None, None, None)
    
    v3.25: 当只有住宿结账单/水单时，反向查找03已完成中是否有匹配的住宿发票文件
    """
    if not amount or not zs_invoice_index:
        return None, None, None
    
    checkout_cities = extract_city_from_text(checkout_text) if checkout_text else []
    checkout_seller = extract_seller_name_from_text(checkout_text) if checkout_text else None
    amt_val = float(amount.replace(',','')) if isinstance(amount, str) else float(amount)
    
    paired_date = None
    paired_fn = None
    paired_seller = None
    
    # 1. 优先: 金额+城市匹配
    if checkout_cities:
        for city in checkout_cities:
            zs_key = f"{amt_val:.2f}_{city}"
            if zs_key in zs_invoice_index:
                for pd, pfn, ps in zs_invoice_index[zs_key]:
                    paired_date, paired_fn, paired_seller = pd, pfn, ps
                    seller_info = f"酒店={ps}" if ps else ""
                    print(f"{indent}🔗 住宿结账单反向配对→发票 {paired_fn} (金额={amt_val:.2f} + 城市={city} {seller_info})")
                    break  # 取第一个匹配
                if paired_date:
                    break
    
    # 2. 降级: 金额+城市列表匹配
    if not paired_date and checkout_cities:
        cities_str = ','.join(sorted(checkout_cities))
        zs_key = f"{amt_val:.2f}_{cities_str}"
        if zs_key in zs_invoice_index and len(zs_invoice_index[zs_key]) == 1:
            paired_date, paired_fn, paired_seller = zs_invoice_index[zs_key][0]
            print(f"{indent}🔗 住宿结账单反向配对(城市列表)→发票 {paired_fn} (金额={amt_val:.2f} + 城市={cities_str})")
    
    # 3. 最终降级: 纯金额匹配(只有1条时才用)
    if not paired_date:
        zs_key = f"{amt_val:.2f}_"
        if zs_key in zs_invoice_index and len(zs_invoice_index[zs_key]) == 1:
            paired_date, paired_fn, paired_seller = zs_invoice_index[zs_key][0]
            print(f"{indent}🔗 住宿结账单反向配对(降级)→发票 {paired_fn} (金额={amt_val:.2f})")
    
    if not paired_date:
        print(f"{indent}⚠️ 住宿结账单未找到对应发票 (金额={amt_val:.2f})")
    
    return paired_date, paired_fn, paired_seller


# ===== 出发地-到达地提取（机票类和高铁类） =====
# 高铁站名英文→中文映射
STATION_EN_MAP = {
    "Shanghaihongqiao": "上海虹桥", "Shanghai": "上海", "Hangzhoudong": "杭州东", "Hangzhou": "杭州",
    "Nanjingnan": "南京南", "Nanjing": "南京", "Kunshannan": "昆山南", "Kunshan": "昆山",
    "Chengdudong": "成都东", "Chengdu": "成都", "Chongqingxi": "重庆西", "Chongqing": "重庆",
    "Guangzhounan": "广州南", "Guangzhoudong": "广州东", "Guangzhou": "广州",
    "Nantongxi": "南通西", "Nantong": "南通",
    "Suzhoubei": "苏州北", "Suzhouyuanqu": "苏州园区", "Suzhou": "苏州",
    "Zhongshanbei": "中山北", "Zhongshan": "中山",
    "Changchun": "长春", "Shenzhenbei": "深圳北", "Shenzhen": "深圳",
    "Beijingnan": "北京南", "Beijing": "北京", "Hefeinan": "合肥南", "Hefei": "合肥",
    "Wuhan": "武汉", "Qingdao": "青岛", "Jinan": "济南", "Xian": "西安",
    "Shenyang": "沈阳", "Harbin": "哈尔滨", "Dalian": "大连",
    "Wenzhou": "温州", "Ningbo": "宁波", "Fuzhou": "福州",
    "Xiamen": "厦门", "Guiyang": "贵阳", "Kunming": "昆明",
    "Nanning": "南宁", "Haikou": "海口", "Sanya": "三亚",
    "Lhasa": "拉萨", "Urumqi": "乌鲁木齐", "Lanzhou": "兰州",
}
STATION_CN_RE = re.compile(
    r'(上海虹桥|上海|杭州东|杭州|南京南|南京|昆山南|昆山|成都东|成都|重庆西|重庆|'
    r'广州南|广州东|广州|南通西|南通|苏州北|苏州园区|苏州|中山北|中山|长春|深圳北|深圳|'
    r'北京南|北京|合肥南|合肥|武汉|青岛|西安|济南|沈阳|哈尔滨|大连|温州|宁波|福州|厦门|'
    r'贵阳|昆明|南宁|海口|三亚|拉萨|乌鲁木齐|兰州|珠海|汕头|湛江|烟台|威海|义乌|常州)'
    r'(?:站)?'
)
# 12306服务费发票关键词（无路线信息）
SERVICE_FEE_KEYWORDS = ["信息系统增值服务", "服务费"]


def extract_route_for_jp(text, cat):
    """机票类：提取出发地-到达地
    
    优先级:
    1. 携程订单行 (如 "携程订单:...,2026/4/21 广州-上海 CA8328")
    2. PDF文本中的城市-城市模式 (如 "广州-上海")
    3. 无路线信息时返回None (保险发票无路线)
    """
    # 保险发票无路线
    if cat == "机票(保险)":
        return None
    
    # 1. 携程订单行
    ctrip = re.search(r'携程订单.*?,\s*\d{4}/\d{1,2}/\d{1,2}\s*(\S+?)\s*-\s*(\S+?)\s+\w?\d+', text)
    if ctrip:
        return f"{ctrip.group(1).strip()}-{ctrip.group(2).strip()}"
    
    # 2. 城市对模式
    cities = r'(北京|上海|广州|深圳|成都|重庆|杭州|南京|长春|昆明|长沙|武汉|西安|郑州|青岛|大连|厦门|贵阳|兰州|乌鲁木齐|合肥|宁波|温州|南宁|海口|三亚|福州|无锡|常州|苏州|天津|石家庄|太原|呼和浩特|哈尔滨|沈阳|济南|珠海|汕头|湛江|烟台|威海)'
    m = re.search(f'{cities}\\s*[-→]\\s*{cities}', text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    
    return None


def extract_route_for_gaotie(text, cat):
    """高铁类：提取出发地-到达地
    
    优先级:
    1. PDF文本中的车站名对 (含英文站名映射)
    2. OFD rai命名空间的DepartureStation/DestinationStation
    3. 12306服务费发票无路线 → 返回None
    
    注意: pdfminer提取顺序可能与视觉不同，使用车次号定位来判断出发/到达顺序
    """
    # 12306服务费发票无路线
    if any(kw in text[:200] for kw in SERVICE_FEE_KEYWORDS):
        return None
    
    # 提取中文站名
    cn_stations = STATION_CN_RE.findall(text)
    # 提取英文站名并转中文
    en_cn_stations = []
    for en, cn in STATION_EN_MAP.items():
        if en in text:
            en_cn_stations.append(cn)
    all_stations = list(set(cn_stations + en_cn_stations))
    
    if len(all_stations) < 2:
        # 无足够站点信息
        return None
    
    # 确定方向: 用车次号分隔出发站和到达站
    train_match = re.search(r'(G\d+|D\d+|C\d+)', text)
    if train_match and len(all_stations) >= 2:
        train_pos = text.find(train_match.group(1))
        before = text[:train_pos]
        after = text[train_pos:]
        
        dep_candidates = [s for s in all_stations if s in before or any(e in before for e, c in STATION_EN_MAP.items() if c == s)]
        arr_candidates = [s for s in all_stations if s in after or any(e in after for e, c in STATION_EN_MAP.items() if c == s)]
        
        if dep_candidates and arr_candidates and dep_candidates != arr_candidates:
            return f"{dep_candidates[0]}-{arr_candidates[0]}"
    
    # Fallback: 如果正好2个站名，使用文本位置排序
    if len(all_stations) == 2:
        pos_map = {}
        for st in all_stations:
            idx = text.find(st)
            if idx == -1:
                for en, cn in STATION_EN_MAP.items():
                    if cn == st:
                        idx = text.find(en)
                        break
            pos_map[st] = idx
        sorted_stations = sorted(all_stations, key=lambda s: pos_map.get(s, 999))
        # 高铁PDF末尾站名顺序通常为: 到达站-出发站 (与视觉相反)
        # 所以反转顺序
        return f"{sorted_stations[1]}-{sorted_stations[0]}"
    
    return None


def extract_route(text, cat):
    """统一路线提取入口: 根据类别调用对应提取函数"""
    base_cat = cat.split("(")[0] if "(" in cat else cat
    if base_cat == "机票":
        return extract_route_for_jp(text, cat)
    elif base_cat == "高铁":
        return extract_route_for_gaotie(text, cat)
    elif base_cat == "住宿":
        return extract_lodging_city(text)
    return None


def extract_amount_from_text(text):
    # 策略1: 价税合计 + ¥
    for m in re.finditer(r'价税合计[\s\S]{0,200}', text):
        seg = m.group(0)
        amts = re.findall(r'[¥￥]\s*([\d,]+\.\d{2})', seg)
        if amts:
            return max(float(a.replace(',','')) for a in amts).__format__('.2f')
    # 策略2: 小写金额（¥在后面，如"（ 小 写 ） 177.90 ¥"）
    m = re.search(r'[\(（]\s*小写\s*[)）]\s*([\d,]+\.\d{2})', text)
    if m:
        return m.group(1).replace(',', '')
    # 策略3: 大写+¥小写
    m = re.search(r'[零壹贰叁肆伍陆柒捌玖拾佰仟万亿圆元整]{2,}[\s]*[¥￥]\s*([\d,]+\.\d{2})', text)
    if m:
        return m.group(1).replace(',', '')
    # 策略4: (小写)¥
    m = re.search(r'[\(（]小写[\)）][\s\S]{0,30}[¥￥]\s*([\d,]+\.\d{2})', text)
    if m:
        return m.group(1).replace(',', '')
    # 策略5: ¥金额取最大
    amounts = re.findall(r'[¥￥]\s*([\d,]+\.\d{2})', text)
    if amounts:
        nums = [float(a.replace(',', '')) for a in amounts]
        return f"{max(nums):.2f}"
    # 策略6: 消费合计（结账单，多行分隔）
    m = re.search(r'消费合计[\s\n]*([\d,]+\.\d{2})', text)
    if m:
        return m.group(1).replace(',', '')
    # 策略7: 合计X元（行程单）
    m = re.search(r'合计([\d,]+\.\d{2})元', text)
    if m:
        return m.group(1).replace(',', '')
    # 策略8: 金额（元）/ 交易金额(元) 格式（高速费通行费等）
    m = re.search(r'金额[（(]元[）)][：:\s]*([\d,]+\.\d{2})', text)
    if m:
        return m.group(1).replace(',', '')
    m = re.search(r'交易金额[（(]元[）)][：:\s]*([\d,]+\.\d{2})', text)
    if m:
        return m.group(1).replace(',', '')
    # 策略9: 所有数字金额取最大（>10，避免提取序号等）
    amts = re.findall(r'([\d,]+\.\d{2})', text)
    if amts:
        nums = [float(a.replace(',', '')) for a in amts if float(a.replace(',', '')) > 10]
        if nums:
            return f"{max(nums):.2f}"
    return None


def extract_date_from_filename(filename):
    m = re.search(r'(\d{4})(\d{2})(\d{2})\d{6}', filename)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= y <= 2030:
            return f"{y}-{mo:02d}-{d:02d}"
    m = re.search(r'(\d{4})[-./](\d{1,2})[-./](\d{1,2})', filename)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}"
    m = re.search(r'水单(\d{2})(\d{2})', filename)
    if m:
        return f"2026-{m.group(1)}-{m.group(2)}"
    m = re.search(r'结账单(\d{4})(\d{2})(\d{2})', filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r'(\d{1,2})[.月](\d{1,2})', filename)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"2026-{mo:02d}-{d:02d}"
    m = re.search(r'(\d{1,2})月(\d{1,2})[日号]', filename)
    if m:
        return f"2026-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
    m = re.search(r'(\d{1,2})月', filename)
    if m:
        return f"2026-{m.group(1).zfill(2)}-01"
    return None


def extract_amount_from_filename(filename):
    m = re.search(r'[¥￥](\d+\.?\d{0,2})', filename)
    if m:
        val = float(m.group(1))
        if 0 < val < 100000:
            return f"{val:.2f}"
    m = re.search(r'(\d+\.?\d{0,2})\s*元', filename)
    if m:
        val = float(m.group(1))
        if 0 < val < 100000:
            return f"{val:.2f}"
    m = re.search(r'金额(\d+\.?\d{0,2})', filename)
    if m:
        val = float(m.group(1))
        if 0 < val < 100000:
            return f"{val:.2f}"
    return None


# 发票内容特征词（用于判断 PDF 是否为发票/报销凭证）
INVOICE_CONTENT_MARKERS = [
    "发票号码", "发票代码", "开票日期", "价税合计", "机器编号",
    "税号", "电子发票", "增值税", "行程报销单", "行程单",
    "结账单", "住宿费", "通行费", "消费合计", "小写",
    "收款人", "复核人", "开票人", "销售方", "购买方",
    " Invoice", "Receipt", "Tax",
]


def has_invoice_markers(text):
    """检查文本是否包含发票特征词，用于过滤非发票 PDF"""
    if not text:
        return False
    return any(marker in text for marker in INVOICE_CONTENT_MARKERS)


def classify(text, filename):
    """返回基础类别（不含子类型），用于流程逻辑判断"""
    s = (text or "") + filename
    for keywords, cat in CATEGORY_RULES:
        for kw in keywords:
            if kw in s:
                return cat
    return "其他"


def classify_with_subtype(text, filename):
    """返回完整类别标签（含子类型），用于文件命名
    
    子类型规则（SOP v3.11）：
    - 机票类 + 保险关键词 → "机票(保险)"
    - 行程单类 + 滴滴关键词 → "滴滴打车(行程单)"  (类别变更)
    - 行程单类 + 高速关键词 → "高速费(行程单)"  (类别变更)
    - 结账单类 + 酒店/住宿关键词 → "住宿(结账单)"  (类别变更)
    """
    base_cat = classify(text, filename)
    s = (text or "") + filename
    
    for base_cat_rule, keywords, subtype in SUBTYPE_RULES:
        if base_cat == base_cat_rule:
            for kw in keywords:
                if kw in s:
                    # 子类型会导致类别变更:
                    # "行程单" → "滴滴打车" or "高速费"
                    # "结账单" → "住宿"
                    if base_cat_rule == "行程单" and kw in ["滴滴", "打车", "网约车", "交通运输服务", "客运服务费"]:
                        return "滴滴打车" + subtype
                    elif base_cat_rule == "行程单" and kw in ["高速", "通行费", "路桥费", "ETC", "车辆通行费"]:
                        return "高速费" + subtype
                    elif base_cat_rule == "结账单":
                        return "住宿" + subtype
                    else:
                        return base_cat + subtype
    
    return base_cat


def is_standard_name(filename):
    """检查文件名是否已符合标准格式（含序号末尾或不含序号均可）"""
    if STANDARD_NAME_RE.match(filename):
        return True
    # 降级匹配：不含序号的标准格式（02待核实中的文件）
    m_noseq = re.match(
        r'^(\d{4}-\d{2}-\d{2})_(' + '|'.join(re.escape(c) for c in VALID_CATEGORIES) + r')_(\d+\.\d{2})'
        r'(?:_([^_\d]+(?:-[^_\d]+)?(?:_[\u4e00-\u9fa5]{2,10})?))?'
        r'(?:_(\d{1,4}))?'
        r'(?:_(\d{4})_(WB|YB))?'
        r'(\.\w+)$', filename)
    return bool(m_noseq)


def get_month_from_filename(filename):
    """从标准文件名提取月份 (YYYY-MM)"""
    m = STANDARD_NAME_RE.match(filename)
    if m:
        return m.group(1)[:7]  # group 1 = 日期(新正则)
    return None


def _dedupe_destination(path):
    """目标文件已存在时追加序号，避免覆盖。"""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    counter = 1
    candidate = f"{stem}_{counter}{ext}"
    while os.path.exists(candidate):
        counter += 1
        candidate = f"{stem}_{counter}{ext}"
    return candidate


def _extract_text_for_existing_invoice(path):
    """为已归档文件重新提取文本，用于迁移命名。"""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == '.pdf':
            return extract_pdf_text(path)
        if ext == '.ofd':
            return extract_ofd_text(path)
        if ext == '.xml':
            return extract_xml_text(path)
    except Exception:
        return ""
    return ""


def _build_name_with_location(match, location):
    """按现有标准字段补入住宿城市，保留发票号、状态、序号等后缀。"""
    date, cat, amount = match.group(1), match.group(2), match.group(3)
    suffix = match.group(5) or ""
    op_date = match.group(6) or ""
    status = match.group(7) or ""
    seq = match.group(8) or ""
    ext = match.group(9)

    parts = [date, cat, amount, location]
    if suffix:
        parts.append(suffix)
    if op_date and status:
        parts.extend([op_date, status])
    if seq:
        parts.append(seq)
    return "_".join(parts) + ext


def _rename_lodging_file_with_city(path):
    """如果住宿类文件缺少城市字段，则识别城市并重命名。"""
    filename = os.path.basename(path)
    m = STANDARD_NAME_RE.match(filename)
    if not m:
        return None, "not_standard"
    cat = m.group(2)
    base_cat = cat.split("(")[0] if "(" in cat else cat
    existing_location = m.group(4) or ""
    if base_cat != "住宿":
        return None, "not_lodging"
    if existing_location:
        return None, "already_has_location"

    text = _extract_text_for_existing_invoice(path)
    city = extract_lodging_city(text)
    if not city:
        return None, "city_not_found"

    new_name = _build_name_with_location(m, city)
    dst = _dedupe_destination(os.path.join(os.path.dirname(path), new_name))
    os.rename(path, dst)
    return dst, "renamed"


def _scan_trips_for_invoice_dirs():
    """扫描行程目录，返回可刷新清单的行程信息。"""
    trip_root = globals().get('TRIP_ROOT', "")
    if not trip_root or not os.path.isdir(trip_root):
        return []

    trips = []
    for year_name in sorted(os.listdir(trip_root)):
        year_dir = os.path.join(trip_root, year_name)
        if not os.path.isdir(year_dir):
            continue
        for month_name in sorted(os.listdir(year_dir)):
            month_dir = os.path.join(year_dir, month_name)
            if not os.path.isdir(month_dir):
                continue
            for folder in sorted(os.listdir(month_dir)):
                folder_path = os.path.join(month_dir, folder)
                invoice_dir = os.path.join(folder_path, "02-发票文件")
                if os.path.isdir(invoice_dir):
                    trips.append({
                        'folder_path': folder_path,
                        'folder_name': folder,
                        'month_name': month_name,
                    })
    return trips


def migrate_done_lodging_city_names():
    """一次性迁移 03 已完成和行程附件中的住宿类旧文件名，补入酒店所在城市。

    场景：用户升级到支持住宿城市命名的新版本后，首次运行发票整理时，
    对已归档和已复制到行程目录的住宿/住宿(结账单)文件重新识别文本并重命名。
    """
    marker = os.path.join(BASE_ROOT, ".migration_lodging_city_v1_0_11.done")
    if os.path.exists(marker):
        return
    if not os.path.isdir(DONE_DIR):
        return

    done_renamed = 0
    trip_renamed = 0
    skipped = 0
    failed = 0
    changed_trips = {}

    print(f"\n{'='*60}")
    print("🏨 一次性迁移：为已完成和行程附件住宿类发票补充酒店城市")
    print(f"{'='*60}")

    for month_dir in sorted(os.listdir(DONE_DIR)):
        month_path = os.path.join(DONE_DIR, month_dir)
        if not os.path.isdir(month_path):
            continue
        for filename in sorted(os.listdir(month_path)):
            if filename.startswith('.') or filename == '台账.md':
                continue
            path = os.path.join(month_path, filename)
            if not is_business_file(path):
                continue
            new_path, reason = _rename_lodging_file_with_city(path)
            if reason == "renamed":
                done_renamed += 1
                print(f"   ✅ 03已完成: {filename} → {os.path.basename(new_path)}")
            elif reason == "city_not_found":
                failed += 1
                print(f"   ⚠️ 未识别城市，跳过: {filename}")
            elif reason in ("already_has_location", "not_standard"):
                skipped += 1

    for trip in _scan_trips_for_invoice_dirs():
        invoice_dir = os.path.join(trip['folder_path'], "02-发票文件")
        lodging_dir = os.path.join(invoice_dir, "住宿")
        if not os.path.isdir(lodging_dir):
            continue
        for filename in sorted(os.listdir(lodging_dir)):
            path = os.path.join(lodging_dir, filename)
            if not is_business_file(path):
                continue
            new_path, reason = _rename_lodging_file_with_city(path)
            if reason == "renamed":
                trip_renamed += 1
                changed_trips[trip['folder_path']] = trip
                print(f"   ✅ 行程附件: {filename} → {os.path.basename(new_path)}")
            elif reason == "city_not_found":
                failed += 1
                print(f"   ⚠️ 行程附件未识别城市，跳过: {filename}")
            elif reason in ("already_has_location", "not_standard"):
                skipped += 1

    if changed_trips:
        _update_trip_invoice_lists(list(changed_trips.values()))
        print(f"   📝 已刷新 {len(changed_trips)} 个行程的发票文件清单")

    try:
        with open(marker, 'w', encoding='utf-8') as f:
            f.write(
                f"migration=lodging_city_v1.0.11\n"
                f"ran_at={datetime.now().isoformat()}\n"
                f"done_renamed={done_renamed}\n"
                f"trip_renamed={trip_renamed}\n"
                f"skipped={skipped}\n"
                f"failed={failed}\n"
            )
    except Exception as e:
        print(f"   ⚠️ 迁移标记写入失败: {e}")

    print(f"🏨 迁移完成：03已完成重命名 {done_renamed} 个，行程附件重命名 {trip_renamed} 个，跳过 {skipped} 个，未识别 {failed} 个")


# ===== 日志 =====

def load_log():
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"runs": [], "last_run": None}


def save_log(log):
    log["last_run"] = datetime.now().isoformat()
    # 只保留最近20次运行记录
    log["runs"] = log["runs"][-20:]
    with open(LOG_FILE, 'w') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ===== 阶段1: 处理 01 待分类 =====

def process_inbox():
    """处理 01 待分类/ 中的新文件
    
    流程:
    1. OFD预处理: 同发票号有PDF→删OFD; 无PDF→提取OFD数据→转PDF→归档
    2. XML预处理: 同发票号有PDF→删XML; 无PDF→提取XML数据→转PDF→归档
    3. PDF处理: 提取日期/金额/类别→归档到03已完成或移到02待核实
    """
    if not os.path.isdir(INPUT_DIR):
        return [], [], 0, []

    files = sorted([f for f in os.listdir(INPUT_DIR)
                    if not f.startswith('.')
                    and f not in ['baoxiao.xlsx', '_发票清单.md', '台账.md', '日志.md']])

    if not files:
        return [], [], 0, []

    print(f"\n{'='*60}")
    print(f"📥 阶段1: 处理 01 待分类/ ({len(files)} 个文件)")
    print(f"{'='*60}")

    success = []
    review = []
    dup_deleted = 0
    next_seq = get_next_seq_number()
    inbox_log_entries = []  # 日志流水: [(原文件名, 去向, 新文件名/原因, 识别结果摘要)]
    seen_invoice_global = set()  # 全局发票号码集合（OFD/XML/PDF共享去重）

    # 预扫描03已完成中的发票号和行程单金额，防止重复归档
    archived_inv_nums = set()       # 已归档的发票号
    archived_dd_amounts = {}        # 已归档的滴滴打车金额: {date_amount_key: True}
    archived_gs_amounts = {}        # 已归档的高速费金额: {date_amount_key: True}
    archived_trip_amounts = {}      # 已归档的行程单金额: {date_amount_key: True}
    zs_checkout_index = {}          # 住宿(结账单)配对索引: {amount_cities → [(date, filename)]}
    zs_invoice_index = {}           # 住宿发票反向配对索引: {amount_cities → [(date, filename, seller_name)]}
    # 索引结构改为列表，支持同金额多条结账单/发票（不同城市或不同入住日期）
    if os.path.isdir(DONE_DIR):
        for month_dir in os.listdir(DONE_DIR):
            mpath = os.path.join(DONE_DIR, month_dir)
            if not os.path.isdir(mpath):
                continue
            for afn in os.listdir(mpath):
                if afn.startswith('.') or afn == '台账.md':
                    continue
                afpath = os.path.join(mpath, afn)
                ext = os.path.splitext(afn)[1].lower()
                # PDF文件: 提取发票号
                if ext == '.pdf':
                    atext = extract_pdf_text(afpath) or ""
                    ainv = extract_invoice_number(atext)
                    if ainv:
                        num, _ = ainv
                        if len(num) >= 18 and num.isdigit():
                            archived_inv_nums.add(num)
                            seen_invoice_global.add(num)
                else:
                    atext = ""
                # 记录已归档各类日期+金额，用于交叉去重和配对
                m = STANDARD_NAME_RE.match(afn)
                if m:
                    adate = m.group(1)    # group 1 = 日期
                    acat = m.group(2)     # group 2 = 类别
                    aamt = float(m.group(3))  # group 3 = 金额
                    da_key = f"{adate}_{aamt}"
                    if acat == '滴滴打车':
                        archived_dd_amounts[da_key] = True
                    elif acat == '高速费':
                        archived_gs_amounts[da_key] = True
                    elif '行程单' in acat:
                        archived_trip_amounts[da_key] = True
                    # 住宿(结账单)索引: 金额+城市 → [(入住日期, 文件名)]
                    # v3.24: 增加城市匹配，避免同金额跨城市误配
                    if acat == '住宿(结账单)':
                        a_cities = extract_city_from_text(atext) if atext else []
                        # 多种key格式: 金额+城市列表, 金额+单个城市, 纯金额(降级)
                        cities_str = ','.join(sorted(a_cities)) if a_cities else ''
                        zs_key_full = f"{aamt:.2f}_{cities_str}"
                        if zs_key_full not in zs_checkout_index:
                            zs_checkout_index[zs_key_full] = []
                        zs_checkout_index[zs_key_full].append((adate, afn))
                        # 也为每个单独城市建立索引
                        for city in a_cities:
                            zs_key_city = f"{aamt:.2f}_{city}"
                            if zs_key_city not in zs_checkout_index:
                                zs_checkout_index[zs_key_city] = []
                            zs_checkout_index[zs_key_city].append((adate, afn))
                        # 纯金额索引(降级，无城市信息的结账单)
                        zs_amt_key = f"{aamt:.2f}_"
                        if zs_amt_key not in zs_checkout_index:
                            zs_checkout_index[zs_amt_key] = []
                        zs_checkout_index[zs_amt_key].append((adate, afn))
                    # 住宿发票索引: 金额+城市 → [(日期, 文件名, 酒店名称)]
                    # v3.25: 住宿结账单反向配对，找03已完成中的对应发票
                    if acat == '住宿':
                        a_cities = extract_city_from_text(atext) if atext else []
                        a_seller = extract_seller_name_from_text(atext) if atext else None
                        cities_str = ','.join(sorted(a_cities)) if a_cities else ''
                        # 金额+城市列表
                        zs_key_full = f"{aamt:.2f}_{cities_str}"
                        if zs_key_full not in zs_invoice_index:
                            zs_invoice_index[zs_key_full] = []
                        zs_invoice_index[zs_key_full].append((adate, afn, a_seller))
                        # 为每个单独城市建立索引
                        for city in a_cities:
                            zs_key_city = f"{aamt:.2f}_{city}"
                            if zs_key_city not in zs_invoice_index:
                                zs_invoice_index[zs_key_city] = []
                            zs_invoice_index[zs_key_city].append((adate, afn, a_seller))
                        # 纯金额索引(降级)
                        zs_amt_key = f"{aamt:.2f}_"
                        if zs_amt_key not in zs_invoice_index:
                            zs_invoice_index[zs_amt_key] = []
                        zs_invoice_index[zs_amt_key].append((adate, afn, a_seller))

    print(f"   已归档发票号: {len(archived_inv_nums)} 个 | 滴滴打车金额: {len(archived_dd_amounts)} 个 | 行程单金额: {len(archived_trip_amounts)} 个 | 住宿结账单索引: {len(zs_checkout_index)} 条 | 住宿发票索引: {len(zs_invoice_index)} 条")

    def move_to_review(src, filename, reason):
        dst = os.path.join(REVIEW_DIR, filename)
        counter = 1
        name, ext = os.path.splitext(filename)
        while os.path.exists(dst):
            dst = os.path.join(REVIEW_DIR, f"{name}_{counter}{ext}")
            counter += 1
        shutil.move(src, dst)
        review.append((filename, reason))
        inbox_log_entries.append((filename, "→02待核实", "", reason))
        print(f"   → 02 待核实 ({reason})")

    # ===== OFD预处理 (SOP 2.7: OFD→PDF自动转换) =====
    ofd_files = [f for f in files if os.path.splitext(f)[1].lower() == '.ofd']
    ofd_converted = 0
    ofd_dup_removed = 0

    if ofd_files:
        print(f"\n🔄 OFD预处理: {len(ofd_files)} 个OFD文件")
        print(f"   规则: 同发票号有PDF→删OFD; 无PDF→提取数据→转PDF→归档")

        # 构建发票号码映射表 (所有文件的发票号码)
        inv_num_map = {}  # num -> [(filename, ext)]
        for f in files:
            src = os.path.join(INPUT_DIR, f)
            _, ext = os.path.splitext(f)
            if ext.lower() not in ['.pdf', '.ofd']:
                continue
            text = extract_ofd_text(src) if ext.lower() == '.ofd' else extract_pdf_text(src)
            inv = extract_invoice_number(text)
            if inv:
                num, _ = inv
                inv_num_map.setdefault(num, []).append((f, ext.lower()))

        for f in ofd_files:
            src = os.path.join(INPUT_DIR, f)
            text = extract_ofd_text(src)
            inv = extract_invoice_number(text)

            # 情况1: 同发票号码已有PDF版本 → 删除OFD (SOP 2.6 PDF优先)
            if inv:
                num, _ = inv
                same_num = inv_num_map.get(num, [])
                has_pdf = any(e == '.pdf' for fn, e in same_num if fn != f)
                if has_pdf:
                    os.remove(src)
                    ofd_dup_removed += 1
                    dup_deleted += 1
                    inbox_log_entries.append((f, "删除-同号有PDF", "", f"发票号={num}"))
                    continue

            # 情况2: 无匹配PDF → 从OFD提取数据，转换后归档
            print(f"   📄 {f[:60]}")

            date = extract_date_from_text(text) or extract_date_from_filename(f)
            amount = extract_amount_from_text(text)
            fn_amount = extract_amount_from_filename(f)
            if fn_amount and amount:
                if float(amount) < float(fn_amount) * 0.3:
                    amount = fn_amount
            elif fn_amount and not amount:
                amount = fn_amount

            cat = classify(text, f)
            cat_label = classify_with_subtype(text, f)

            # 机票类/高铁类/住宿类特殊日期规则 (用基础类别判断)
            if cat == "机票":
                trip_date, trip_source = extract_trip_date_for_jp(text)
                if trip_date:
                    date = trip_date
                    print(f"      🛫 机票行程日期={trip_date} (来源={trip_source})")
                else:
                    print(f"      🛫 无行程日期，使用开票日期={date}")
            if cat == "高铁":
                trip_date, trip_source = extract_trip_date_for_gaotie(text)
                if trip_date:
                    date = trip_date
                    print(f"      🚄 高铁开车日期={trip_date} (来源={trip_source})")
                else:
                    print(f"      🚄 无开车日期，使用开票日期={date}")
            # 住宿类: 优先入住日期，其次配对推断，最后开票日期 (SOP v3.23→v3.25)
            # v3.25: 结账单始终做反向配对提示(找03已完成中的发票)
            if cat == "住宿" and amount:
                stay_date, stay_source = extract_stay_date_from_text(text)
                if cat_label == "住宿(结账单)":  # 结账单: 反向配对找发票
                    # v3.25: 始终做反向配对提示
                    inv_date, inv_fn, inv_seller = find_matching_invoice_for_checkout(
                        text, amount, zs_invoice_index, indent="      ")
                    if stay_date:
                        date = stay_date
                        print(f"      🏨 住宿入住日期={stay_date} (来源={stay_source})")
                        if inv_fn:
                            print(f"      🏨 对应发票已归档: {inv_fn} (日期={inv_date})")
                    elif inv_date:
                        # 无入住日期但有对应发票→使用发票日期
                        print(f"      🏨 结账单反向配对→使用发票日期={inv_date}")
                        date = inv_date
                    else:
                        print(f"      🏨 结账单无入住日期且无反向配对，使用打印日期={date}")
                else:  # 发票: 配对结账单推断日期
                    if stay_date:
                        date = stay_date
                        print(f"      🏨 住宿入住日期={stay_date} (来源={stay_source})")
                    else:
                        # 配对推断: 金额+城市匹配已有结账单 (v3.24: 加城市过滤防跨城误配)
                        inv_cities = extract_city_from_text(text)
                        paired_date = None
                        paired_fn = None
                        amt_val = float(amount.replace(',','')) if amount else 0
                        # 优先: 金额+发票城市匹配结账单城市
                        if inv_cities:
                            for city in inv_cities:
                                zs_key = f"{amt_val:.2f}_{city}"
                                if zs_key in zs_checkout_index:
                                    for pd, pfn in zs_checkout_index[zs_key]:
                                        paired_date, paired_fn = pd, pfn
                                        print(f"      🏨 住宿配对推断={paired_date} (金额={amount} + 城市={city} ↔ 结账单={paired_fn})")
                                        break  # 取第一个匹配
                                    if paired_date:
                                        break
                        # 降级: 无城市信息的发票用纯金额匹配(可能多条，需谨慎)
                        if not paired_date:
                            zs_key = f"{amt_val:.2f}_"
                            if zs_key in zs_checkout_index and len(zs_checkout_index[zs_key]) == 1:
                                # 只有1条结账单时才用纯金额匹配
                                paired_date, paired_fn = zs_checkout_index[zs_key][0]
                                print(f"      🏨 住宿配对推断(降级)= {paired_date} (金额={amount} ↔ 结账单={paired_fn})")
                        if paired_date:
                            date = paired_date
                        else:
                            print(f"      🏨 无入住日期且无配对，使用开票日期={date}")

            if not date:
                move_to_review(src, f, "OFD无法提取日期")
                continue
            if not amount:
                move_to_review(src, f, "OFD无法提取金额")
                continue
            try:
                amount = f"{float(amount.replace(',','')):.2f}"
            except:
                move_to_review(src, f, "OFD金额格式异常")
                continue

            # 机票类/高铁类提取出发地-到达地 (SOP v3.10)
            route = extract_route(text, cat_label)

            # 发票号码去重 (在已归档文件中检查)
            if inv:
                num, _ = inv
                if num in seen_invoice_global:
                    os.remove(src)
                    dup_deleted += 1
                    inbox_log_entries.append((f, "删除-OFD发票号重复", "", f"发票号={num}"))
                    print(f"      🗑️ 删除（发票号码已存在: {num}）")
                    continue
                seen_invoice_global.add(num)

            # 尝试OFD→PDF转换（写到临时目录避免权限问题）
            base_name = os.path.splitext(f)[0]
            tmp_pdf = os.path.join('/tmp', f"{base_name}_ofd2pdf.pdf")
            out_ext = '.pdf'  # 输出格式始终为PDF

            if FITZ_AVAILABLE and convert_ofd_to_pdf(src, tmp_pdf):
                print(f"      🔄 OFD→PDF转换成功")
                os.remove(src)
                ofd_converted += 1
                # 使用转换后的PDF（来自临时目录）
                process_src = tmp_pdf
            else:
                print(f"      ⚠️ OFD→PDF转换失败，保留OFD格式")
                process_src = src
                out_ext = '.ofd'

            # 生成标准文件名并归档 (用含子类型的类别标签)
            # 机票/高铁类含出发地-到达地 (SOP v3.10)
            # v3.20: 末尾增加操作日期与报销状态
            # v3.22: 序号放在末尾(状态后缀之后)
            # v3.30: 增加购买方公司简称
            buyer_name = extract_buyer_name_from_text(text)
            buyer_short = shorten_company_name(buyer_name) if buyer_name else ""
            buyer_part = f"_{buyer_short}" if buyer_short else ""
            status_suffix = make_status_suffix()
            route_part = f"_{route}" if route else ""
            seq_suffix = f"_{next_seq:03d}"
            new_name = f"{date}_{cat_label}_{amount}{route_part}{buyer_part}{status_suffix}{seq_suffix}{out_ext}"
            month_dir = os.path.join(DONE_DIR, date[:7])
            os.makedirs(month_dir, exist_ok=True)
            dst = os.path.join(month_dir, new_name)

            if os.path.exists(dst):
                if inv:
                    suffix = inv[0][-4:]
                    new_name = f"{date}_{cat_label}_{amount}{route_part}{buyer_part}_{suffix}{status_suffix}{seq_suffix}{out_ext}"
                    dst = os.path.join(month_dir, new_name)
                else:
                    counter = 1
                    while os.path.exists(dst):
                        new_name = f"{date}_{cat_label}_{amount}{route_part}{buyer_part}_{counter}{status_suffix}{seq_suffix}{out_ext}"
                        dst = os.path.join(month_dir, new_name)
                        counter += 1

            shutil.move(process_src, dst)
            next_seq += 1
            success.append((dst, new_name, date, amount, cat_label))
            print(f"      → 03 已完成/{date[:7]}/{new_name}")

        if ofd_converted > 0 or ofd_dup_removed > 0:
            print(f"\n   📊 OFD预处理汇总: 转换{ofd_converted}个 | 删除重复{ofd_dup_removed}个")

        # 重新扫描目录（OFD已被转换或删除）
        files = sorted([f for f in os.listdir(INPUT_DIR)
                        if not f.startswith('.')
                        and f not in ['baoxiao.xlsx', '_发票清单.md', '台账.md', '日志.md']])

    # ===== XML预处理 (SOP 2.8: XML→PDF自动转换) =====
    xml_files = [f for f in files if os.path.splitext(f)[1].lower() == '.xml']
    xml_converted = 0
    xml_dup_removed = 0

    if xml_files:
        print(f"\n🔄 XML预处理: {len(xml_files)} 个XML文件")
        print(f"   规则: 同发票号有PDF→删XML; 无PDF→提取数据→转PDF→归档")

        # 构建发票号码映射表 (当前目录中PDF和XML文件的发票号码)
        inv_num_map2 = {}  # num -> [(filename, ext)]
        for f in files:
            src = os.path.join(INPUT_DIR, f)
            _, ext = os.path.splitext(f)
            if ext.lower() not in ['.pdf', '.xml']:
                continue
            text = extract_xml_text(src) if ext.lower() == '.xml' else extract_pdf_text(src)
            inv = extract_invoice_number(text)
            if inv:
                num, _ = inv
                inv_num_map2.setdefault(num, []).append((f, ext.lower()))

        for f in xml_files:
            src = os.path.join(INPUT_DIR, f)
            text = extract_xml_text(src)
            inv = extract_invoice_number(text)

            # 情况1: 同发票号码已有PDF版本 → 删除XML (SOP 2.6 PDF优先)
            if inv:
                num, _ = inv
                same_num = inv_num_map2.get(num, [])
                has_pdf = any(e == '.pdf' for fn, e in same_num if fn != f)
                if has_pdf:
                    os.remove(src)
                    xml_dup_removed += 1
                    dup_deleted += 1
                    inbox_log_entries.append((f, "删除-XML同号有PDF", "", f"发票号={num}"))
                    print(f"   🗑️ 删除XML（同发票号有PDF版: {num}）")
                    continue

            # 情况2: 无匹配PDF → 从XML提取数据，转换后归档
            print(f"   📄 {f[:60]}")

            # XML优先用结构化字段提取金额/日期（比文本匹配更准确）
            xml_fields = extract_xml_fields(src)
            xml_amount = xml_fields.get('amount', '') if xml_fields else ''
            xml_date_raw = xml_fields.get('issue_time', '') if xml_fields else ''

            # 金额: 结构化字段优先 > 文本提取 > 文件名
            amount = xml_amount or extract_amount_from_text(text)
            fn_amount = extract_amount_from_filename(f)
            if fn_amount and amount:
                if float(amount) < float(fn_amount) * 0.3:
                    amount = fn_amount
            elif fn_amount and not amount:
                amount = fn_amount

            # 日期: 结构化字段优先 > 文本提取 > 文件名
            date = None
            if xml_date_raw:
                dm = re.match(r'(\d{4})-(\d{2})-(\d{2})', xml_date_raw)
                if dm:
                    y, mo, d = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
                    if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
                        date = f"{y}-{mo:02d}-{d:02d}"
            if not date:
                date = extract_date_from_text(text) or extract_date_from_filename(f)

            cat = classify(text, f)
            cat_label = classify_with_subtype(text, f)

            # 机票类/高铁类/住宿类特殊日期规则 (用基础类别判断)
            if cat == "机票":
                trip_date, trip_source = extract_trip_date_for_jp(text)
                if trip_date:
                    date = trip_date
                    print(f"      🛫 机票行程日期={trip_date} (来源={trip_source})")
                else:
                    print(f"      🛫 无行程日期，使用开票日期={date}")
            if cat == "高铁":
                trip_date, trip_source = extract_trip_date_for_gaotie(text)
                if trip_date:
                    date = trip_date
                    print(f"      🚄 高铁开车日期={trip_date} (来源={trip_source})")
                else:
                    print(f"      🚄 无开车日期，使用开票日期={date}")
            # 住宿类: 优先入住日期，其次配对推断，最后开票日期 (SOP v3.25)
            # v3.25: 结账单始终做反向配对提示(找03已完成中的发票)
            if cat == "住宿" and amount:
                stay_date, stay_source = extract_stay_date_from_text(text)
                if cat_label == "住宿(结账单)":  # 结账单: 反向配对找发票
                    # v3.25: 始终做反向配对提示
                    inv_date, inv_fn, inv_seller = find_matching_invoice_for_checkout(
                        text, amount, zs_invoice_index, indent="      ")
                    if stay_date:
                        date = stay_date
                        print(f"      🏨 住宿入住日期={stay_date} (来源={stay_source})")
                        if inv_fn:
                            print(f"      🏨 对应发票已归档: {inv_fn} (日期={inv_date})")
                    elif inv_date:
                        print(f"      🏨 结账单反向配对→使用发票日期={inv_date}")
                        date = inv_date
                    else:
                        print(f"      🏨 结账单无入住日期且无反向配对，使用打印日期={date}")
                else:  # 发票: 配对结账单推断日期
                    if stay_date:
                        date = stay_date
                        print(f"      🏨 住宿入住日期={stay_date} (来源={stay_source})")
                    else:
                        inv_cities = extract_city_from_text(text)
                        # XML结构化字段可能补充城市信息
                        if xml_fields and xml_fields.get('seller_name') and not inv_cities:
                            seller = xml_fields.get('seller_name')
                            for city in MAJOR_CITIES:
                                if city in seller and city not in inv_cities:
                                    inv_cities.append(city)
                        paired_date = None
                        paired_fn = None
                        amt_val = float(amount.replace(',','')) if amount else 0
                        if inv_cities:
                            for city in inv_cities:
                                zs_key = f"{amt_val:.2f}_{city}"
                                if zs_key in zs_checkout_index:
                                    for pd, pfn in zs_checkout_index[zs_key]:
                                        paired_date, paired_fn = pd, pfn
                                        print(f"      🏨 住宿配对推断={paired_date} (金额={amount} + 城市={city} ↔ 结账单={paired_fn})")
                                        break
                                    if paired_date:
                                        break
                        if not paired_date:
                            zs_key = f"{amt_val:.2f}_"
                            if zs_key in zs_checkout_index and len(zs_checkout_index[zs_key]) == 1:
                                paired_date, paired_fn = zs_checkout_index[zs_key][0]
                                print(f"      🏨 住宿配对推断(降级)= {paired_date} (金额={amount} ↔ 结账单={paired_fn})")
                        if paired_date:
                            date = paired_date
                        else:
                            print(f"      🏨 无入住日期且无配对，使用开票日期={date}")

            # 机票类/高铁类提取出发地-到达地 (SOP v3.10)
            route = extract_route(text, cat_label)

            if not date:
                move_to_review(src, f, "XML无法提取日期")
                continue
            if not amount:
                move_to_review(src, f, "XML无法提取金额")
                continue
            try:
                amount = f"{float(amount.replace(',','')):.2f}"
            except:
                move_to_review(src, f, "XML金额格式异常")
                continue

            # 发票号码去重 (在已归档文件中检查)
            if inv:
                num, _ = inv
                if num in seen_invoice_global:
                    os.remove(src)
                    dup_deleted += 1
                    inbox_log_entries.append((f, "删除-XML发票号重复", "", f"发票号={num}"))
                    print(f"      🗑️ 删除（发票号码已存在: {num}）")
                    continue
                seen_invoice_global.add(num)

            # 尝试XML→PDF转换（写到临时目录避免权限问题）
            base_name = os.path.splitext(f)[0]
            tmp_pdf = os.path.join('/tmp', f"{base_name}_xml2pdf.pdf")
            out_ext = '.pdf'  # 输出格式始终为PDF

            if FPDF_AVAILABLE and convert_xml_to_pdf(src, tmp_pdf):
                print(f"      🔄 XML→PDF转换成功")
                os.remove(src)
                xml_converted += 1
                # 使用转换后的PDF（来自临时目录）
                process_src = tmp_pdf
            else:
                print(f"      ⚠️ XML→PDF转换失败，移到02待核实")
                move_to_review(src, f, "XML无法转PDF(fpdf2不可用或转换失败)")
                continue

            # 生成标准文件名并归档 (用含子类型的类别标签)
            # 机票/高铁类含出发地-到达地 (SOP v3.10)
            # v3.20: 末尾增加操作日期与报销状态
            # v3.22: 序号放在末尾(状态后缀之后)
            # v3.30: 增加购买方公司简称（XML优先用结构化字段）
            if xml_fields:
                buyer_name = xml_fields.get('buyer_name', '') or extract_buyer_name_from_text(text)
            else:
                buyer_name = extract_buyer_name_from_text(text)
            buyer_short = shorten_company_name(buyer_name) if buyer_name else ""
            buyer_part = f"_{buyer_short}" if buyer_short else ""
            status_suffix = make_status_suffix()
            route_part = f"_{route}" if route else ""
            seq_suffix = f"_{next_seq:03d}"
            new_name = f"{date}_{cat_label}_{amount}{route_part}{buyer_part}{status_suffix}{seq_suffix}{out_ext}"
            month_dir = os.path.join(DONE_DIR, date[:7])
            os.makedirs(month_dir, exist_ok=True)
            dst = os.path.join(month_dir, new_name)

            if os.path.exists(dst):
                if inv:
                    suffix = inv[0][-4:]
                    new_name = f"{date}_{cat_label}_{amount}{route_part}{buyer_part}_{suffix}{status_suffix}{seq_suffix}{out_ext}"
                    dst = os.path.join(month_dir, new_name)
                else:
                    counter = 1
                    while os.path.exists(dst):
                        new_name = f"{date}_{cat_label}_{amount}{route_part}{buyer_part}_{counter}{status_suffix}{seq_suffix}{out_ext}"
                        dst = os.path.join(month_dir, new_name)
                        counter += 1

            shutil.move(process_src, dst)
            next_seq += 1
            success.append((dst, new_name, date, amount, cat_label))
            print(f"      → 03 已完成/{date[:7]}/{new_name}")

        if xml_converted > 0 or xml_dup_removed > 0:            print(f"\n   📊 XML预处理汇总: 转换{xml_converted}个 | 删除重复{xml_dup_removed}个")

        # 重新扫描目录（XML已被转换或删除）
        files = sorted([f for f in os.listdir(INPUT_DIR)
                        if not f.startswith('.')
                        and f not in ['baoxiao.xlsx', '_发票清单.md', '台账.md', '日志.md']])

    # ===== PDF+图片处理 =====
    # 第一遍: 提取发票号码，标记重复（仅PDF和OCR成功的图片）
    invoice_map = {}
    duplicate_nums = set()
    for f in files:
        src = os.path.join(INPUT_DIR, f)
        name, ext = os.path.splitext(f)
        if ext.lower() not in ['.pdf']:
            continue
        text = extract_pdf_text(src)
        inv = extract_invoice_number(text)
        if inv:
            num, _ = inv
            if num in invoice_map:
                duplicate_nums.add(num)
            else:
                invoice_map[num] = (f, src)

    seen_invoice = set()

    for f in files:
        src = os.path.join(INPUT_DIR, f)
        name, ext = os.path.splitext(f)
        ext_lower = ext.lower()
        is_image = ext_lower in IMAGE_EXTENSIONS
        is_pdf = ext_lower == '.pdf'
        print(f"📄 {f[:80]}")

        # 非PDF和非图片格式 → 移到02待核实
        if not is_pdf and not is_image:
            move_to_review(src, f, f"非发票格式({ext})")
            continue

        # 图片格式: 尝试OCR提取文字
        if is_image:
            img_text = extract_image_text(src)
            if img_text and len(img_text) > 20:
                # OCR成功提取到有效文字 → 用OCR文字进行分类处理
                text = img_text
                print(f"   🖼️ OCR识别成功({len(img_text)}字)")
            else:
                # OCR不可用或识别失败 → 移到02待核实
                reason = "图片OCR不可用" if not OCR_AVAILABLE else "图片OCR识别失败(文字不足)"
                move_to_review(src, f, reason)
                continue
        else:
            text = extract_pdf_text(src)

        # 发票号码去重（与OFD预处理共享去重集合）
        inv = extract_invoice_number(text)
        if inv:
            num, _ = inv
            if num in seen_invoice or num in seen_invoice_global:
                os.remove(src)
                dup_deleted += 1
                inbox_log_entries.append((f, "删除-发票号重复(PDF)", "", f"发票号={num}"))
                print(f"   🗑️ 删除（发票号码重复: {num}）")
                continue
            seen_invoice.add(num)

        date = extract_date_from_text(text) or extract_date_from_filename(f)
        amount = extract_amount_from_text(text)
        fn_amount = extract_amount_from_filename(f)
        if fn_amount and amount:
            if float(amount) < float(fn_amount) * 0.3:
                amount = fn_amount
        elif fn_amount and not amount:
            amount = fn_amount

        cat = classify(text, f)
        cat_label = classify_with_subtype(text, f)

        # 行程单vs发票交叉去重: 行程单与已有对应发票金额匹配时删行程单
        # 行程单申请日期可能比发票开票日期早1天，检查±1天范围
        if cat_label in ('滴滴打车(行程单)', '高速费(行程单)') and amount:
            trip_amount = float(amount) if amount else 0
            if trip_amount > 0:
                # 检查同日期和±1天是否有对应发票
                da_keys = [f"{date}_{trip_amount:.2f}"]
                # ±1天: 行程单申请日期可能比发票开票日期早1天
                import datetime as dt_mod
                try:
                    d_obj = dt_mod.datetime.strptime(date, '%Y-%m-%d')
                    for offset in [-1, 1]:
                        d2 = d_obj + dt_mod.timedelta(days=offset)
                        da_keys.append(f"{d2.strftime('%Y-%m-%d')}_{trip_amount:.2f}")
                except: pass
                if cat_label == '滴滴打车(行程单)':
                    overlap = any(k in archived_dd_amounts for k in da_keys)
                    dup_type = "滴滴打车"
                else:
                    overlap = any(k in archived_gs_amounts for k in da_keys)
                    dup_type = "高速费"
                if overlap:
                    os.remove(src)
                    dup_deleted += 1
                    inbox_log_entries.append((f, f"删除-行程单与{dup_type}发票交叉去重", "", f"金额={trip_amount:.2f}"))
                    print(f"   🗑️ 删除行程单（已有对应{dup_type}发票，金额={trip_amount:.2f}）")
                    continue

        # 滴滴打车发票: 检查已有行程单金额匹配时删行程单标记
        # （此检查在行程单处理之前执行，防止行程单先归档再被发票覆盖）

        # 机票类：优先使用行程日期（备注/携程订单），而非开票日期
        if cat == "机票":
            trip_date, trip_source = extract_trip_date_for_jp(text)
            if trip_date:
                date = trip_date
                print(f"   🛫 机票行程日期={trip_date} (来源={trip_source})")
            else:
                print(f"   🛫 无行程日期，使用开票日期={date}")

        # 高铁类：优先使用开车日期（乘车日期），而非开票日期
        if cat == "高铁":
            trip_date, trip_source = extract_trip_date_for_gaotie(text)
            if trip_date:
                date = trip_date
                print(f"   🚄 高铁开车日期={trip_date} (来源={trip_source})")
            else:
                print(f"   🚄 无开车日期，使用开票日期={date}")

        # 住宿类: 优先入住日期，其次配对推断，最后开票日期 (SOP v3.25)
        # v3.25: 结账单始终做反向配对提示(找03已完成中的发票)
        if cat == "住宿" and amount:
            stay_date, stay_source = extract_stay_date_from_text(text)
            if cat_label == "住宿(结账单)":  # 结账单: 反向配对找发票
                # v3.25: 始终做反向配对提示
                inv_date, inv_fn, inv_seller = find_matching_invoice_for_checkout(
                    text, amount, zs_invoice_index, indent="   ")
                if stay_date:
                    date = stay_date
                    print(f"   🏨 住宿入住日期={stay_date} (来源={stay_source})")
                    if inv_fn:
                        print(f"   🏨 对应发票已归档: {inv_fn} (日期={inv_date})")
                elif inv_date:
                    print(f"   🏨 结账单反向配对→使用发票日期={inv_date}")
                    date = inv_date
                else:
                    print(f"   🏨 结账单无入住日期且无反向配对，使用打印日期={date}")
            else:  # 发票: 配对结账单推断日期
                if stay_date:
                    date = stay_date
                    print(f"   🏨 住宿入住日期={stay_date} (来源={stay_source})")
                else:
                    # 配对推断: 金额+城市匹配已有结账单 (v3.24)
                    inv_cities = extract_city_from_text(text)
                    paired_date = None
                    paired_fn = None
                    amt_val = float(amount.replace(',','')) if amount else 0
                    if inv_cities:
                        for city in inv_cities:
                            zs_key = f"{amt_val:.2f}_{city}"
                            if zs_key in zs_checkout_index:
                                for pd, pfn in zs_checkout_index[zs_key]:
                                    paired_date, paired_fn = pd, pfn
                                    print(f"   🏨 住宿配对推断={paired_date} (金额={amount} + 城市={city} ↔ 结账单={paired_fn})")
                                    break
                                if paired_date:
                                    break
                    if not paired_date:
                        zs_key = f"{amt_val:.2f}_"
                        if zs_key in zs_checkout_index and len(zs_checkout_index[zs_key]) == 1:
                            paired_date, paired_fn = zs_checkout_index[zs_key][0]
                            print(f"   🏨 住宿配对推断(降级)= {paired_date} (金额={amount} ↔ 结账单={paired_fn})")
                    if paired_date:
                        date = paired_date
                    else:
                        print(f"   🏨 无入住日期且无配对，使用开票日期={date}")

        # 机票类/高铁类提取出发地-到达地 (SOP v3.10)
        route = extract_route(text, cat_label)

        if not date:
            move_to_review(src, f, "无法提取日期")
            continue
        if not amount:
            move_to_review(src, f, "无法提取金额")
            continue

        # 发票内容校验：非发票 PDF（无发票特征词）移入待核实
        if not has_invoice_markers(text):
            move_to_review(src, f, "非发票内容(无发票特征词)")
            continue
        try:
            amount = f"{float(amount.replace(',','')):.2f}"
        except:
            move_to_review(src, f, "金额格式异常")
            continue

        # 生成标准文件名 (用含子类型的类别标签)
        # 机票/高铁类含出发地-到达地 (SOP v3.10)
        # v3.20: 末尾增加操作日期与报销状态
        # v3.22: 序号放在末尾(状态后缀之后)
        # v3.30: 增加购买方公司简称
        buyer_name = extract_buyer_name_from_text(text)
        buyer_short = shorten_company_name(buyer_name) if buyer_name else ""
        buyer_part = f"_{buyer_short}" if buyer_short else ""
        status_suffix = make_status_suffix()
        route_part = f"_{route}" if route else ""
        seq_suffix = f"_{next_seq:03d}"
        new_name = f"{date}_{cat_label}_{amount}{route_part}{buyer_part}{status_suffix}{seq_suffix}{ext}"
        month_dir = os.path.join(DONE_DIR, date[:7])
        os.makedirs(month_dir, exist_ok=True)
        dst = os.path.join(month_dir, new_name)

        if os.path.exists(dst):
            if inv:
                suffix = inv[0][-4:]
                new_name = f"{date}_{cat_label}_{amount}{route_part}{buyer_part}_{suffix}{status_suffix}{seq_suffix}{ext}"
                dst = os.path.join(month_dir, new_name)
            else:
                counter = 1
                while os.path.exists(dst):
                    new_name = f"{date}_{cat_label}_{amount}{route_part}{buyer_part}_{counter}{status_suffix}{seq_suffix}{ext}"
                    dst = os.path.join(month_dir, new_name)
                    counter += 1

        shutil.move(src, dst)
        next_seq += 1
        success.append((dst, new_name, date, amount, cat_label))
        inv_info = f"发票号={inv[0]}" if inv else "无发票号"
        route_info = f"路线={route}" if route else ""
        inbox_log_entries.append((f, f"→03已完成/{date[:7]}", new_name, f"{cat_label} ¥{amount} {inv_info} {route_info}"))
        print(f"   → 03 已完成/{date[:7]}/{new_name}")

        # 更新已归档金额映射，供后续行程单交叉去重使用
        if cat_label == '滴滴打车' and amount:
            try:
                da_key = f"{date}_{float(amount):.2f}"
                archived_dd_amounts[da_key] = True
            except: pass
        elif cat_label == '高速费' and amount:
            try:
                da_key = f"{date}_{float(amount):.2f}"
                archived_gs_amounts[da_key] = True
            except: pass

    return success, review, dup_deleted, inbox_log_entries


# ===== 阶段2: 处理 02 待核实（已手动核实的文件）=====

def process_review():
    """扫描 02 待核实/，把已手动重命名为标准格式的文件归档到 03 已完成/
    
    同时将XML文件移回 01 待分类/，让下次运行时由XML预处理阶段处理。
    """
    if not os.path.isdir(REVIEW_DIR):
        return [], []

    review_log_entries = []  # 02待核实日志流水
    next_seq = get_next_seq_number()

    files = sorted([f for f in os.listdir(REVIEW_DIR)
                    if not f.startswith('.') and f not in ['日志.md', '台账.md']
                    and os.path.isfile(os.path.join(REVIEW_DIR, f))])

    if not files:
        return [], []

    archived = []
    pending = []
    xml_moved = 0

    print(f"\n{'='*60}")
    print(f"📋 阶段2: 扫描 02 待核实/ ({len(files)} 个文件)")
    print(f"{'='*60}")

    for f in files:
        src = os.path.join(REVIEW_DIR, f)
        _, ext = os.path.splitext(f)

        # XML文件移回01待分类（下次运行由XML预处理处理）
        if ext.lower() == '.xml':
            dst = os.path.join(INPUT_DIR, f)
            if os.path.exists(dst):
                name, ext2 = os.path.splitext(f)
                counter = 1
                while os.path.exists(dst):
                    dst = os.path.join(INPUT_DIR, f"{name}_{counter}{ext2}")
                    counter += 1
            shutil.move(src, dst)
            xml_moved += 1
            review_log_entries.append((f, "→01待分类(XML重新处理)", "", "XML文件"))
            print(f"   🔄 XML移回01待分类: {f}")
            continue

        if is_standard_name(f):
            # 文件名已符合标准格式 → 用户已核实，归档到 03 已完成
            # v3.20: 检查是否已有状态后缀，没有则自动追加
            # v3.22: 序号放在末尾(状态后缀之后)
            m = STANDARD_NAME_RE.match(f)
            # 新正则: group1=日期, group2=类别, group3=金额, group4=路线, group5=后缀, group6=MMDD, group7=WB/YB, group8=NNN序号, group9=扩展名
            # 02待核实文件不含序号，需要用不含序号的旧正则检查
            # 用简单正则匹配不含序号的标准格式
            m_noseq = re.match(
                r'^(\d{4}-\d{2}-\d{2})_(' + '|'.join(re.escape(c) for c in VALID_CATEGORIES) + r')_(\d+\.\d{2})'
                r'(?:_([^_\d]+(?:-[^_\d]+)?(?:_[\u4e00-\u9fa5]{2,10})?))?'
                r'(?:_(\d{1,4}))?'
                r'(?:_(\d{4})_(WB|YB))?'
                r'(\.\w+)$', f)
            if m_noseq:
                seq_suffix = f"_{next_seq:03d}"
                inv_date = m_noseq.group(1)
                inv_cat = m_noseq.group(2)
                inv_amount = m_noseq.group(3)
                inv_route = m_noseq.group(4) or ""
                inv_suffix = m_noseq.group(5) or ""
                inv_mmdd = m_noseq.group(6) or ""
                inv_status = m_noseq.group(7) or ""

                route_part = f"_{inv_route}" if inv_route else ""
                suffix_part = f"_{inv_suffix}" if inv_suffix else ""
                if inv_mmdd and inv_status:
                    status_part = f"_{inv_mmdd}_{inv_status}"
                else:
                    status_suffix = make_status_suffix()
                    status_part = status_suffix
                inv_ext = m_noseq.group(8)

                archive_name = f"{inv_date}_{inv_cat}_{inv_amount}{route_part}{suffix_part}{status_part}{seq_suffix}{inv_ext}"
            else:
                # 文件名可能有其他格式，在末尾加序号
                seq_suffix = f"_{next_seq:03d}"
                name_part, ext_part = os.path.splitext(f)
                # 检查是否已有状态后缀
                if re.search(r'_\d{4}_(WB|YB)$', name_part):
                    archive_name = f"{name_part}{seq_suffix}{ext_part}"
                else:
                    status_suffix = make_status_suffix()
                    archive_name = f"{name_part}{status_suffix}{seq_suffix}{ext_part}"

            month = get_month_from_filename(f)
            month_dir = os.path.join(DONE_DIR, month)
            os.makedirs(month_dir, exist_ok=True)
            dst = os.path.join(month_dir, archive_name)

            # 重名处理
            if os.path.exists(dst):
                name, ext = os.path.splitext(archive_name)
                counter = 1
                while os.path.exists(dst):
                    dst = os.path.join(month_dir, f"{name}_{counter}{ext}")
                    counter += 1

            shutil.move(src, dst)
            next_seq += 1
            archived.append(archive_name)
            review_log_entries.append((f, f"→03已完成/{month}", archive_name, "手动核实后归档"))
            print(f"   ✅ 已核实归档: {f} → 03 已完成/{month}/")
        else:
            pending.append(f)

    if xml_moved > 0:
        print(f"\n   📊 XML文件移回01待分类: {xml_moved} 个（下次运行自动处理）")

    if pending:
        print(f"\n   ⏳ 仍待核实 ({len(pending)} 个，需手动重命名为标准格式):")
        for f in pending:
            print(f"      - {f}")
        print(f"\n   💡 标准格式: YYYY-MM-DD_类别_金额.扩展名")
        print(f"   💡 类别: {' | '.join(VALID_CATEGORIES)}")
        print(f"   💡 示例: 2026-03-15_餐饮_358.00.pdf 或 2026-03-15_餐饮_358.00.jpg")

    return archived, review_log_entries


# ===== 主流程 =====

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

    if not ensure_configured():
        return

    os.makedirs(DONE_DIR, exist_ok=True)
    os.makedirs(REVIEW_DIR, exist_ok=True)

    print(f"🤖 发票自动整理 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 升级到支持住宿城市命名后，首次运行时迁移历史 03 已完成文件。
    migrate_done_lodging_city_names()

    # 阶段1: 处理新文件
    success, review, dup_deleted, inbox_log_entries = process_inbox()

    # 阶段2: 处理已核实文件
    archived, review_log_entries = process_review()

    # 汇总
    print(f"\n{'='*60}")
    print(f"📊 本次运行汇总")
    print(f"{'='*60}")
    print(f"   01待分类 → 03已完成: {len(success)} 个")
    print(f"   01待分类 → 02待核实: {len(review)} 个")
    print(f"   去重删除:            {dup_deleted} 个")
    print(f"   02待核实 → 03已完成: {len(archived)} 个（手动核实后自动归档）")

    if success:
        summary = defaultdict(lambda: defaultdict(float))
        for _, _, d, amt, cat in success:
            summary[d[:7]][cat] += float(amt)
        print(f"\n   📈 新归档按月汇总:")
        grand = 0
        for month in sorted(summary.keys()):
            cats = summary[month]
            total = sum(cats.values())
            grand += total
            items = " | ".join(f"{c}: ¥{v:,.2f}" for c, v in sorted(cats.items()))
            print(f"     {month}  ¥{total:,.2f}  [{items}]")
        print(f"     小计: ¥{grand:,.2f}")

    # 记录日志
    log = load_log()
    log["runs"].append({
        "time": datetime.now().isoformat(),
        "inbox_to_done": len(success),
        "inbox_to_review": len(review),
        "dup_deleted": dup_deleted,
        "review_to_done": len(archived),
    })
    save_log(log)

    total_done = len(success) + len(archived)
    if total_done == 0 and not review and dup_deleted == 0:
        print(f"\n✨ 无新文件，所有文件已就绪。")
    else:
        print(f"\n✅ 完成。")

    # 最终状态
    inbox_count = sum(1 for f in os.listdir(INPUT_DIR) if is_business_file(os.path.join(INPUT_DIR, f))) if os.path.isdir(INPUT_DIR) else 0
    review_count = sum(1 for f in os.listdir(REVIEW_DIR) if is_business_file(os.path.join(REVIEW_DIR, f))) if os.path.isdir(REVIEW_DIR) else 0
    done_count = sum(
        1
        for root, _, files in os.walk(DONE_DIR)
        for f in files
        if is_business_file(os.path.join(root, f))
    ) if os.path.isdir(DONE_DIR) else 0
    print(f"\n📁 当前状态: 01待分类={inbox_count} | 02待核实={review_count} | 03已完成={done_count}")

    # 更新台账
    update_ledgers()

    # ===== 追加01待分类流水日志 =====
    append_flow_log(INPUT_DIR, "01 待分类", inbox_log_entries, success, review, dup_deleted)

    # ===== 追加02待核实流水日志 =====
    append_flow_log(REVIEW_DIR, "02 待核实", review_log_entries, archived, [], 0)

    # 行程关联: 将新归档发票自动复制到匹配行程的附件目录
    if success:
        link_to_trips(success)


def link_to_trips(success_list):
    """将新归档发票自动关联到已有行程，复制到对应附件目录"""
    # 从 config 读取行程根目录 (可被 config.py 覆盖)
    trip_root = globals().get('TRIP_ROOT', "")
    if not trip_root:
        return
    # 发票类别→附件子目录映射 (从 config 读取，可被 config.py 覆盖)
    if 'CAT_TO_SUBDIR' in dir():
        cat_to_subdir = CAT_TO_SUBDIR
    else:
        cat_to_subdir = {
            "机票": "机票高铁", "机票(保险)": "机票高铁", "高铁": "机票高铁",
            "住宿": "住宿", "住宿(结账单)": "住宿",
            "餐饮": "餐饮",
            "滴滴打车": "打车", "滴滴打车(行程单)": "打车",
            "礼品": "礼品",
            "高速费": "其他", "高速费(行程单)": "其他", "充电费": "其他",
            "行程单": "其他", "结账单": "其他", "其他": "其他",
        }

    # 扫描所有行程
    trips = []
    year_dir = os.path.join(trip_root, "2026 年")
    if not os.path.isdir(year_dir):
        return
    for month_name in os.listdir(year_dir):
        month_dir = os.path.join(year_dir, month_name)
        if not os.path.isdir(month_dir):
            continue
        for folder in os.listdir(month_dir):
            folder_path = os.path.join(month_dir, folder)
            if not os.path.isdir(folder_path):
                continue
            # 解析行程日期范围: 出差N-YYYY-MM-DD～YYYY-MM-DD_路线
            m = re.match(r'出差\d+-(\d{4}-\d{2}-\d{2})～(\d{4}-\d{2}-\d{2})', folder)
            if m:
                trips.append({
                    'start': m.group(1),
                    'end': m.group(2),
                    'folder_path': folder_path,
                    'folder_name': folder,
                    'month_name': month_name,
                })

    if not trips:
        return

    linked_count = 0
    for dest_path, new_name, date, amount, category in success_list:
        # 查找日期匹配的行程
        for trip in trips:
            start_dt = datetime.strptime(trip['start'], '%Y-%m-%d')
            end_dt = datetime.strptime(trip['end'], '%Y-%m-%d')
            inv_dt = datetime.strptime(date, '%Y-%m-%d')
            if inv_dt < start_dt or inv_dt > end_dt:
                continue

            subdir = cat_to_subdir.get(category, '其他')
            dest_dir = os.path.join(trip['folder_path'], '02-发票文件', subdir)
            if not os.path.isdir(dest_dir):
                continue

            dest_file = os.path.join(dest_dir, new_name)
            if os.path.exists(dest_file):
                continue

            shutil.copy2(dest_path, dest_file)
            linked_count += 1
            print(f"   🔗 关联到出差: {new_name} → {trip['folder_name']}/{subdir}/")

    if linked_count > 0:
        print(f"   ✅ 关联 {linked_count} 张发票到行程附件")
        # 更新行程发票文件清单
        _update_trip_invoice_lists(trips)
    else:
        print(f"   ℹ️ 无新发票需要关联行程")


def _update_trip_invoice_lists(trips):
    """更新行程的发票文件清单.md"""
    # 从 config 读取配置 (可被 config.py 覆盖)
    non_reimburse = globals().get('NON_REIMBURSE',
        ["行程单", "滴滴打车(行程单)", "高速费(行程单)", "住宿(结账单)", "结账单"])
    cat_to_subdir = globals().get('CAT_TO_SUBDIR', {
        "机票": "机票高铁", "机票(保险)": "机票高铁", "高铁": "机票高铁",
        "住宿": "住宿", "住宿(结账单)": "住宿",
        "餐饮": "餐饮",
        "滴滴打车": "打车", "滴滴打车(行程单)": "打车",
        "礼品": "礼品",
        "高速费": "其他", "高速费(行程单)": "其他", "充电费": "其他",
        "行程单": "其他", "结账单": "其他", "其他": "其他",
    })
    subdirs = globals().get('SUBDIRS', ["机票高铁", "住宿", "餐饮", "打车", "礼品", "其他"])

    for trip in trips:
        invoice_dir = os.path.join(trip['folder_path'], '02-发票文件')
        if not os.path.isdir(invoice_dir):
            continue

        # 扫描附件目录中的所有发票文件
        all_invoices = []
        for subdir in subdirs:
            subdir_path = os.path.join(invoice_dir, subdir)
            if not os.path.isdir(subdir_path):
                continue
            for fname in os.listdir(subdir_path):
                m = STANDARD_NAME_RE.match(fname)
                if not m:
                    continue
                # 新正则: group1=日期, group2=类别, group3=金额, group4=路线, group5=后缀, group6=MMDD, group7=WB/YB, group8=NNN序号, group9=扩展名
                seq = m.group(8)        # 序号NNN(末尾)
                inv_date = m.group(1)   # 日期
                category = m.group(2)   # 类别
                amount = m.group(3)     # 金额
                route = m.group(4) or ""    # 路线
                suffix = m.group(5) or ""   # 后缀
                op_date = m.group(6) or ""  # 操作日期MMDD
                status = m.group(7) or "WB"  # 报销状态WB/YB
                ext = m.group(9)
                all_invoices.append({
                    'date': inv_date, 'category': category, 'amount': amount,
                    'route': route, 'suffix': suffix, 'ext': ext,
                    'seq': int(seq), 'op_date': op_date, 'status': status,
                    'filename': fname,
                    'is_reimburse': category not in non_reimburse,
                    'subdir': cat_to_subdir.get(category, '其他'),
                })

        if not all_invoices:
            continue

        # 按子目录分组
        by_subdir = defaultdict(list)
        total_reimburse = 0
        total_all = 0
        for inv in all_invoices:
            by_subdir[inv['subdir']].append(inv)
            amt = float(inv['amount'])
            total_all += amt
            if inv['is_reimburse']:
                total_reimburse += amt

        count_reimburse = sum(1 for i in all_invoices if i['is_reimburse'])

        # 生成清单MD
        md = f"# 发票文件清单 — {trip['folder_name'].split('_', 1)[1] if '_' in trip['folder_name'] else trip['folder_name']}\n\n"
        md += f"## 概览\n\n"
        md += f"| 项目 | 数量 | 金额 |\n|------|------|------|\n"
        md += f"| 发票总数 | {len(all_invoices)} | ¥{total_all:,.2f} |\n"
        md += f"| 正式发票(可报销) | {count_reimburse} | ¥{total_reimburse:,.2f} |\n"
        md += f"| 辅助文件(行程单/结账单) | {len(all_invoices) - count_reimburse} | ¥{total_all - total_reimburse:,.2f} |\n\n"

        for subdir in subdirs:
            items = by_subdir.get(subdir, [])
            if not items:
                continue
            subdir_total = sum(float(i['amount']) for i in items)
            md += f"## {subdir}（{len(items)}张，¥{subdir_total:,.2f}）\n\n"
            md += f"| 序号 | 日期 | 类别 | 金额 | 路线/备注 | 报销状态 | 文件名 |\n|------|------|------|------|------|----------|------|\n"
            for i in sorted(items, key=lambda x: x.get('seq', 0)):
                remark = i['route'] if i['route'] else i['suffix']
                seq = i.get('seq', 0)
                md += f"| {seq:03d} | {i['date']} | {i['category']} | ¥{float(i['amount']):,.2f} | {remark} | {i.get('status', 'WB')} | {i['filename']} |\n"
            md += "\n"

        md += f"\n> 📁 附件目录: [[个人行程与报销/02 行程与员工报销单/2026 年/{trip['month_name']}/{trip['folder_name']}/02-发票文件|02-发票文件]]\n"
        md += f"> 📝 行程详情: [[个人行程与报销/02 行程与员工报销单/2026 年/{trip['month_name']}/{trip['folder_name']}/01-行程详情|01-行程详情]]\n"

        md_path = os.path.join(invoice_dir, "发票文件清单.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)


def _gen_master_ledger(all_records, stage_data):
    """生成个人行程与报销总台账（合并三阶段+行程统计）"""
    NON_REIMBURSE = ["行程单", "滴滴打车(行程单)", "高速费(行程单)", "住宿(结账单)", "结账单"]
    CAT_ORDER = ["机票", "机票(保险)", "高铁", "住宿", "住宿(结账单)", "餐饮",
                 "滴滴打车", "滴滴打车(行程单)", "礼品", "高速费", "高速费(行程单)",
                 "充电费", "其他", "结账单", "行程单", "未分类"]

    total = len(all_records)
    r_count = sum(1 for r in all_records if r['reimburse'])
    r_total = sum(r['amount'] for r in all_records if r['reimburse'])

    # 阶段统计
    stage_stats = defaultdict(lambda: {'count': 0, 'rc': 0, 'ra': 0.0})
    for r in all_records:
        s = r['stage']
        stage_stats[s]['count'] += 1
        if r['reimburse']:
            stage_stats[s]['rc'] += 1
            stage_stats[s]['ra'] += r['amount']

    # 类别统计
    cat_stats = defaultdict(lambda: {'count': 0, 'rc': 0, 'ra': 0.0})
    for r in all_records:
        c = r['cat'] or '未分类'
        cat_stats[c]['count'] += 1
        if r['reimburse']:
            cat_stats[c]['rc'] += 1
            cat_stats[c]['ra'] += r['amount']

    # 月度统计（03已完成）
    monthly_stats = defaultdict(lambda: {'count': 0, 'rc': 0, 'ra': 0.0})
    for r in stage_data.get('03已完成', []):
        m = r.get('month', '')
        if m:
            monthly_stats[m]['count'] += 1
            if r['reimburse']:
                monthly_stats[m]['rc'] += 1
                monthly_stats[m]['ra'] += r['amount']

    today = datetime.now().strftime('%Y-%m-%d')
    md = f"# 个人行程与报销 · 总台账\n\n"
    md += f"> 合并01待分类、02待核实、03已完成数据，用于全局快速查询与核查。\n"
    md += f"> 最后更新: {today} | 自动生成，脚本每次运行后同步更新\n\n---\n\n"

    md += "## 全局概览\n\n"
    md += f"| 指标 | 数值 |\n|------|------|\n"
    md += f"| 文件总数 | {total} |\n| 正式发票数 | {r_count} |\n| 报销金额合计 | ¥{r_total:,.2f} |\n\n"

    md += "## 各阶段分布\n\n"
    md += "| 阶段 | 文件数 | 正式发票数 | 报销金额 |\n|------|--------|-----------|----------|\n"
    for sk in ['01待分类', '02待核实', '03已完成']:
        s = stage_stats.get(sk, {'count':0, 'rc':0, 'ra':0.0})
        md += f"| {sk.replace('待', ' 待').replace('已完成', ' 已完成')} | {s['count']} | {s['rc']} | ¥{s['ra']:,.2f} |\n"
    md += f"| **合计** | **{total}** | **{r_count}** | **¥{r_total:,.2f}** |\n\n"

    md += "## 类别统计（全局）\n\n"
    md += "| 类别 | 文件数 | 计入报销 | 报销金额 |\n|------|--------|----------|----------|\n"
    for cat in CAT_ORDER:
        if cat in cat_stats:
            s = cat_stats[cat]
            md += f"| {cat} | {s['count']} | {s['rc']} | ¥{s['ra']:,.2f} |\n"
    for cat in sorted(cat_stats.keys()):
        if cat not in CAT_ORDER:
            s = cat_stats[cat]
            md += f"| {cat} | {s['count']} | {s['rc']} | ¥{s['ra']:,.2f} |\n"
    md += f"| **合计** | **{total}** | **{r_count}** | **¥{r_total:,.2f}** |\n\n"

    md += "## 月度归档统计（03已完成）\n\n"
    md += "| 月份 | 文件数 | 正式发票数 | 报销金额 |\n|------|--------|-----------|----------|\n"
    for m in sorted(monthly_stats.keys()):
        s = monthly_stats[m]
        md += f"| {m} | {s['count']} | {s['rc']} | ¥{s['ra']:,.2f} |\n"
    md += "\n"

    md += """## 行程关联统计

> 数据来源: [[03 行程/2026 年/行程总览|行程总览]]

| 指标 | 数值 |
|------|------|
| 总出差次数 | 3 |
| 总出差天数 | 17天 |
| 行程报销金额 | ¥13,953.88 |

| 出差 | 日期范围 | 天数 | 路线 | 正式发票数 | 报销金额 | 状态 |
|------|---------|------|------|----------|---------|------|
| 1 | 01-04～01-09 | 5 | 广州-上海-杭州-成都-重庆-广州 | 8 | ¥1,761.88 | ✅ |
| 2 | 01-11～01-14 | 3 | 广州-上海-昆山-上海-南京-广州 | 3 | ¥12,192.00 | ✅ |
| 3 | 01-26～02-04 | 9 | 广州-重庆-上海-昆山-上海-苏州-南京-上海-广州 | 0⚠️ | ¥0.00 | ⚠️缺失 |

"""

    # 全部发票记录（03已完成）
    r3 = sorted(stage_data.get('03已完成', []), key=lambda r: (r.get('date','9999'), r['filename']))
    md += "## 全部发票记录（03已完成）\n\n"
    md += "| # | 日期 | 类别 | 金额 | 路线 | 发票号后4位 | 计入报销 | 归档月份 | 文件名 |\n"
    md += "|---|------|------|------|------|-----------|----------|----------|--------|\n"
    for i, r in enumerate(r3, 1):
        rk = "✅" if r['reimburse'] else "❌"
        md += f"| {i} | {r['date']} | {r['cat']} | ¥{r['amount']:,.2f} | {r['route'] or ''} | {r['suffix'] or ''} | {rk} | {r.get('month','')} | `{r['filename']}` |\n"

    # 待处理文件
    pending = sorted(
        stage_data.get('01待分类', []) + stage_data.get('02待核实', []),
        key=lambda r: (r['stage'], r.get('date','9999'), r['filename'])
    )
    if pending:
        md += "\n## 待处理文件\n\n"
        md += "| # | 阶段 | 日期 | 类别 | 金额 | 文件名 |\n"
        md += "|---|------|------|------|------|--------|\n"
        for i, r in enumerate(pending, 1):
            md += f"| {i} | {r['stage']} | {r['date'] or '-'} | {r['cat'] or '-'} | ¥{r['amount']:,.2f} | `{r['filename']}` |\n"

    # 发票号索引
    sr = [r for r in r3 if r['suffix']]
    if sr:
        md += "\n## 发票号后4位索引（03已完成）\n\n"
        md += "| 后4位 | 日期 | 类别 | 金额 | 文件名 |\n|-------|------|------|------|--------|\n"
        for r in sorted(sr, key=lambda r: r['suffix']):
            md += f"| {r['suffix']} | {r['date']} | {r['cat']} | ¥{r['amount']:,.2f} | `{r['filename']}` |\n"

    md += "\n---\n\n## 台账与日志链接\n\n"
    md += "- [[01 发票整理/01 待分类/日志|01 待分类日志]]\n"
    md += "- [[01 发票整理/02 待核实/日志|02 待核实日志]]\n"
    md += "- [[01 发票整理/03 已完成/台账|03 已完成台账]]\n"
    md += "- [[03 行程/2026 年/行程总览|行程总览]]\n"

    # 总台账路径 (从 config.py 读取，可被覆盖)
    ledger_path = globals().get('TOTAL_LEDGER_PATH',
        os.path.join(os.path.dirname(os.path.dirname(INPUT_DIR)), "总台账.md"))
    with open(ledger_path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f"   📋 总台账更新: {total} 条记录, 报销 ¥{r_total:,.2f}")

def append_flow_log(dir_path, stage_label, log_entries, success_list, review_list, dup_count):
    """追加流水日志到 01待分类/日志.md 或 02待核实/日志.md
    
    每次运行追加一条运行记录，包含：
    - 运行时间
    - 每个文件的处理流水（原始名→去向→新名→识别结果）
    - 运行汇总（归档/待核实/删除数量）
    """
    log_path = os.path.join(dir_path, "日志.md")
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 如果日志文件不存在，创建初始结构
    if not os.path.exists(log_path):
        init_md = f"# {stage_label}日志\n\n"
        init_md += f"> 流水记录模式：每次运行追加处理过程，记录文件的进出流转。\n\n"
        init_md += "---\n\n"
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(init_md)
    
    # 读取现有内容
    with open(log_path, 'r', encoding='utf-8') as f:
        existing = f.read()
    
    # 构建本次运行记录
    run_md = f"\n## 🕐 {now_str}\n\n"
    
    # 汇总
    if stage_label == "01 待分类":
        run_md += f"| 指标 | 数值 |\n|------|------|\n"
        run_md += f"| 归档到03已完成 | {len(success_list)} |\n"
        run_md += f"| 移到02待核实 | {len(review_list)} |\n"
        run_md += f"| 去重删除 | {dup_count} |\n\n"
    else:
        run_md += f"| 指标 | 数值 |\n|------|------|\n"
        run_md += f"| 归档到03已完成 | {len(success_list)} |\n\n"
    
    # 文件处理流水
    if log_entries:
        run_md += f"### 文件处理流水\n\n"
        run_md += "| # | 原始文件名 | 去向 | 新文件名 | 识别结果 |\n"
        run_md += "|---|------------|------|----------|----------|\n"
        for i, (orig, dest, new_name, detail) in enumerate(log_entries, 1):
            # 原始文件名可能很长，截断显示
            orig_short = orig[:50] + "..." if len(orig) > 50 else orig
            new_short = new_name[:40] + "..." if len(new_name) > 40 else (new_name or "")
            run_md += f"| {i} | `{orig_short}` | {dest} | `{new_short}` | {detail} |\n"
        run_md += "\n"
    
    # 如果有归档成功的，列出详细识别结果
    if success_list and stage_label == "01 待分类":
        run_md += "### 归档详情\n\n"
        run_md += "| # | 原始名(截断) | 新文件名 | 日期 | 类别 | 金额 |\n"
        run_md += "|---|-------------|----------|------|------|------|\n"
        for i, (orig, new, date, amt, cat) in enumerate(success_list, 1):
            orig_short = orig[:40] + "..." if len(orig) > 40 else orig
            run_md += f"| {i} | `{orig_short}` | `{new}` | {date} | {cat} | ¥{amt} |\n"
        run_md += "\n"
    
    if success_list and stage_label == "02 待核实":
        run_md += "### 已核实归档\n\n"
        run_md += "| # | 文件名 | 去往 |\n"
        run_md += "|---|--------|------|\n"
        for i, f in enumerate(success_list, 1):
            run_md += f"| {i} | `{f}` | → 03已完成 |\n"
        run_md += "\n"
    
    run_md += "---\n\n"
    
    # 追加到现有内容
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(existing + run_md)
    
    total_entries = len(log_entries) if log_entries else 0
    print(f"   📝 日志追加: {stage_label} ({total_entries} 条处理记录)")

def update_ledgers():
    """扫描03已完成目录，生成台账MD文件。01/02日志由main()追加流水记录。"""
    # 从 config 读取 (可被 config.py 覆盖)
    non_reimburse = globals().get('NON_REIMBURSE',
        ["行程单", "滴滴打车(行程单)", "高速费(行程单)", "住宿(结账单)", "结账单"])

    def parse_filename(fname):
        m = STANDARD_NAME_RE.match(fname)
        if not m:
            # 降级: 旧格式无序号无状态后缀
            m2 = re.match(r'(\d{4}-\d{2}-\d{2})_(' + '|'.join(re.escape(c) for c in VALID_CATEGORIES) + r')_(\d+\.\d{2})', fname)
            if not m2:
                return None
            date, cat, amount = m2.group(1), m2.group(2), float(m2.group(3))
            rest = fname[m2.end():]
            ext = os.path.splitext(fname)[1]
            rest = rest[:-len(ext)] if rest.endswith(ext) else rest
            parts = rest.split('_') if rest else []
            route, suffix, op_date, status, seq = '', '', '', 'WB', 0
        else:
            seq = int(m.group(8))    # group 8 = NNN 序号(末尾)
            date = m.group(1)        # group 1 = 日期
            cat = m.group(2)         # group 2 = 类别
            amount = float(m.group(3))  # group 3 = 金额
            route = m.group(4) or ''    # group 4 = 路线
            suffix = m.group(5) or ''   # group 5 = 后缀
            op_date = m.group(6) or ''  # group 6 = MMDD
            status = m.group(7) or 'WB'  # group 7 = WB/YB
        base_cat = cat.split('(')[0]
        return {'date': date, 'cat': cat, 'amount': amount, 'route': route, 'suffix': suffix,
                'op_date': op_date, 'status': status, 'seq': seq,
                'reimburse': cat not in non_reimburse, 'filename': fname}

    def scan_dir(dir_path, is_done=False):
        records = []
        ALL_EXTENSIONS = ('.pdf', '.ofd', '.xml', '.xlsx', '.zip',
                          '.jpg', '.jpeg', '.png', '.heic', '.bmp', '.tiff', '.tif', '.webp')
        if is_done:
            for month_dir in sorted(os.listdir(dir_path)):
                month_path = os.path.join(dir_path, month_dir)
                if not os.path.isdir(month_path): continue
                for fname in sorted(os.listdir(month_path)):
                    if fname.startswith('.') or not fname.endswith(ALL_EXTENSIONS): continue
                    info = parse_filename(fname)
                    if info:
                        info['month'] = month_dir
                        records.append(info)
                    else:
                        records.append({'date': '', 'cat': '', 'amount': 0, 'route': '', 'suffix': '',
                                        'reimburse': True, 'filename': fname, 'month': month_dir})
        else:
            if not os.path.isdir(dir_path): return records
            for fname in sorted(os.listdir(dir_path)):
                if fname.startswith('.') or not fname.endswith(ALL_EXTENSIONS): continue
                fpath = os.path.join(dir_path, fname)
                if not os.path.isfile(fpath): continue
                info = parse_filename(fname)
                if info: records.append(info)
                else: records.append({'date': '', 'cat': '', 'amount': 0, 'route': '', 'suffix': '',
                                      'reimburse': True, 'filename': fname})
        return records

    def gen_md(stage_label, records, is_done=False, doc_type="台账"):
        total = len(records)
        r_count = sum(1 for r in records if r['reimburse'])
        r_total = sum(r['amount'] for r in records if r['reimburse'])
        cat_stats = defaultdict(lambda: {'count': 0, 'rc': 0, 'ra': 0.0})
        for r in records:
            c = r['cat'] or '未分类'
            cat_stats[c]['count'] += 1
            if r['reimburse']:
                cat_stats[c]['rc'] += 1
                cat_stats[c]['ra'] += r['amount']
        records.sort(key=lambda r: (r.get('date', ''), r['filename']))
        md = f"# {stage_label}{doc_type}\n\n"
        md += f"> 自动生成，用于快速查询与核查。最后更新: {datetime.now().strftime('%Y-%m-%d')}\n\n"
        md += "## 概览统计\n\n"
        md += f"| 指标 | 数值 |\n|------|------|\n"
        md += f"| 文件总数 | {total} |\n| 正式发票数 | {r_count} |\n| 报销金额合计 | ¥{r_total:,.2f} |\n\n"
        md += "## 类别统计\n\n"
        md += "| 类别 | 文件数 | 计入报销数 | 报销金额 |\n|------|--------|-----------|----------|\n"
        for cat in sorted(cat_stats.keys(), key=lambda c: cat_stats[c]['ra'], reverse=True):
            s = cat_stats[cat]
            md += f"| {cat} | {s['count']} | {s['rc']} | ¥{s['ra']:,.2f} |\n"
        md += f"| **合计** | **{total}** | **{r_count}** | **¥{r_total:,.2f}** |\n\n"
        md += "## 全部记录\n\n"
        if is_done:
            md += "| 序号 | 日期 | 类别 | 金额 | 路线 | 后缀 | 操作日期 | 报销状态 | 计入报销 | 归档月份 | 文件名 |\n"
            md += "|------|------|------|------|------|------|----------|----------|----------|----------|--------|\n"
            for r in sorted(records, key=lambda x: x.get('seq', 0)):
                rk = "✅" if r['reimburse'] else "❌"
                st = r.get('status', '') or ''
                od = r.get('op_date', '') or ''
                seq = r.get('seq', 0)
                md += f"| {seq:03d} | {r['date']} | {r['cat']} | ¥{r['amount']:,.2f} | {r['route'] or ''} | {r['suffix'] or ''} | {od} | {st} | {rk} | {r.get('month', '')} | `{r['filename']}` |\n"
        else:
            md += "| # | 日期 | 类别 | 金额 | 路线 | 后缀 | 操作日期 | 报销状态 | 计入报销 | 文件名 |\n"
            md += "|---|------|------|------|------|------|----------|----------|----------|--------|\n"
            for i, r in enumerate(records, 1):
                rk = "✅" if r['reimburse'] else "❌"
                st = r.get('status', '') or ''
                od = r.get('op_date', '') or ''
                md += f"| {i} | {r['date']} | {r['cat']} | ¥{r['amount']:,.2f} | {r['route'] or ''} | {r['suffix'] or ''} | {od} | {st} | {rk} | `{r['filename']}` |\n"
        sr = [r for r in records if r['suffix']]
        if sr:
            md += "\n## 发票号后4位索引\n\n"
            md += "| 后4位 | 日期 | 类别 | 金额 | 文件名 |\n|-------|------|------|------|--------|\n"
            for r in sorted(sr, key=lambda r: r['suffix']):
                md += f"| {r['suffix']} | {r['date']} | {r['cat']} | ¥{r['amount']:,.2f} | `{r['filename']}` |\n"
        return md

    # 只生成03已完成台账
    records = scan_dir(DONE_DIR, True)
    md = gen_md("03 已完成", records, True, doc_type="台账")
    ledger_path = os.path.join(DONE_DIR, "台账.md")
    with open(ledger_path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f"   📋 台账更新: 03 已完成 ({len(records)} 条)")
    for r in records:
        r['stage'] = "03已完成"

    # 生成总台账
    _gen_master_ledger(records, {"03已完成": records})

if __name__ == "__main__":
    main()
