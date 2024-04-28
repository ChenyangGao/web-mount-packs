#!/usr/bin/env python3
# coding: utf-8

__author__ = 'ChenyangGao <https://chenyanggao.github.io/>'
__version__ = (0, 0, 4)
__all__ = [
    'BRACKET_PATTERN', 'bracket_pattern', 'translate', 'compile', 
    'replace', 'replace_template', 'get_dict_of_match', 
]
__doc__ = '''
Q & A: Abount BRACKET PATTERN

Usage::

    [name]
        懒惰模糊匹配，translate into (?P<name>.*?)
    [:]
        贪婪模糊匹配，translate into .*
    [+]
        懒惰模糊匹配，translate into .+?
    [+:]
        贪婪模糊匹配，translate into .+
    [name:]
        贪婪模糊匹配，translate into (?P<name>.*)
    [name+:]
        贪婪模糊匹配，translate into (?P<name>.+)
    [:s]
        启用单行模式 DOTALL (. 会匹配 \\r 和 \\n)
        各种模式详见下面文档中的 (?aiLmsux) (?aiLmsux-imsx:...)
        https://docs.python.org/3/library/re.html#regular-expression-syntax
    [:-s]
        禁用单行模式 DOTALL
    [:m]
        启用多行模式 MULTILINE (^ 和 $ 会检查 \\r 和 \\n)
    [:-m]
        禁用多行模式 MULTILINE
    [name:s]
        懒惰模糊匹配，单行模式，翻译成 (?P<name>(?s:.*?))
    [name::s]
        贪婪模糊匹配，单行模式，翻译成 (?P<name>(?s:.*))
    [<]
        匹配任意个不等于占位符之前的第1个字符，如果占位符在开头，则用 . 
    [>]
        匹配任意个不等于占位符之后的第1个字符，如果占位符在结尾，则用 .
    [=string]
        按原样匹配 string，正则表达式元字符会被自动转义
    [`string`]
        按原样匹配 string，当成嵌入的模式，递归地翻译
    [[^chars]
        匹配任意个不在字符集 chars 中的字符
    [[chars]
        匹配任意个在字符集 chars 中的字符
    [/pattern/]
        匹配正则表达式 pattern
    [~pattern]
        匹配正则表达式 pattern
    [name::sm[chars]
        贪婪匹配，启用 s 和 m 模式，任意个在字符集 chars 中的字符，
        创建命名捕获组 name (如果省略 name，则不创建捕获组)

Grammar::

    bracket_pattern: # If all parts are empty, then escape it
        [ name? nonempty? desire? flags? pattern? ]
    name:
        STRING
    nonempty:
        '+' | ''
    desire:
        ':' | ''
    flags:
        ':' CHAR+ # see https://docs.python.org/3/library/re.html#regular-expression-syntax
                  # (?aiLmsux-imsx:...) letters from the set 'a', 'i', 'L', 'm', 
                  # 's', 'u', 'x', optionally followed by '-' followed by one or 
                  # more letters from the 'i', 'm', 's', 'x'.
    pattern:
        '=' STRING       # STRING as such a string
        | '`' STRING '`' # STRING as embedded string may
                         #     contain bracket_pattern
        | '[^' STRING    # STRING as distinct characters
        | '[' STRING     # STRING as distinct characters
        | '/' STRING '/' # STRING as regular expression
        | '~' STRING     # STRING as regular expression
'''

import re

from collections import ChainMap
from operator import itemgetter, methodcaller
from re import compile as re_compile, escape, sub, Match, Pattern
from typing import Any, Callable, Final, Mapping, Optional, Union


BARE_PATTERN: Final[str] = ('(?:'
 r'(?P<name>[^\d\W]\w*)?'
  '(?P<nonempty>\+)?'
  '(?P<desire>:)?'
  '(?::(?P<flags>[-a-zA-Z]+))?'
  '(?P<pattern>'
    '(?P<noleft><)|'
    '(?P<noright>>)|'
   r'=(?P<str>(?s:.+?)(?<![^\\]\\))|'
   r'`(?P<strx>(?s:.*?)(?<![^\\]\\))`|'
   r'\[\^(?P<outlist>(?s:.+?))(?<![^\\]\\)|'
   r'\[(?P<inlist>(?s:.+?))(?<![^\\]\\)|'
   r'/(?P<regexp>(?s:.*?))(?<![^\\]\\)/|'
   r'~(?P<regexp2>(?s:.+?))(?<![^\\]\\)|'
  ')'
')')
BRACKET_PATTERN: Final[Pattern] = re_compile(r'\[%s\]' % BARE_PATTERN)
ID_DOLLAR_PATTERN: Final[Pattern] = re_compile(
    # Roughly equivalent to r'\$(?:([^\d\W]\w*)|\{((?s:.+?))(?<![^\\]\\)\})'
    r'\$(?P<braced>\{)?(?P<named>(?(braced)(?s:.+?)|[^\d\W]\w*))'
    r'(?(braced)(?<![^\\]\\)\})')
ID_BRACKET_PATTERN: Final[Pattern] = re_compile(r'\[(?P<named>\w+)\]')
NAME_BRACKET_PATTERN: Final[Pattern] = re_compile(r'\[(?P<named>[^\d\W]\w*)\]')
ENCLOSED_BRACKET_PATTERN: Final[Pattern] = re_compile(
    r'\[(?P<named>(?s:.+?)(?<![^\\]\\))\]')


def bracket_pattern(prefix: str = '[', suffix: str = ']') -> str:
    return '%s%s%s' % (escape(prefix), BARE_PATTERN, escape(suffix))

bracket_pattern.__doc__ = '''\
Create a regular expression, also known as BRACKET PATTERN, 
that is enclosing `BARE_PATTERN` with `prefix` and `suffix`. 
`BARE_PATTERN` is 
''' + BARE_PATTERN


def _repl(
    m: Match, /, 
    rule_pattern: Union[str, Pattern] = BRACKET_PATTERN, 
) -> str:
    '''
    :param m:
    :param rule_pattern:

    :return:
    '''
    name = m['name']
    quantifier = '+' if m['nonempty'] else '*'
    lazy = '?' if not m['desire'] else ''
    flags = m['flags']

    if not m['pattern']:
        if not any(m.groups()):
            return escape(m.group())
        pattern = '.' + quantifier
    elif m['noleft'] is not None:
        if m.start() == 0:
            pattern = '.' + quantifier
        else:
            pattern = '[^%s]%s' % (escape(m.string[m.start()-1]), quantifier)
    elif m['noright'] is not None:
        if m.end() == len(m.string):
            pattern = '.' + quantifier
        else:
            pattern = '[^%s]%s' % (escape(m.string[m.end()]), quantifier)
    elif m['str'] is not None:
      flags = lazy = ''
      pattern = escape(m['str'])
    elif m['strx'] is not None:
      flags = lazy = ''
      pattern = translate(m['strx'], rule_pattern)
    elif m['outlist'] is not None:
        pattern = '[^%s]%s' % (m['outlist'], quantifier)
    elif m['inlist'] is not None:
        pattern = '[%s]%s' % (m['inlist'], quantifier)
    elif m['regexp'] is not None:
      lazy = ''
      pattern = m['regexp']
    elif m['regexp2'] is not None:
      lazy = ''
      pattern = m['regexp2']

    if flags:
        pattern = f'(?{flags}:{pattern}{lazy})'
    elif lazy:
        pattern = f'{pattern}{lazy}'

    if name is not None:
        pattern = '(?P<%s>%s)' % (name, pattern)
    return pattern


def translate(
    pattern: str, 
    rule_pattern: Union[str, Pattern] = BRACKET_PATTERN, 
) -> str:
    '''Translate a BRACKET PATTERN `pattern` into a regular expression.

    :param pattern: 
        A string you want to translate. Search it with `rule_pattern`, 
        all matches will be automatically translated into a specific 
        regular expression, and the mismatches will be escaped.
    :param rule_pattern: 
        A regular expression, that is enclosing `BARE_PATTERN` with 
        a certain `prefix` and `suffix`. You can use `bracket_pattern` 
        function in this module to get such a regular expression.

    :return: Regular expression from translation.
    '''
    parts: list[str] = []
    push = parts.append
    l = 0
    for m in re.finditer(rule_pattern, pattern):
        push(escape(pattern[l:m.start()]))
        push(_repl(m, rule_pattern))
        l = m.end()
    if not parts:
        return escape(pattern)
    push(escape(pattern[l:]))
    return ''.join(parts)


def compile(
    pattern: str, 
    rule_pattern: Union[str, Pattern] = BRACKET_PATTERN, 
    flags: int = re.M | re.U, 
) -> Pattern:
    '''Translate a BRACKET PATTERN `pattern` into a regular expression, 
    and then compile it.

    :param pattern: 
        A string you want to translate. Search it with `rule_pattern`, 
        all matches will be automatically translated into a specific 
        regular expression, and the mismatches will be escaped.
    :param rule_pattern: 
        A regular expression, that is enclosing `BARE_PATTERN` with 
        a certain `prefix` and `suffix`. You can use `bracket_pattern` 
        function in this module to get such a regular expression.
    :param flags:
        The regex matching flags. This is a combination of the flags given 
        to re.compile(), any (?...) inline flags in the pattern, and implicit 
        flags such as UNICODE if the pattern is a Unicode string.
        See: https://docs.python.org/3/library/re.html#re.Pattern.flags

    :return: Translate `pattern` into a regular expression, then compile it, 
             and return a `re.Pattern` object.
    '''
    return re_compile(translate(pattern, rule_pattern), flags)


def replace(
    string: str, 
    map: Union[Mapping, Callable] = lambda _: '', 
    key: Union[Callable[[Match], Any], int, str] = lambda m: \
        int(g) if (g := m[m.lastindex or 0]).isdecimal() else g, 
    pattern: Union[str, Pattern] = ID_DOLLAR_PATTERN, 
    count: int = 0, 
    flags: int = 0, 
) -> str:
    '''Searching for `string` using `pattern`, will get a collection of 
    match objects. First use `key`, and then use `map`, on each match 
    object, to get a replacement string, and replace the original string 
    of relevant match object with it respectively.

    :param string: The original string to be replaced.
    :param map: Take the value from `key`, hereinafter referred to as key, 
        and return the replacement string.
        `map` is `Mapping`: 
            `map[key]` (if the result is `None`, gets the matched original string) 
            as the replacement string.
        `map` is callable: 
            `map(key)` (if the result is `None`, gets the matched original string) 
            as the replacement string.  
    :param key: Get a value from a single `re.Match` object, 
        that value will be passed to `map` later.
        `key` is `int`: Returns the subgroup of the match object, 
            which references the index `key`.
        `key` is `str`: Returns the subgroup (named group) of the match object,  
            which references the name `key`.
        `key` is callable: Takes a single `re.Match` object argument, 
            returns a value that is acceptable to `map`.
    :param pattern: (That argument will be directly given to re.sub())
        The `pattern` may be a string or a `re.Pattern` object.
    :param count: (That argument will be directly given to re.sub())
        The maximum number of pattern occurrences to be replaced. `count` must be 
        a non-negative integer. If omitted or zero, all occurrences will be replaced. 
        Empty matches for the pattern are replaced only when not adjacent to a previous 
        empty match, so sub('x*', '-', 'abxd') returns '-a-b--d-'. 
        See: https://docs.python.org/3/library/re.html#re.sub
    :param flags: (That argument will be directly given to re.sub())
        The regex matching flags. This is a combination of the flags given 
        to re.compile(), any (?...) inline flags in the pattern, and implicit 
        flags such as UNICODE if the pattern is a Unicode string.
        See: https://docs.python.org/3/library/re.html#re.Pattern.flags

    :return: Return a copy with all occurrences of substring old replaced by new.
    '''
    if callable(map):
        meth = getattr(map, '__call__')
    else:
        meth = getattr(map, '__getitem__')
    if not callable(key):
        key = itemgetter(key)
    repl = lambda m: m.group() if (r := meth(key(m))) is None else str(r)
    return sub(pattern, repl, string, count=count, flags=flags)


def replace_template(
    pattern: Union[str, Pattern], 
    template: str, 
    string: str, 
    get_map_of_match: Callable[[Match], Mapping] = methodcaller('groupdict'), 
    template_key: Union[Callable[[Match], Any], int, str] = lambda m: \
        int(g) if (g := m[m.lastindex or 0]).isdecimal() else g, 
    template_id_pattern: Union[str, Pattern] = ID_DOLLAR_PATTERN, 
    count: int = 0, 
    flags: int = 0, 
):
    '''Use `pattern` to search `string`, will get a collection of match 
    objects. For each match object, render the `template` with its data 
    (gets data from a match object by the `get_map_of_match` function), 
    the rendered result is used as a replacement string, to replace the 
    original string of the match object.

    :param pattern:
        The `pattern` that contains some capture groups, may be a string 
        (as a BRACKET PATTERN to be compiled) or a `re.Pattern` object. 
        When there is a match, it uses the `get_map_of_match` function 
        to collect data from capture groups of the match object.
    :param template: Template to render with data from a match object 
        (using the `get_map_of_match` function as the data getter).
    :param string: The original string to be replaced.
    :param get_map_of_match: 
        Get data from a `re.Match` object and return it as a `Mapping` object. 
    :param template_key: Get a value from a `re.Match` object (that match 
        object as a placeholder, see `template_id_pattern`). 
        `template_key` is `int`: Returns the subgroup of the match object, 
            which references the index `key`.
        `template_key` is `str`: Returns the subgroup (named group) of the match object,  
            which references the name `key`.
        `template_key` is callable: Takes a single `re.Match` object argument, 
            returns a value that is acceptable to `map`.
    :param template_id_pattern: Use `template_id_pattern` to search for 
        placeholders from `template`. A placeholder contains a name as a key 
        (gets with `template_key`) that identify when they are rendered.
    :param count: (That argument will be directly given to re.sub())
        The maximum number of pattern occurrences to be replaced. `count` must be 
        a non-negative integer. If omitted or zero, all occurrences will be replaced. 
        Empty matches for the pattern are replaced only when not adjacent to a previous 
        empty match, so sub('x*', '-', 'abxd') returns '-a-b--d-'. 
        See: https://docs.python.org/3/library/re.html#re.sub
    :param flags: (That argument will be directly given to re.sub())
        The regex matching flags. This is a combination of the flags given 
        to re.compile(), any (?...) inline flags in the pattern, and implicit 
        flags such as UNICODE if the pattern is a Unicode string.
        See: https://docs.python.org/3/library/re.html#re.Pattern.flags

    :return: Return the string obtained by replacing the leftmost non-overlapping 
        occurrences of `pattern` in `string` by the replacement rendered `template`.
    '''
    if isinstance(pattern, str):
        pattern = compile(pattern)
    return replace(
        string, 
        map=lambda m: replace(
            template, 
            map=m, 
            key=template_key, 
            pattern=template_id_pattern, 
        ), 
        key=get_map_of_match, 
        pattern=pattern, 
        count=count, 
        flags=flags, 
    )


def get_dict_of_match(
    match: Match, 
    idx_prefix: Optional[str] = None, 
    extra: Optional[Mapping] = None, 
) -> Mapping:
    '''Get data from a `re.Match` object and return it as a `Mapping` object. 

    :param match: A `re.Match` object.
    :param idx_prefix: If it is not None, add additional data into 
        returned mapping. 
        These additional data are provided by the following dictionary:
            {
                f'{idx_prefix}0': match[0], 
                **{f'{idx_prefix}{i}': v for i, v in enumerate(match.groups(),1)}
            }
    :param extra: A `Mapping` object as additional data in returned mapping.

    :return: 
        If `idx_prefix` and `extra` are None, returns `match.groupdict()`.
        If `idx_prefix` is not None, see `:param idx_prefix:` 
            for which additional data are added.
        If extra is not None, it will be added as additional data.
    '''
    g: dict = match.groupdict()
    g[0] = match[0]
    g.update(enumerate(match.groups(), 1))
    if idx_prefix is not None:
        d = {f'{idx_prefix}0': match[0]}
        d.update((f'{idx_prefix}{i}', v) for i, v in enumerate(match.groups(), 1))
        cm = ChainMap(g, d)
        if extra is not None:
            cm.maps.append(extra)
        return cm
    if extra is not None:
        return ChainMap(g, extra)
    return g


if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser(description='BRACKET PATTERN translator and template replacer')
    subparsers = parser.add_subparsers()
    parser_translate = subparsers.add_parser(
        'translate', aliases=['t'], 
        help='Translate a BRACKET PATTERN into regular expression.')
    parser_translate.add_argument(
        'pattern', nargs=1, help='A valid BRACKET PATTERN to be translated')
    parser_translate.set_defaults(func=lambda args: translate(args.pattern[0]))
    parser_replace = subparsers.add_parser(
        'replace', aliases=['r'], 
        help='Search for the BRACKET PATTERN `pattern` in `string`, '
             'to get a collection of matches, replace the placeholders '
             'in the `template` with the capture group data in each '
             'match to get the replacement string')
    parser_replace.add_argument(
        '--pattern', '-p', required=True, help='A valid BRACKET PATTERN')
    parser_replace.add_argument(
        '--template', '-t', required=True, 
        help='A template, uses placeholders like $name and ${name}')
    parser_replace.add_argument(
        '--string', '-s', required=True, help='Original string to be replaced')
    parser_replace.set_defaults(func=lambda args: replace_template(
        pattern=args.pattern, template=args.template, string=args.string))
    args = parser.parse_args()
    if not args.__dict__:
        parser.parse_args(['-h'])
    print(args.func(args))

