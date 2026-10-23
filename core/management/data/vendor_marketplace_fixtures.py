"""Static data for realistic vendor/marketplace development fixtures.

Pure data: no model imports.  The seeder in
``core.management.seeders.vendor_marketplace_fixtures`` resolves these
records against the seeded reference data (categories, brands, variant
attributes, cities) and creates the fixture rows.

The curated catalog only covers roots that the imported Digikala catalog
does not populate.  Products that already exist for a root are reused, so
the generator never duplicates the imported catalog.
"""

SEED_MARKER = "seed_vendor_marketplace"
SHARED_PASSWORD = "Test@123456"

# Cities are stored transliterated by the location fixture; ``label`` is the
# Persian name used in addresses and warehouse names.  Coordinates are the
# real city centres (the fixture's own City.latitude/longitude is sparse).
CITY_PROFILES = [
    {
        "name": "thran",
        "label": "تهران",
        "latitude": "35.689200",
        "longitude": "51.389000",
        "postal_prefix": "11",
    },
    {
        "name": "mshhd",
        "label": "مشهد",
        "latitude": "36.260500",
        "longitude": "59.616800",
        "postal_prefix": "91",
    },
    {
        "name": "asfhan",
        "label": "اصفهان",
        "latitude": "32.654600",
        "longitude": "51.668000",
        "postal_prefix": "81",
    },
    {
        "name": "shyraz",
        "label": "شیراز",
        "latitude": "29.591800",
        "longitude": "52.583700",
        "postal_prefix": "71",
    },
    {
        "name": "tbryz",
        "label": "تبریز",
        "latitude": "38.096200",
        "longitude": "46.273800",
        "postal_prefix": "51",
    },
    {
        "name": "krj",
        "label": "کرج",
        "latitude": "35.835500",
        "longitude": "50.991500",
        "postal_prefix": "31",
    },
    {
        "name": "ahvaz",
        "label": "اهواز",
        "latitude": "31.318300",
        "longitude": "48.670600",
        "postal_prefix": "61",
    },
    {
        "name": "rsht",
        "label": "رشت",
        "latitude": "37.280800",
        "longitude": "49.583200",
        "postal_prefix": "41",
    },
    {
        "name": "krmanshah",
        "label": "کرمانشاه",
        "latitude": "34.314200",
        "longitude": "47.065000",
        "postal_prefix": "67",
    },
    {
        "name": "kysh",
        "label": "کیش",
        "latitude": "26.557800",
        "longitude": "54.019400",
        "postal_prefix": "79",
    },
]

STREETS = [
    "خیابان ولیعصر",
    "خیابان انقلاب",
    "خیابان شریعتی",
    "بلوار کشاورز",
    "میدان ونک",
    "خیابان مطهری",
    "بلوار فردوس",
    "خیابان آزادی",
    "خیابان جمهوری",
    "بلوار میرداماد",
    "بلوار سجاد",
    "خیابان چهارباغ",
]

MALE_FIRST_NAMES = [
    "علی",
    "محمد",
    "رضا",
    "امیر",
    "حسین",
    "مهدی",
    "سعید",
    "مجید",
    "کامران",
    "بابک",
    "پویا",
    "آرش",
    "نوید",
    "سینا",
    "یاسر",
    "فرهاد",
    "بیژن",
    "شهاب",
    "کوروش",
    "رامین",
]

FEMALE_FIRST_NAMES = [
    "فاطمه",
    "زهرا",
    "مریم",
    "سارا",
    "نرگس",
    "الهام",
    "شیما",
    "نازنین",
    "پریسا",
    "مهسا",
    "نگار",
    "آزاده",
    "لیلا",
    "سمیرا",
    "هستی",
    "بهاره",
    "شقایق",
    "یاسمن",
    "سحر",
    "مینا",
]

LAST_NAMES = [
    "رضایی",
    "محمدی",
    "حسینی",
    "کریمی",
    "موسوی",
    "احمدی",
    "جعفری",
    "صادقی",
    "قاسمی",
    "علیزاده",
    "مرادی",
    "اکبری",
    "شریفی",
    "کاظمی",
    "نوری",
    "زمانی",
    "سلطانی",
    "امینی",
    "فرهادی",
    "رستمی",
    "میرزایی",
    "پارسا",
    "خسروی",
    "ایزدی",
    "سلیمانی",
    "طاهری",
    "شمس",
    "کیانی",
    "راد",
    "دهقان",
]

BUSINESS_PREFIXES = [
    "فروشگاه",
    "مجموعه",
    "مرکز خرید",
    "گالری",
    "هایپر",
    "بازرگانی",
    "تجارت",
    "پخش",
    "آتلیه",
    "سی‌وی",
]

BUSINESS_CORES = [
    "پارس",
    "آریا",
    "کیان",
    "نوین",
    "سپهر",
    "الوند",
    "زرین",
    "ماهان",
    "تیام",
    "رادین",
    "بهار",
    "آفتاب",
    "ستاره",
    "الماس",
    "کاسپین",
    "ایرانیان",
    "پرشیا",
    "آریانا",
    "دیبا",
    "سام",
    "نیک",
    "برتر",
    "سرآمد",
    "امید",
    "مهر",
    "خورشید",
    "آسمان",
    "دریا",
    "جوان",
    "پویا",
]

# Each business type owns one or more root categories.  Types are reused
# round-robin so many businesses share categories, which is what makes the
# marketplace comparison and cart flows realistic.
BUSINESS_TYPES = [
    {
        "key": "digital",
        "roots": (1001, 1017, 1009),
        "suffixes": ("دیجیتال", "موبایل", "تکنولوژی"),
    },
    {
        "key": "beauty",
        "roots": (1323, 1598),
        "suffixes": ("آرایشی", "زیبایی", "بهداشت"),
    },
    {
        "key": "home",
        "roots": (1102, 1262),
        "suffixes": ("خانه", "آشپزخانه", "لوازم خانگی"),
    },
    {
        "key": "fashion",
        "roots": (1375, 1491),
        "suffixes": ("پوشاک", "مد", "زرین"),
    },
    {
        "key": "market",
        "roots": (1801, 1960),
        "suffixes": ("سوپرمارکت", "بازرگانی", "محلی"),
    },
    {
        "key": "kids",
        "roots": (1911,),
        "suffixes": ("کودک", "اسباب‌بازی", "نوزاد"),
    },
    {
        "key": "sport",
        "roots": (1763,),
        "suffixes": ("ورزش", "سفر", "کوهستان"),
    },
    {
        "key": "tools",
        "roots": (1666, 1549),
        "suffixes": ("ابزار", "خودرو", "صنعتی"),
    },
    {
        "key": "culture",
        "roots": (1717,),
        "suffixes": ("کتاب", "هنر", "فرهنگی"),
    },
    {
        "key": "pet",
        "roots": (2016,),
        "suffixes": ("پت", "حیوانات", "پت‌شاپ"),
    },
]

# Category-id -> realistic buy-price band in the shop currency.  Existing
# imported products get a deterministic cost inside their category's band;
# curated products use the same table through their leaf category.
CATEGORY_PRICE_BANDS = {
    1001: (8_000_000, 80_000_000),
    1003: (250_000, 2_500_000),
    1004: (150_000, 1_500_000),
    1005: (100_000, 1_200_000),
    1006: (150_000, 1_800_000),
    1007: (100_000, 1_800_000),
    1008: (700_000, 5_000_000),
    1010: (18_000_000, 65_000_000),
    1020: (900_000, 6_000_000),
    1023: (4_000_000, 35_000_000),
    1032: (400_000, 9_000_000),
    1041: (300_000, 5_000_000),
    1095: (3_000_000, 60_000_000),
    1096: (4_000_000, 80_000_000),
    1097: (3_000_000, 25_000_000),
    1098: (1_000_000, 8_000_000),
    1099: (2_000_000, 15_000_000),
    1100: (150_000, 1_200_000),
    1101: (800_000, 6_000_000),
    1124: (200_000, 2_000_000),
    1297: (1_500_000, 8_000_000),
    1305: (1_500_000, 9_000_000),
    1315: (800_000, 5_000_000),
    1323: (200_000, 4_000_000),
    1324: (200_000, 2_500_000),
    1325: (200_000, 1_500_000),
    1330: (150_000, 1_500_000),
    1332: (150_000, 3_000_000),
    1335: (250_000, 2_000_000),
    1352: (80_000, 1_000_000),
    1104: (600_000, 5_000_000),
    1106: (1_500_000, 8_000_000),
    1108: (300_000, 1_500_000),
    1137: (150_000, 800_000),
    1139: (200_000, 900_000),
    1276: (4_000_000, 25_000_000),
    1289: (3_000_000, 18_000_000),
    1292: (1_500_000, 8_000_000),
    1301: (1_500_000, 9_000_000),
    1383: (450_000, 2_500_000),
    1389: (250_000, 1_500_000),
    1400: (350_000, 2_000_000),
    1404: (800_000, 4_000_000),
    1500: (8_000_000, 60_000_000),
    1535: (1_200_000, 8_000_000),
    1547: (1_000_000, 7_000_000),
    1553: (900_000, 6_000_000),
    1567: (1_500_000, 9_000_000),
    1575: (500_000, 3_500_000),
    1600: (700_000, 5_000_000),
    1631: (1_200_000, 6_000_000),
    1636: (150_000, 1_200_000),
    1665: (700_000, 5_000_000),
    1668: (1_500_000, 9_000_000),
    1669: (1_200_000, 7_000_000),
    1683: (1_500_000, 8_000_000),
    1735: (80_000, 500_000),
    1736: (50_000, 400_000),
    1744: (2_000_000, 12_000_000),
    1776: (200_000, 1_200_000),
    1777: (1_200_000, 8_000_000),
    1786: (800_000, 6_000_000),
    1792: (250_000, 1_800_000),
    1803: (40_000, 250_000),
    1804: (700_000, 4_500_000),
    1813: (500_000, 3_500_000),
    1818: (250_000, 2_000_000),
    1850: (400_000, 3_000_000),
    1928: (150_000, 1_200_000),
    1929: (200_000, 1_500_000),
    1948: (3_000_000, 18_000_000),
    1959: (150_000, 1_000_000),
    1963: (700_000, 4_000_000),
    1966: (500_000, 3_500_000),
    1977: (500_000, 3_000_000),
    2016: (150_000, 2_500_000),
}

ROOT_PRICE_BANDS = {
    1001: (150_000, 80_000_000),
    1009: (10_000_000, 65_000_000),
    1017: (150_000, 80_000_000),
    1102: (150_000, 10_000_000),
    1262: (500_000, 30_000_000),
    1323: (80_000, 4_000_000),
    1375: (150_000, 5_000_000),
    1491: (500_000, 60_000_000),
    1549: (100_000, 10_000_000),
    1598: (80_000, 6_000_000),
    1666: (150_000, 10_000_000),
    1717: (50_000, 12_000_000),
    1763: (100_000, 8_000_000),
    1801: (30_000, 4_500_000),
    1911: (100_000, 18_000_000),
    1960: (100_000, 4_000_000),
    2016: (100_000, 3_000_000),
}

# Products created only for roots the imported catalog does not cover.
# ``category`` is the seeded leaf category id; ``variants`` lists one
# selection per variant, keyed by variant-attribute name.
CURATED_PRODUCTS = [
    # Laptops (1009)
    {
        "name": "لپ تاپ لنوو مدل ThinkPad E14 نسل 12",
        "category": 1010,
        "brand": "Lenovo",
        "variants": [{"Storage": "256 GB"}, {"Storage": "512 GB"}],
    },
    {
        "name": "لپ تاپ ایسوس مدل VivoBook 15",
        "category": 1010,
        "brand": "Asus",
        "variants": [{"Storage": "256 GB"}, {"Storage": "512 GB"}],
    },
    {
        "name": "لپ تاپ اچ‌پی مدل ProBook 450 G10",
        "category": 1010,
        "variants": [{"Storage": "256 GB"}, {"Storage": "512 GB"}],
    },
    # Home and kitchen (1102)
    {
        "name": "قابلمه و تابه گرانیتی 5 پارچه",
        "category": 1104,
        "variants": [{"Color": "مشکی"}, {"Color": "طوسی"}],
    },
    {
        "name": "سرویس پخت و پز استیل 12 پارچه",
        "category": 1106,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "ست کفگیر و ملاقه سیلیکونی 6 پارچه",
        "category": 1108,
        "variants": [{"Color": "مشکی"}, {"Color": "قرمز"}],
    },
    {
        "name": "ماگ سرامیکی طرح مینیمال",
        "category": 1137,
        "variants": [{"Color": "سفید"}, {"Color": "مشکی"}, {"Color": "آبی"}],
    },
    {
        "name": "ست لیوان شیشه‌ای 6 عددی",
        "category": 1139,
        "variants": [{"Variant": "Default"}],
    },
    # Home appliances (1262)
    {
        "name": "سرخ کن بدون روغن فیلیپس مدل Airfryer XL",
        "category": 1289,
        "brand": "Philips",
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "پلوپز سامسونگ 1.8 لیتری",
        "category": 1292,
        "brand": "Samsung",
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "چای ساز فیلیپس 1.7 لیتری",
        "category": 1301,
        "brand": "Philips",
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "جارو شارژی سامسونگ مدل Jet",
        "category": 1276,
        "brand": "Samsung",
        "variants": [{"Color": "سفید"}, {"Color": "مشکی"}],
    },
    # Fashion and jewellery (1375 / 1491)
    {
        "name": "تی شرت مردانه نخی یقه گرد",
        "category": 1389,
        "variants": [{"Size": "Small"}, {"Size": "Medium"}, {"Size": "Large"}],
    },
    {
        "name": "هودی مردانه کلاه‌دار",
        "category": 1383,
        "variants": [{"Size": "Small"}, {"Size": "Medium"}, {"Size": "Large"}],
    },
    {
        "name": "کفش اسپرت مردانه مدل رانینگ",
        "category": 1404,
        "variants": [{"Color": "مشکی"}, {"Color": "سفید"}],
    },
    {
        "name": "کیف پول چرم مردانه",
        "category": 1400,
        "variants": [{"Color": "مشکی"}, {"Color": "قهوه ای"}],
    },
    {
        "name": "انگشتر نقره زنانه طرح رومینا",
        "category": 1535,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "گردنبند طلا 18 عیار زنانه",
        "category": 1500,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "دستبند نقره مردانه",
        "category": 1547,
        "variants": [{"Variant": "Default"}],
    },
    # Automotive (1549)
    {
        "name": "روغن موتور کاسترول 5W-30",
        "category": 1553,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "کفپوش خودرو چرمی ست 5 عددی",
        "category": 1575,
        "variants": [{"Color": "مشکی"}, {"Color": "قهوه ای"}],
    },
    {
        "name": "دوربین ثبت وقایع خودرو مدل DVR-1080",
        "category": 1567,
        "variants": [{"Variant": "Default"}],
    },
    # Health (1598)
    {
        "name": "فشارسنج بازویی دیجیتال",
        "category": 1600,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "ویتامین C 1000 میلی‌گرم",
        "category": 1636,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "پروتئین وی 2 کیلوگرمی",
        "category": 1631,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "ماساژور برقی دستی",
        "category": 1665,
        "variants": [{"Variant": "Default"}],
    },
    # Tools (1666)
    {
        "name": "دریل برقی 750 وات",
        "category": 1668,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "پیچ گوشتی و دریل شارژی 12 ولت",
        "category": 1669,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "نردبان آلومینیومی 6 پله",
        "category": 1683,
        "variants": [{"Variant": "Default"}],
    },
    # Books, stationery, art (1717)
    {
        "name": "دفتر یادداشت جلد سخت A5",
        "category": 1735,
        "variants": [{"Color": "مشکی"}, {"Color": "آبی"}, {"Color": "قرمز"}],
    },
    {
        "name": "خودکار روان نویس ست 6 عددی",
        "category": 1736,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "گیتار آکوستیک 41 اینچ",
        "category": 1744,
        "variants": [{"Variant": "Default"}],
    },
    # Sport and travel (1763)
    {
        "name": "توپ فوتبال سایز 5",
        "category": 1792,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "دمبل قابل تنظیم 20 کیلوگرمی",
        "category": 1786,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "قمقمه ورزشی استیل 1 لیتری",
        "category": 1776,
        "variants": [{"Color": "مشکی"}, {"Color": "آبی"}, {"Color": "نقره ای"}],
    },
    {
        "name": "چادر مسافرتی 4 نفره",
        "category": 1777,
        "variants": [{"Variant": "Default"}],
    },
    # Groceries (1801)
    {
        "name": "برنج ایرانی هاشمی 5 کیلوگرمی",
        "category": 1804,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "چای سیاه ممتاز 500 گرمی",
        "category": 1818,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "روغن زیتون فرابکر 1 لیتری",
        "category": 1813,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "عسل طبیعی 900 گرمی",
        "category": 1850,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "ماکارونی 700 گرمی",
        "category": 1803,
        "variants": [{"Variant": "Default"}],
    },
    # Kids (1911)
    {
        "name": "پازل چوبی 100 تکه",
        "category": 1928,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "عروسک پولیشی خرگوش",
        "category": 1929,
        "variants": [{"Color": "صورتی"}, {"Color": "سفید"}],
    },
    {
        "name": "کالسکه کودک تاشو",
        "category": 1948,
        "variants": [{"Color": "مشکی"}, {"Color": "آبی"}],
    },
    {
        "name": "شیشه شیر کودک 240 میلی‌لیتری",
        "category": 1959,
        "variants": [{"Variant": "Default"}],
    },
    # Local products (1960)
    {
        "name": "عسل طبیعی کوهستان 1 کیلوگرمی",
        "category": 1966,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "برنج محلی طارم 5 کیلوگرمی",
        "category": 1963,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "آجیل سنتی مخلوط 1 کیلوگرمی",
        "category": 1977,
        "variants": [{"Variant": "Default"}],
    },
    # Pet shop (2016)
    {
        "name": "غذای خشک گربه بالغ 2 کیلوگرمی",
        "category": 2016,
        "variants": [{"Variant": "Default"}],
    },
    {
        "name": "قلاده سگ قابل تنظیم",
        "category": 2016,
        "variants": [{"Color": "مشکی"}, {"Color": "قرمز"}],
    },
    {
        "name": "اسباب بازی موش پارچه‌ای گربه",
        "category": 2016,
        "variants": [{"Variant": "Default"}],
    },
]
