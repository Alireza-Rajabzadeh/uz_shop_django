"""Reference rows for ``business_content.SuggestionPage``.

Pure data: no model imports, so both the migration that seeds the table and
any future management command can import it safely.

``title`` and ``descriptions`` are stored in Persian and rendered straight by
the panels — this is content the vendor reads, not a gettext msgid (the
msgid/msgstr split in ``locale/`` is for API messages). The panels are fixed
to Persian at runtime, so there is no second translation to keep in sync yet.

Adding a suggestion means adding a row here; ``slug`` is the identity, so
re-running the seed updates copy, ``required``, and ``context`` in place
rather than duplicating. ``activate`` is deliberately absent: an operator's
activation choice must survive a re-seed.
"""

SUGGESTION_PAGES = [
    {
        "slug": "home",
        "title": "خانه",
        "descriptions": "صفحه اصلی ورود مشتریان به فروشگاه شما.",
        "required": True,
        "context": "page",
    },
    {
        "slug": "about",
        "title": "درباره ما",
        "descriptions": "به مشتریان معرفی کنید که شما کیستید و چه می‌فروشید.",
        "required": True,
        "context": "page",
    },
    {
        "slug": "contact",
        "title": "تماس با ما",
        "descriptions": "شماره تماس، آدرس و راه‌های ارتباطی فروشگاه.",
        "required": True,
        "context": "page",
    },
    {
        "slug": "faq",
        "title": "پرسش‌های متداول",
        "descriptions": "پاسخ پرسش‌هایی که مشتریان بیش از همه می‌پرسند.",
        "required": False,
        "context": "page",
    },
    {
        "slug": "terms",
        "title": "شرایط و قوانین",
        "descriptions": "قواعد خرید از فروشگاه شما.",
        "required": False,
        "context": "page",
    },
    {
        "slug": "privacy",
        "title": "حریم خصوصی",
        "descriptions": "نحوه جمع‌آوری و استفاده از داده‌های مشتریان.",
        "required": False,
        "context": "page",
    },
    {
        "slug": "shipping",
        "title": "ارسال و تحویل",
        "descriptions": "زمان، هزینه و پوشش ارسال مرسوله‌ها.",
        "required": False,
        "context": "page",
    },
    {
        "slug": "returns",
        "title": "مرجوعی و بازپرداخت",
        "descriptions": "مدت زمان مرجوعی و فرآیند بازپرداخت وجه.",
        "required": False,
        "context": "page",
    },
]
