import re
import unicodedata


PERSIAN_TO_LATIN = {
    '\u0622': 'a',
    '\u0627': 'a',
    '\u0628': 'b',
    '\u067e': 'p',
    '\u062a': 't',
    '\u062b': 's',
    '\u062c': 'j',
    '\u0686': 'ch',
    '\u062d': 'h',
    '\u062e': 'kh',
    '\u062f': 'd',
    '\u0630': 'z',
    '\u0631': 'r',
    '\u0632': 'z',
    '\u0698': 'zh',
    '\u0633': 's',
    '\u0634': 'sh',
    '\u0635': 's',
    '\u0636': 'z',
    '\u0637': 't',
    '\u0638': 'z',
    '\u0639': 'a',
    '\u063a': 'gh',
    '\u0641': 'f',
    '\u0642': 'gh',
    '\u06a9': 'k',
    '\u06af': 'g',
    '\u0644': 'l',
    '\u0645': 'm',
    '\u0646': 'n',
    '\u0648': 'v',
    '\u0647': 'h',
    '\u06cc': 'y',
    ' ': '-',
    '\u200c': '-',
}


def persian_to_latin(text: str) -> str:
    result = []
    for char in text:
        result.append(PERSIAN_TO_LATIN.get(char, char))
    latin = ''.join(result)
    latin = latin.replace('--', '-').strip('-')
    return latin


_PERSIAN_CHARS_RE = re.compile(
    r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]'
)

_INPUT_MAP = str.maketrans({
    '\u06f0': '0', '\u06f1': '1', '\u06f2': '2', '\u06f3': '3', '\u06f4': '4',
    '\u06f5': '5', '\u06f6': '6', '\u06f7': '7', '\u06f8': '8', '\u06f9': '9',
    '\u0660': '0', '\u0661': '1', '\u0662': '2', '\u0663': '3', '\u0664': '4',
    '\u0665': '5', '\u0666': '6', '\u0667': '7', '\u0668': '8', '\u0669': '9',
    '\u061f': '?', '\u060c': ',', '\u061b': ';',
    '\u200c': ' ',
    '\u2018': "'", '\u2019': "'",
    '\u00ab': '"', '\u00bb': '"',
    '\u2013': '-', '\u2014': '-',
})

_POST_FOLD = str.maketrans({
    '\u0259': 'e', '\u014b': 'n', '\u0127': 'h',
    '\u0294': '', '\u02c0': '', '\u02d0': '',
    '\u2018': "'", '\u2019': "'",
    '\u00ab': '"', '\u00bb': '"',
    '\u2013': '-', '\u2014': '-',
})

_g2p_converter = None


def _get_g2p_converter():
    global _g2p_converter
    if _g2p_converter is None:
        from PersianG2p import Persian_g2p_converter

        _g2p_converter = Persian_g2p_converter()
    return _g2p_converter


def to_english_letters(value: str) -> str:
    """Normalize text to plain ASCII English letters.

    English input is kept as-is. Persian input is converted with PersianG2p.
    Non-Persian segments (letters, digits, punctuation) are never sent through
    the converter, because it verbalizes numbers.
    """
    text = str(value).strip().translate(_INPUT_MAP)
    if _PERSIAN_CHARS_RE.search(text):
        parts = []
        buffer = []
        for char in text:
            if _PERSIAN_CHARS_RE.match(char):
                buffer.append(char)
            else:
                if buffer:
                    parts.append(('fa', ''.join(buffer)))
                    buffer = []
                parts.append(('raw', char))
        if buffer:
            parts.append(('fa', ''.join(buffer)))
        converted = []
        for kind, segment in parts:
            if kind == 'fa':
                try:
                    segment = _get_g2p_converter().transliterate(
                        segment, secret=True
                    )
                except Exception:
                    segment = persian_to_latin(segment)
            converted.append(segment)
        text = ''.join(converted)
    text = unicodedata.normalize('NFD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.translate(_POST_FOLD)
    return ' '.join(text.split())
