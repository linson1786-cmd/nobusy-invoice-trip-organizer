"""
配置文件模板 - 首次使用时复制为 config.py 并填写真实值

快速开始:
1. cp config_template.py config.py
2. 编辑 config.py，修改以下必填项:
   - OBSIDIAN_VAULT: 你的 Obsidian 笔记库路径
   - EMAIL_ADDRESS: 你的163邮箱地址
   - EMAIL_AUTH_CODE: 你的163邮箱授权码
3. python3 init.py

注意: BASE_ROOT / INVOICE_ROOT / TRIP_ROOT 等路径由 OBSIDIAN_VAULT 自动计算，
      通常只需修改 OBSIDIAN_VAULT 即可。运行 setup.py init 会自动生成 config.py。
"""
import os

# ========== 必填: 路径配置 ==========

# Obsidian 笔记库根目录
# macOS 示例: "/Users/你的用户名/Library/Mobile Documents/iCloud~md~obsidian/Documents/你的库名"
# Windows 示例: "C:\\Users\\你的用户名\\Documents\\ObsidianVault"
# 不使用 Obsidian 时，指向任意文件夹即可
OBSIDIAN_VAULT = "~/Documents/MyVault"

# 01 文件识别整理目录相对路径 (相对于 OBSIDIAN_VAULT)
INVOICE_BASE_REL = "个人行程与报销/01 文件识别整理"

# 行程与报销单目录相对路径 (相对于 OBSIDIAN_VAULT)
TRIP_BASE_REL = "个人行程与报销/02 行程与员工报销单"

# ===== 以下路径由上面三项自动计算，通常无需手动修改 =====
# 01 文件识别整理根目录（脚本用）
BASE_ROOT = os.path.join(os.path.expanduser(OBSIDIAN_VAULT), INVOICE_BASE_REL)
INPUT_DIR = os.path.join(BASE_ROOT, "01 待分类")
DONE_DIR = os.path.join(BASE_ROOT, "03 已完成")
REVIEW_DIR = os.path.join(BASE_ROOT, "02 待核实")
LOG_FILE = os.path.join(BASE_ROOT, ".organizer_log.json")

# 行程根目录（trip脚本用）
INVOICE_ROOT = BASE_ROOT
TRIP_ROOT = os.path.join(os.path.expanduser(OBSIDIAN_VAULT), TRIP_BASE_REL)

# 报销单 Excel 模板路径 (如使用报销单生成功能，填写模板路径; 否则留空)
REIMBURSEMENT_TEMPLATE = ""


# ========== 必填: 邮箱配置 ==========

# 163 邮箱
EMAIL_ADDRESS = "your_email@163.com"      # 改为你的163邮箱
EMAIL_AUTH_CODE = "YOUR_AUTH_CODE"         # 改为你的163邮箱授权码 (非登录密码!)
IMAP_SERVER = "imap.163.com"
IMAP_PORT = 993

# QQ 邮箱 (可选)
QQ_EMAIL_ADDRESS = ""
QQ_EMAIL_AUTH_CODE = ""

# 邮件附件下载目录 (相对于项目目录)
EMAIL_DOWNLOAD_DIR = "email_attachments"


# ========== 一般无需修改 ==========

VALID_CATEGORIES = [
    "餐饮", "住宿", "住宿比价图", "机票", "机票比价图", "高铁", "高铁比价图", "滴滴打车", "行程单", "高速费", "充电费", "油电类", "礼品", "结账单", "其他",
    "机票(保险)", "滴滴打车(行程单)", "住宿(结账单)", "高速费(行程单)"
]

IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.heic', '.bmp', '.tiff', '.tif', '.webp']

CAT_TO_SUBDIR = {
    "机票": "机票高铁", "机票(保险)": "机票高铁", "机票比价图": "机票高铁", "高铁": "机票高铁", "高铁比价图": "机票高铁",
    "住宿": "住宿", "住宿(结账单)": "住宿", "住宿比价图": "住宿",
    "餐饮": "餐饮",
    "滴滴打车": "打车", "滴滴打车(行程单)": "打车",
    "礼品": "礼品",
    "高速费": "其他", "高速费(行程单)": "其他",
    "充电费": "其他", "油电类": "其他", "行程单": "其他", "结账单": "其他", "其他": "其他",
}

SUBDIRS = ["机票高铁", "住宿", "打车", "礼品", "其他"]
NON_REIMBURSE = ["行程单", "滴滴打车(行程单)", "高速费(行程单)", "住宿(结账单)", "结账单", "机票比价图", "高铁比价图", "住宿比价图"]

CATEGORY_RULES = [
    # ===== 比价图类（最优先，防止 OTA 截图被通用词抢先匹配）=====
    (["直飞", "乘机人", "托运行李", "机场燃油", "机建燃油",
      "机票比价", "余票紧张", "免费手提行李",
      "出发城市", "到达城市", "起降时间", "航班动态",
      "飞常准", "值机柜台", "登机口", "准点分析", "前序航班",
      "行李转盘", "到达口"], "机票比价图"),
    (["乘车人", "车次", "运行时间", "出发站", "到达站", "12306",
      "抢票", "候补", "高铁比价", "火车票比价",
      "预订成功", "预定成功", "订单详情",
      "历时", "检票口", "询车票"], "高铁比价图"),
    (["房型", "大床房", "双床房", "标准间", "豪华房", "亲子房",
      "入住人", "连住", "每晚",
      "住宿比价", "酒店比价"], "住宿比价图"),
    # ===== 发票类 =====
    (["结账单", "水单"], "结账单"),
    (["行程单", "行程报销单", "出行记录", "出行行程"], "行程单"),
    (["住宿", "酒店", "华住", "全季", "入住", "房费", "离店"], "住宿"),
    (["蟹", "手信", "礼品", "礼盒", "水果", "玩具",
      "日用杂品", "日用品", "日化用品",
      "移动通信设备", "通讯器材"], "礼品"),
    (["高速", "通行费", "路桥费", "ETC"], "高速费"),
    (["充电费", "蔚来", "NIO", "换电", "充电桩"], "充电费"),
    (["加油", "汽油", "柴油", "中石化", "中石油", "中海油", "壳牌",
      "油品", "燃油费", "加油站", "供电", "电费", "充电服务"], "油电类"),
    (["滴滴", "打车", "网约车", "交通运输服务", "客运服务费"], "滴滴打车"),
    (["火车票", "高铁", "车票", "铁路", "电子客票"], "高铁"),
    (["机票", "航空", "航班", "登机牌",
      "保险服务", "经纪代理服务"], "机票"),
    (["餐饮", "餐费", "餐厅", "饭店", "酒水"], "餐饮"),
]

SUBTYPE_RULES = [
    ("机票", ["保险服务", "保险"], "(保险)"),
    ("行程单", ["滴滴", "打车", "网约车"], "(行程单)"),
    ("行程单", ["高速", "通行费", "ETC"], "(行程单)"),
    ("结账单", ["酒店", "住宿", "入住", "离店"], "(结账单)"),
]

MAJOR_CITIES = [
    "上海", "北京", "广州", "深圳", "杭州", "成都", "重庆", "西安",
    "苏州", "南京", "武汉", "天津", "长沙",
    "昆明", "贵阳", "郑州", "合肥",
    "珠海", "中山", "佛山", "东莞",
]

FONT_PATH = "/Library/Fonts/Arial Unicode.ttf"  # macOS 默认
# Windows 用户改为: FONT_PATH = r"C:\Windows\Fonts\arialuni.ttf"

DEBUG = False
OCR_LANGUAGE = "chi_sim+eng"
