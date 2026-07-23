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
