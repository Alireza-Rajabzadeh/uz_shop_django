import re
import unicodedata


_WHITESPACE = re.compile(r"\s+")
_CHARACTER_TRANSLATION = str.maketrans({
    "ي": "ی",
    "ى": "ی",
    "ك": "ک",
    "ة": "ه",
    "ۀ": "ه",
    "ؤ": "و",
    "إ": "ا",
    "أ": "ا",
    "ٱ": "ا",
    "ـ": "",
    "\u200c": " ",
    "\u200d": " ",
})


def normalize_search_text(value: str) -> str:
    translated = unicodedata.normalize("NFKC", value).translate(_CHARACTER_TRANSLATION)
    without_marks = "".join(
        character for character in translated
        if unicodedata.category(character) != "Mn"
    )
    return _WHITESPACE.sub(" ", without_marks).strip().casefold()
