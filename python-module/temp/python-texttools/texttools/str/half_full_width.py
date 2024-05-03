def chr_half2full(char: str) -> str:
    "单字符：半角转全角"
    code = ord(char)
    if code == 32:
        return chr(12288)
    elif 32 < code <= 126:
        return chr(code + 65248)
    else:
        return char


def ctr_half2full(string: str) -> str:
    "字符串: 半角转全角"
    return ''.join(map(chr_half2full, string))
