__all__ = ['BRACKET_PATTERN', 'wrap_pattern', 'translate', 'compile']

import re

from re import compile as re_compile, escape, Match, Pattern
from typing import Final, Union
from uuid import uuid4


__doc__ = '''
Bracket Wrapped Pattern 😂

---------- Usage ----------

[#{comment}#] # 注释 -> 会被直接忽略
[?{name}]     # 引用名称为{name}的捕获组

# NOTE: 下面所有的{name}可以为空，如此则不创建捕获组，否则创建命名捕获组
# NOTE: {desire}为空时，会尝试解读为懒惰（非贪婪匹配）

[{name}={string}]            # 匹配字符串，字符串会按原样匹配
[{name}'{string}']           # 匹配字符串，字符串会按原样匹配
[{name}"{string}"]           # 匹配字符串，字符串会按原样匹配
[{name}\'\'\'{string}\'\'\'] # 匹配字符串，字符串会按原样匹配
[{name}"""{string}"""]       # 匹配字符串，字符串会按原样匹配
[{name}`{string}`]           # 匹配字符串，字符串会被递归翻译（请参考 `translate`）
[{name}```{string}```]       # 匹配字符串，字符串会被递归翻译（请参考 `translate`）

# NOTE: 下面的每个变量都可以为空，但不能全部为空，若如此，则原样返回
# NOTE: 如果{pattern}是正则表达式，会忽略{desire}
[{name}{bound}{desire}{flags}{pattern}]

[{name}] # 占位匹配，会创建命名捕获组，默认用 .*?

# 下面按顺序分别讲解{bound}、{desire}、{flags}、{pattern}

## {bound}
[^^] # 会在对{pattern}翻译得到的正则表达式前加一个  \A
[$$] # 会在对{pattern}翻译得到的正则表达式后加一个  \Z
[^]  # 会在对{pattern}翻译得到的正则表达式前加一个  ^
[$]  # 会在对{pattern} 翻译得到的正则表达式后加一个 $


## {desire}

### lazy 懒惰
### 尝试用懒惰模式（如果{pattern}翻译前就是正则表达式，则忽略此配置）
[{name}] # 因为没有其他配置，此处 {name} 不可为空
[:0]
[:😪]
[:-_-]

### eager 积极
[:]
[:1]
[:🤑]
[:$_$]

## {flags}
[:aiLmsux-imsx]
[:s] # DOTALL
[:-s] # cancel DOTALL
[:i] # IGNORECASE
[:-i] # cancel IGNORECASE
[:m] # MULTILINE
[:-m] # cancel MULTILINE

### flags 可取的值参考 https://docs.python.org/3/library/re.html#regular-expression-syntax
> (?aiLmsux-imsx:...)
> 
> (Zero or more letters from the set 'a', 'i', 'L', 'm', 's', 'u', 'x', optionally 
> followed by '-' followed by one or more letters from the 'i', 'm', 's', 'x'.) 
> The letters set or remove the corresponding flags: re.A (ASCII-only matching), 
> re.I (ignore case), re.L (locale dependent), re.M (multi-line), re.S (dot matches all), 
> re.U (Unicode matching), and re.X (verbose), for the part of the expression. 
> (The flags are described in Module Contents.)
> 
> The letters 'a', 'L' and 'u' are mutually exclusive when used as inline flags, so they 
> can’t be combined or follow '-'. Instead, when one of them appears in an inline group, 
> it overrides the matching mode in the enclosing group. In Unicode patterns (?a:...) 
> switches to ASCII-only matching, and (?u:...) switches to Unicode matching (default). 
> In byte pattern (?L:...) switches to locale depending matching, and (?a:...) switches to 
> ASCII-only matching (default). This override is only in effect for the narrow inline group, 
> and the original matching mode is restored outside of the group.

## {pattern}
[<]             # 如果此占位符前面有字符{x}，翻译成 [^{x}]* ，否则翻译成 .*
[>]             # 如果此占位符后面有字符{x}，翻译成 [^{x}]* ，否则翻译成 .*
[[{chars}]      # 会被翻译成正则表达式 [{chars}]，其中{chars}是字符集
[[^{chars}]     # 会被翻译成正则表达式 [^{chars}]，其中{chars}是字符集
[|{wildcards}|] # 把通配符模式(unix shell pattern){wildcards}翻译成对应正则表达式
[*{wildcards}]  # 把通配符模式(unix shell pattern){wildcards}翻译成对应正则表达式
[/{regexp}/]    # {regexp}是正则表达式，因此不用翻译
[~{regexp}]     # {regexp}是正则表达式，因此不用翻译

---------- GRAMMAR ----------

expr: '[' 
    '#' comment '#'
    | '?' name 
    | name? string
    | name? bound? desire? flags? pattern?
']'

comment:
    comment_pattern

name:
    name_pattern

string:
    '=' string_pattern
    | "'" string_pattern "'"
    | '"' string_pattern '"'
    | "'''" string_pattern "'''"
    | '"""' string_pattern '"""'
    | '`' string_pattern '`'
    | '```' string_pattern '```'

bound:
    ':' ( '^^' | '$$' | '^' | '$' )

desire:
    eager | lazy 

eager: 
    ':' ( '1' | '🤑' | '$_$' | '' )

lazy:
    (':' ( '0' | '😪' | '-_-' )) | ''

flags:
    flags_pattern

pattern:
    noleft
    noright
    | outlist
    | inlist
    | wildcard
    | wildcard2
    | regexp
    | regexp2

noleft:
    '<'

noright:
    '>'

outlist:
    '[^' chars_pattern

inlist:
    '[' chars_pattern

wildcard:
    '|' wildcard_pattern '|'

wildcard2:
    '*' wildcard_pattern

regexp:
    '/' regexp_pattern '/'

regexp2:
    '~' regexp_pattern

# NOTE: The specific patterns of these productions below are related to 
#       the regular expressions they actually use (see `BARE_PATTERN`)
comment_pattern: STRING
name_pattern: STRING
string_pattern: STRING
flags_pattern: STRING
chars_pattern: STRING
wildcard_pattern: STRING
regexp_pattern: STRING
'''


BARE_PATTERN: Final[str] = ('(?:'
 r'\?(?P<refer>[^\d\W]\w*)|'
 r'#(?P<comment>(?s:.*?))(?<![^\\]\\)#|'
  '(?P<capture>'
   r'(?P<name>[^\d\W]\w*)?'
    '(?P<config>'
      '(?P<string>'
       r'=(?P<str>(?s:.+?)(?<![^\\]\\))|'
       r'(?P<str_wraper>\'\'\'|"""|```|\'|"|`)'
        '(?P<strn>(?s:.*?))'
     r'(?<![^\\]\\)(?P=str_wraper))|'
     r'(?P<bound>\^\^|\$\$|\^|\$|)'
    #r'(?P<quantifier>\+|\*|\{\d+(?:,\d+)?\}|\{,\d+\}|)'
      '(?:'
        '(?P<eager>:(?:1|🤑|$_$|))|'
        '(?P<lazy>:(?:0|😪|-_-)|)'
      ')'
      '(?::(?P<flags>[-a-zA-Z]+)|)'
      '(?P<pattern>'
        '(?P<noleft><)|'
        '(?P<noright>>)|'
       r'\[\^(?P<outlist>(?s:.+?))(?<![^\\]\\)|'
       r'\[(?P<inlist>(?s:.+?))(?<![^\\]\\)|'
       r'\|(?P<wildcard>(?s:.*?))(?<![^\\]\\)\||'
       r'/(?P<regexp>(?s:.*?))(?<![^\\]\\)/|'
       r'\*(?P<wildcard2>(?s:.+?))(?<![^\\]\\)|'
       r'~(?P<regexp2>(?s:.+?))(?<![^\\]\\)|'
      ')'
    ')'
  ')'
')')
BRACKET_PATTERN: Final[Pattern] = re_compile(r'\[%s\]' % BARE_PATTERN)


def wrap_pattern(prefix: str = '[', suffix: str = ']') -> str:
    return '%s%s%s' % (escape(prefix), BARE_PATTERN, escape(suffix))


# FORK FROM: https://github.com/python/cpython/blob/3.9/Lib/fnmatch.py#L80
# DOC: https://docs.python.org/3/library/fnmatch.html#fnmatch.translate
def _translate_wildcard_pattern(pat: str, lazy: bool = False) -> str:
    """Translate a shell PATTERN to a regular expression.

    There is no way to quote meta-characters.
    """

    STAR = object()
    uhex = uuid4().hex
    groupnum = 0
    res: list = []
    add = res.append
    i, n = 0, len(pat)
    while i < n:
        c = pat[i]
        i = i+1
        if c == '*':
            # compress consecutive `*` into one
            if (not res) or res[-1] is not STAR:
                add(STAR)
        elif c == '?':
            add('.')
        elif c == '[':
            j = i
            if j < n and pat[j] == '!':
                j = j+1
            if j < n and pat[j] == ']':
                j = j+1
            while j < n and pat[j] != ']':
                j = j+1
            if j >= n:
                add('\\[')
            else:
                stuff = pat[i:j]
                if '--' not in stuff:
                    stuff = stuff.replace('\\', r'\\')
                else:
                    chunks = []
                    k = i+2 if pat[i] == '!' else i+1
                    while True:
                        k = pat.find('-', k, j)
                        if k < 0:
                            break
                        chunks.append(pat[i:k])
                        i = k+1
                        k = k+3
                    chunks.append(pat[i:j])
                    # Escape backslashes and hyphens for set difference (--).
                    # Hyphens that create ranges shouldn't be escaped.
                    stuff = '-'.join(s.replace('\\', r'\\').replace('-', r'\-')
                                     for s in chunks)
                # Escape set operations (&&, ~~ and ||).
                stuff = re.sub(r'([&~|])', r'\\\1', stuff)
                i = j+1
                if stuff[0] == '!':
                    stuff = '^' + stuff[1:]
                elif stuff[0] in ('^', '['):
                    stuff = '\\' + stuff
                add(f'[{stuff}]')
        else:
            add(escape(c))
    assert i == n

    # Deal with STARs.
    inp = res
    res = []
    add = res.append
    i, n = 0, len(inp)
    # Fixed pieces at the start?
    while i < n and inp[i] is not STAR:
        add(inp[i])
        i += 1
    # Now deal with STAR fixed STAR fixed ...
    # For an interior `STAR fixed` pairing, we want to do a minimal
    # .*? match followed by `fixed`, with no possibility of backtracking.
    # We can't spell that directly, but can trick it into working by matching
    #    .*?fixed
    # in a lookahead assertion, save the matched part in a group, then
    # consume that group via a backreference. If the overall match fails,
    # the lookahead assertion won't try alternatives. So the translation is:
    #     (?=(?P<name>.*?fixed))(?P=name)
    # Group names are created as needed: g0, g1, g2, ...
    # The numbers are obtained from _nextgroupnum() to ensure they're unique
    # across calls and across threads. This is because people rely on the
    # undocumented ability to join multiple translate() results together via
    # "|" to build large regexps matching "one of many" shell patterns.
    expand = '.*?' if lazy else '.*'
    while i < n:
        assert inp[i] is STAR
        i += 1
        if i == n:
            add(expand)
            break
        assert inp[i] is not STAR
        fixed = []
        while i < n and inp[i] is not STAR:
            fixed.append(inp[i])
            i += 1
        fixed_ = "".join(fixed)
        if i == n:
            add(expand)
            add(fixed_)
        else:
            add(f"(?=(?P<_{uhex}{groupnum}>.*?{fixed_}))(?P=_{groupnum})")
            groupnum += 1
    assert i == n
    return "".join(res)


def _repl(
    m: Match, 
    translate_pattern: Union[str, Pattern] = BRACKET_PATTERN, 
) -> str:
    if m['refer'] is not None:
        return '(?P=%s)' % m['refer']
    elif m['comment'] is not None:
        return ''

    if not m['capture']:
        return escape(m.group())

    name = m['name']
    config = m['config']
    if config is None:
        return '(?P<%s>(?s:.*?))' % name
    if m['string'] is not None:
        if m['str'] is not None:
            pattern = escape(m['str'])
        elif m['str_wraper'] in ('`', '```'):
            pattern = translate(m['strn'], translate_pattern)
        else:
            pattern = escape(m['strn'])
        if name:
            return '(?P<%s>%s)' % (name, pattern)
        return pattern

    bound = m['bound']
    lbound = rbound = ''
    if bound:
        if bound == '^^':
            lbound = r'\A'
        elif bound == '$$':
            rbound = r'\Z'
        elif bound == '^':
            lbound = '^'
        elif bound == '$':
            rbound = '$'

    is_lazy = m['eager'] is None
    lazy = '?' if is_lazy else ''
    flags = m['flags']

    if not m['pattern']:
        pattern = '.*'
    elif m['noleft'] is not None:
        if m.start() == 0:
            pattern = '.*'
        else:
            pattern = '[^%s]*' % escape(m.string[m.start()-1])
    elif m['noright'] is not None:
        if m.end() == len(m.string):
            pattern = '.*'
        else:
            pattern = '[^%s]*' % escape(m.string[m.end()])
    elif m['outlist'] is not None:
        pattern = '[^%s]*' % m['outlist']
    elif m['inlist'] is not None:
        pattern = '[%s]*' % m['inlist']
    else:
        lazy = ''
        if m['wildcard'] is not None:
            pattern = _translate_wildcard_pattern(m['wildcard'], is_lazy)
        elif m['wildcard2'] is not None:
            pattern = _translate_wildcard_pattern(m['wildcard2'], is_lazy)
        elif m['regexp'] is not None:
            pattern = m['regexp']
        elif m['regexp2'] is not None:
            pattern = m['regexp2']

    if flags:
        pattern = f'(?{flags}:{lbound}{pattern}{lazy}{rbound})'
    else:
        pattern = f'{lbound}{pattern}{lazy}{rbound}'
    if name is not None:
        pattern = '(?P<%s>%s)' % (name, pattern)
    return pattern


def translate(
    pattern: str, 
    translate_pattern: Union[str, Pattern] = BRACKET_PATTERN, 
) -> str:
    'Translate a BRACKET PATTERN `pattern` to a regular expression.'
    parts = []
    push = parts.append
    l = 0
    for m in re.finditer(translate_pattern, pattern):
        push(escape(pattern[l:m.start()]))
        push(_repl(m, translate_pattern))
        l = m.end()
    if not parts:
        return escape(pattern)
    push(escape(pattern[l:]))
    return ''.join(parts)


def compile(
    pattern: str, 
    translate_pattern: Union[str, Pattern] = BRACKET_PATTERN, 
    flags: int = re.M | re.U, 
) -> Pattern:
    'Translate a BRACKET PATTERN `pattern` to a regular expression, and then compile it.'
    return re_compile(translate(pattern, translate_pattern), flags)


translate.__doc__ = (translate.__doc__ or '') + '\n\n<<[ Reference ]>>\n' + __doc__
compile.__doc__ = (compile.__doc__ or '') + '\n\n<<[ Reference ]>>\n' + __doc__

