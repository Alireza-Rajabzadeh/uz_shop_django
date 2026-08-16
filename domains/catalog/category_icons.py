def normalize_category_name(value):
    return " ".join(
        (value or "")
        .casefold()
        .replace("ي", "ی")
        .replace("ى", "ی")
        .replace("ك", "ک")
        .replace("\u200c", " ")
        .replace("_", " ")
        .replace("-", " ")
        .split()
    )


# Order matters: specific category families must be checked before broad ones.
CATEGORY_ICON_RULES = (
    ("baby", ("نوزاد", "سیسمونی", "شیرخوار", "baby")),
    ("paw-print", ("حیوانات", "حیوان خانگی", "پرنده", "آکواریوم", "سگ", "گربه", "pet")),
    ("first-aid", ("پزشکی", "سلامت", "دارو", "دندانپزشکی", "کمک درمانی", "ارتوپدی", "medical")),
    ("fork-knife", ("خوراکی", "غذا", "نوشیدنی", "آشامیدنی", "قهوه", "چای", "food")),
    ("plant", ("گل و گیاه", "باغبانی", "کشاورزی", "نهال", "plant", "garden")),
    ("soccer-ball", ("فوتبال", "توپ", "football", "soccer")),
    ("barbell", ("ورزش", "ورزشی", "بدنسازی", "کوهنوردی", "کمپینگ", "fitness", "sport")),
    ("game-controller", ("کنسول بازی", "دسته بازی", "بازی pc", "پلی استیشن", "xbox", "gaming")),
    ("puzzle-piece", ("اسباب بازی", "عروسک", "لگو", "پازل", "toy")),
    ("device-mobile", ("موبایل", "گوشی", "تبلت", "سیم کارت", "mobile", "tablet")),
    ("laptop", ("لپ تاپ", "لپتاپ", "مک بوک", "notebook", "laptop")),
    ("headphones", ("هدفون", "هندزفری", "اسپیکر", "میکروفون", "صوتی", "audio")),
    ("watch", ("ساعت", "مچ بند", "watch")),
    ("camera", ("دوربین", "لنز", "عکاسی", "فیلمبرداری", "camera")),
    ("television", ("تلویزیون", "ویدئو پروژکتور", "پروژکتور", "television", "projector")),
    ("desktop-tower", ("کامپیوتر", "رایانه", "مانیتور", "مادربرد", "پردازنده", "کارت گرافیک", "هارد", "پرینتر", "اسکنر", "مودم", "computer", "desktop", "mini pc", "all in one")),
    ("armchair", ("مبلمان", "مبل", "صندلی", "تخت خواب", "armchair", "furniture")),
    ("house", ("لوازم خانگی", "خانه و آشپزخانه", "دکوراسیون", "روشنایی", "home", "kitchen")),
    ("t-shirt", ("پوشاک", "لباس", "پیراهن", "شلوار", "کفش", "جوراب", "کیف", "clothing", "fashion")),
    ("car", ("خودرو", "اتومبیل", "موتورسیکلت", "لاستیک", "car", "automotive")),
    ("book-open", ("کتاب", "مجله", "لوازم تحریر", "نوشت افزار", "book", "stationery")),
    ("sparkle", ("آرایشی", "زیبایی", "عطر", "ادکلن", "مراقبت پوست", "مراقبت مو", "beauty", "cosmetic")),
    ("toolbox", ("ابزارآلات", "ابزار دستی", "ابزار برقی", "ابزار صنعتی", "دریل", "پیچ گوشتی", "آچار", "toolbox")),
    ("wrench", ("تعمیر", "یدکی", "wrench", "repair")),
    ("gift", ("هدیه", "کادو", "gift")),
    ("shopping-cart", ("سوپرمارکت", "خواربار", "grocery")),
    ("storefront", ("فروشگاه", "بازارچه", "store")),
)


def match_category_icon(name, fa_name=None):
    normalized = normalize_category_name(f"{name or ''} {fa_name or ''}")
    for icon, keywords in CATEGORY_ICON_RULES:
        if any(_contains_keyword(normalized, keyword) for keyword in keywords):
            return icon
    return None


def _contains_keyword(normalized_name, keyword):
    normalized_keyword = normalize_category_name(keyword)
    if " " not in normalized_keyword:
        return normalized_keyword in normalized_name.split()
    return normalized_keyword in normalized_name
