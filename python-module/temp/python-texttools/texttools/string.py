from fnmatch import fnmatch
from re import compile as re_compile, ASCII
from urllib.parse import unquote as url_unescape


SRE_Pattern = type(re_compile(''))
BLANK_CRE = re_compile(r'\s+')
UNICODE_CRE = re_compile(r'&#(?:(?P<u>[0-9]+)|x(?P<u8>[0-9A-Fa-f]+));', ASCII)
ASCII_CRE = re_compile(r'\\u([0-9A-Fa-f]+)', ASCII)


def _ncr_trans(group):
    kind = group.lastgroup
    if kind == 'u':
        return chr(int(group[kind]))
    return chr(int(group[kind], 16))

def unicode_unescape(string):
    # 功能相当于 html.unescape
    return UNICODE_CRE.sub(_ncr_trans, string)

# 把字符串str中的NCR转换为Native Unicode
def ascii_unescape(string):
    trans = lambda g: chr(int(g[1], 16))
    return ASCII_CRE.sub(trans, string)


def dbc_case(string):
    "全角转半角"
    def t(char):
        if char == '\u3000':
            return '\u0020'
        elif '\uff01' <= char <= '\uff5e':
            return chr(ord(char) - 65248)
        else:
            return char
    return ''.join(map(t, string))

def sbc_case(string):
    "半角转全角"
    def t(char):
        if char == '\u0020':
            return '\u3000'
        elif '\u0021' <= char <= '\u007e':
            return chr(ord(char) + 65248)
        else:
            return char
    return ''.join(map(t, string))

def long_substitute(string, olds, new='', count=0):
    "在字符串中一次替换多个子串"
    olds = '|'.join(map(re.escape, olds))
    return re.sub(olds, new, string, count)

def long_replace(string, olds, new='', count=-1):
    "在字符串中一次替换多个子串"
    if count < 0:
        count = 0
    elif count is 0:
        count = -1
    return long_substitute(string, olds, new, count)

def gen_translate(string, from_str, to_str=''):
    "参考Oracle的SQL函数translate"
    l = len(to_str)
    for s in string:
        p = from_str.find(s)
        if p is -1:
            yield s
        elif p < l:
            yield to_str[p]
        else:
            yield ''

def translate(string, from_str, to_str=''):
    "参考Oracle的SQL函数translate"
    return ''.join(gen_translate(string, from_str, to_str))

def lpad(string, padded_length, pad_string=' '):
    "参考Oracle的SQL函数lpad"
    return string.rjust(padded_length, pad_string)[:padded_length]

def rpad(string, padded_length, pad_string=' '):
    "参考Oracle的SQL函数rpad"
    return string.ljust(padded_length, pad_string)[:padded_length]

def substring_index(string, delimiter, count):
    if count == 0:
        return ''
    elif count > 0:
        end = -1
        for i in range(count):
            end = string.find(delimiter, end+1)
            if end == -1:
                return string
        else:
            return string[:end]
    else:
        start = None
        for i in range(-count):
            start = string.rfind(delimiter, 0, start)
            if start == -1:
                return string
        else:
            return string[start+1:]

def distinct_string(string, split_sep=RE_BLANK, join_sep=' ', reverse=False):
    if split_sep is '':
        splitted_list = tuple(string)
    else:
        if isinstance(split_sep, SRE_Pattern):
            splitted_list = split_sep.split(string)
        else:
            splitted_list = string.split(split_sep)
    return join_sep.join(sorted(set(splitted_list), key=splitted_list.index, 
                         reverse=reverse))


def if_match_unix_pattern(pattern, string):
    return fnmatch(string, pattern)

def if_match_re_fullmatch(pattern, string):
    return re.fullmatch(pattern, string) is not None

def if_match_re_search(pattern, string):
    return re.match(pattern, string) is not None

def if_match_re_search(pattern, string):
    return re.search(pattern, string) is not None

def pad_start(
    string: str, /, 
    width: int, 
    fillstr: str = ' '
) -> str:
    if len(string) >= width:
        return string
    whole_len, trunc_len = divmod(width - len(string), len(fillstr))
    return fillstr * whole_len + fillstr[:trunc_len] + string

def pad_end(
    string: str, /, 
    width: int, 
    fillstr: str = ' '
) -> str:
    if len(string) >= width:
        return string
    whole_len, trunc_len = divmod(width - len(string), len(fillstr))
    return string + fillstr * whole_len + fillstr[:trunc_len] 

