__all__ = ['make_repl', 'replace']

from re import Match, Pattern
from string import Template
from typing import Callable, Mapping, Union

from .bracket_pattern import compile
from .bracket_template import BracketTemplate
from .make_repl import make_repl_using_template


def make_repl(
    template: Union[str, Template], 
    extra: Mapping = {}, 
    safe: bool = False,
):
    '''`template`中至少可以引用这些名字
_i
    代表这是第几个匹配，从 1 开始计数
_0
    代表当前所匹配到的字符串整体
_1, _2, ..., _n
    代表当前匹配中的索引是 n 的捕获组，从 1 开始计数
name
    代表当前匹配中的名称是 name 的捕获组
    '''
    if isinstance(template, str):
        template = BracketTemplate(template)
    return make_repl_using_template(template, extra, safe)


def replace(
    pattern: Union[str, Pattern], 
    repl: Union[str, Template, Callable[[Match], str]], 
    string: str, 
    count: int = 0, 
) -> str:
    if isinstance(pattern, str):
        pattern = compile(pattern)
    if not callable(repl):
        repl = make_repl(repl)
    return pattern.sub(repl, string, count)

