"""Reference rows for ``marketplace.PricingStrategy``.

Pure data: no model imports, so both the migration that creates the table and
the ``seed`` command can import it safely.

Adding a strategy means adding a ``VariantCostStrategyEnum`` member, a row
here, and a branch in ``InventoryPricingService._calculate_basis()`` — the
table only carries display data and never gains a write path of its own.

``description`` is a content-component document: the same
``{components: [{id, key, version, props}]}`` shape landing pages use, so the
front ends render the guide through their existing content registry. Only
``components`` is stored; per-instance ``version`` is checked against the
registry by the renderer, so a content-contract bump invalidates nothing here.
"""

from domains.inventory.enums.VariantCostStrategyEnum import VariantCostStrategyEnum

# Fixed ids: BusinessOffer.cost_strategy defaults to the "latest" row, which
# must be id 1 (mirrors inventory.InventoryType seeding).
LATEST_ID = 1

SHARED_FORMULA_NOTE = (
    "> قیمت پیشنهادی فقط محاسبه می‌شود؛ ذخیره یا انتشار خودکار ندارد "
    "و باید برای اعمالِ آن خودتان قیمت را ثبت کنید."
)

LANDED_COST_NOTE = (
    "> هزینهٔ واحدِ هر تامین، هزینهٔ نهایی (landed) همان تامین است: "
    "(قیمت خرید واحد × تعداد + هزینه‌های جانبی) ÷ تعداد."
)


def _components(component_id, intro, usage, formula, extra_note=None):
    """Build one guide document from three ``rich_text`` component instances."""
    parts = [formula]
    if extra_note is not None:
        parts.append(extra_note)
    parts.append(SHARED_FORMULA_NOTE)
    return {
        "components": [
            {
                "id": f"guide-{component_id}-intro",
                "key": "rich_text",
                "version": 1,
                "props": {"content": intro},
            },
            {
                "id": f"guide-{component_id}-usage",
                "key": "rich_text",
                "version": 1,
                "props": {"content": usage},
            },
            {
                "id": f"guide-{component_id}-formula",
                "key": "rich_text",
                "version": 1,
                "props": {"content": "\n\n".join(parts)},
            },
        ]
    }


PRICING_STRATEGY_SEED = [
    {
        "id": LATEST_ID,
        "code": VariantCostStrategyEnum.LATEST.value,
        "name": "Latest",
        "fa_name": "آخرین هزینه",
        "description": _components(
            "latest",
            "مبنای قیمت‌گذاری، هزینهٔ واحدِ **آخرین تامین رسیده**‌ی باقی‌ماندهٔ این "
            "محصول است؛ یعنی قیمت پیشنهادی از روی هزینهٔ نهایی همان یک رسید انبار "
            "ساخته می‌شود.",
            "**کجا استفاده شود:** زمانی که قیمت تامین ثابت است یا تغییراتش ناچیز "
            "است. اگر تامین‌های اخیر با اختلاف زیادی خریداری شده باشند، این "
            "استراتژی می‌تواند قیمت را ناگهان بالا یا پایین ببرد.",
            "**فرمول\n\n"
            "هزینهٔ واحد (landed) = (قیمت خرید واحد × تعداد رسید + هزینه‌های جانبی) "
            "÷ تعداد رسید\n\n"
            "قیمت پیشنهادی = مبنای هزینه × (۱ + درصد سود انتظاری ÷ ۱۰۰)",
        ),
    },
    {
        "id": LATEST_ID + 1,
        "code": VariantCostStrategyEnum.WEIGHTED_AVERAGE.value,
        "name": "Weighted average",
        "fa_name": "میانگین وزنی",
        "description": _components(
            "weighted-average",
            "مبنای قیمت‌گذاری، **میانگین وزنی هزینهٔ واحدِ همهٔ تامین‌های باقی‌مانده** "
            "است؛ هر تامین به نسبت تعدادِ باقی‌مانده‌اش در این میانگین وزن دارد.",
            "**کجا استفاده شود:** برای محصولاتی که از چند تامین با قیمت‌های متفاوت "
            "خریداری شده‌اند و می‌خواهید نوسان قیمت خرید، به‌جای جهش در یک لحظه، در "
            "قیمت فروش یکنواخت پخش شود. انتخاب متعادل برای بیشتر کالاها.",
            "**فرمول\n\n"
            "مبنای هزینه = Σ (باقی‌ماندهٔ هر تامین × هزینهٔ واحد آن) ÷ مجموع "
            "باقی‌مانده‌ها\n\n"
            "قیمت پیشنهادی = مبنای هزینه × (۱ + درصد سود انتظاری ÷ ۱۰۰)",
            LANDED_COST_NOTE,
        ),
    },
    {
        "id": LATEST_ID + 2,
        "code": VariantCostStrategyEnum.FIFO_NEXT.value,
        "name": "FIFO next",
        "fa_name": "FIFO بعدی",
        "description": _components(
            "fifo-next",
            "مبنای قیمت‌گذاری، هزینهٔ واحدِ **قدیمی‌ترین تامین باقی‌مانده** (اولین "
            "ورود در روش FIFO) است.",
            "**کجا استفاده شود:** وقتی می‌خواهید کالا به همان ترتیبی که خریداری شده "
            "از انبار خارج شود. این روش معمولاً کهنه‌ترین بهای خرید را در قیمت فروش "
            "نشان می‌دهد و برای کالاهای تاریخ‌دار یا با چرخش موجودی بالا کاربرد "
            "دارد.",
            "**فرمول\n\n"
            "مبنای هزینه = هزینهٔ واحدِ قدیمی‌ترین تامینِ باقی‌مانده\n\n"
            "قیمت پیشنهادی = مبنای هزینه × (۱ + درصد سود انتظاری ÷ ۱۰۰)",
            LANDED_COST_NOTE,
        ),
    },
]
