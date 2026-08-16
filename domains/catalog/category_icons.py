import json
from pathlib import Path

_CATALOG_PATH = (
    Path(__file__).resolve().parents[2]
    / "core"
    / "management"
    / "data"
    / "phosphor_icons.json"
)


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
    ("diamond", ("طلا و نقره", "جواهر", "زیورآلات", "jewelry")),
    ("cpu", ("کالای دیجیتال",)),
    ("package", ("محصولات بومی و محلی",)),
    ("baby", ("نوزاد", "سیسمونی", "شیرخوار", "baby")),
    ("paw-print", ("حیوانات", "حیوان خانگی", "پرنده", "آکواریوم", "سگ", "گربه", "پت", "pet")),
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
    ("shopping-cart", ("سوپرمارکت", "سوپر مارکت", "مارکت", "خواربار", "grocery")),
    ("storefront", ("فروشگاه", "بازارچه", "store")),
)

# English slug tokens that carry little meaning for icon search.
_SLUG_STOP_WORDS = frozenset(
    {
        "accesories", "accessories", "all", "automatic", "baby", "car", "category",
        "child", "children", "china", "content", "decorative", "devices", "digital",
        "economic", "electric", "electronic", "equipment", "female", "first", "hand",
        "home", "hygiene", "industrial", "installment", "international", "kitchen",
        "kids", "liquid", "local", "male", "man", "men", "men's", "mens", "online",
        "organic", "original", "parsian", "persian", "personal", "product", "products",
        "rural", "sanitary", "semi", "set", "sets", "shop", "silver", "solid", "supplies",
        "tools", "traditional", "uni", "woman", "women", "women's", "womens", "gold",
    }
)


def _load_catalog():
    with _CATALOG_PATH.open(encoding="utf-8") as catalog_file:
        return json.load(catalog_file)["icons"]


_ICON_CATALOG = _load_catalog()


def match_category_icon(name, fa_name=None, slug=None):
    normalized = normalize_category_name(f"{name or ''} {fa_name or ''}")
    for icon, keywords in CATEGORY_ICON_RULES:
        if any(_contains_keyword(normalized, keyword) for keyword in keywords):
            return icon
    if slug:
        return _search_catalog(slug)
    return None


def _contains_keyword(normalized_name, keyword):
    normalized_keyword = normalize_category_name(keyword)
    if " " not in normalized_keyword:
        return normalized_keyword in normalized_name.split()
    return normalized_keyword in normalized_name


def _search_catalog(slug):
    tokens = [
        token
        for token in _slug_tokens(slug)
        if token not in _SLUG_STOP_WORDS and len(token) >= 3
    ]
    if not tokens:
        return None

    token_set = set(tokens)
    for icon in _ICON_CATALOG:
        words = icon["key"].split("-")
        if len(words) == len(tokens) and set(words) == token_set:
            return icon["key"]

    for token in tokens:
        for icon in _ICON_CATALOG:
            words = icon["key"].split("-")
            if len(words) == 1 and words[0] == token:
                return icon["key"]

    return None


def _slug_tokens(slug):
    segment = slug.rstrip("/").split("/")[-1]
    for prefix in ("category-", "landing-", "main-"):
        if segment.startswith(prefix):
            segment = segment[len(prefix):]
            break
    return [token for token in segment.split("-") if token]