#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["parse", "render"]

from collections.abc import Mapping, MutableMapping
from re import compile as re_compile


token_specification = [
    ("left_brace", r"\{\{"), 
    ("right_brace", r"\}\}"), 
    ("less_than", r"\\<"), 
    ("greater_than", r"\\>"), 
    ("left_block_with_name", r"<(?P<lbq>\?)?\{\{(?!\d)(?P<lbn>\w+)\}\}"), 
    ("left_block", r"<"), 
    ("right_block", r">"), 
    ("fstring_placeholder", r"\{[^{}]*\}"), 
    ("any", "(?s:.)")
]
tokenize = re_compile("|".join(f"(?P<{group}>{token})" for group, token in token_specification)).finditer


class Block(list):

    def __init__(
        self, 
        /, 
        name: None | str = None, 
        hidden: bool = False, 
    ):
        self.name = name
        self.hidden = hidden

    def render(self, ns: MutableMapping, /) -> str:
        try:
            s = "".join(part.render(ns) for part in self)
        except (AttributeError, KeyError, NameError, TypeError):
            s = ""
        if self.name:
            ns[self.name] = s
        if self.hidden:
            return ""
        return s


class String(str):

    def __str__(self, /) -> str:
        return super().__str__()

    def render(self, ns: MutableMapping, /) -> str:
        return str(self)


class FString(str):

    def __init__(self, s, /):
        self.code = compile("f%r" % str(s), "", "eval")

    def __str__(self, /) -> str:
        return super().__str__()

    def __repr__(self, /) -> str:
        return "f%r" % str(self)

    def render(self, ns: MutableMapping, /) -> str:
        return eval(self.code, ns)


def parse(pattern: str) -> Block:
    """模式解析

    语法简介：
        - 用 "<" 和 ">" 包围的字符串称为块，块可以嵌套，形如 "<...>"
        - 整个 pattern 字符串也是一个块
        - 块内的字符串会被当作 Python 的 fstring 进行插值填充，如果填充失败，则这个块返回空字符串 ""
        - 块可以有名字（类似正则表达式的捕获组），放在 "{{" 和 "}}" 之内，语法为 "<{{name}}...>"，之后这个块的值可以被 "{name}" 反复引用
        - 有名字的块可以只取名不输出，便于后续引用，语法为 "<?{{name}}...>"
        - 如果想使用 < 和 >，但不作为块的提示符号，则写成 "\\<" 和 "\\>"

    关于 Python 的 fstring 的介绍：
        - https://docs.python.org/3/reference/lexical_analysis.html#formatted-string-literals
        - https://peps.python.org/pep-0498/
        - https://peps.python.org/pep-0701/

    使用例子：

    1. MoviePilot 刮削时可以把文件进行移动和重命名，使用 jinja2 的语法，如果使用本模块，则可以少写约 2/3 的字

    jinja2 的写法

        {{title}}{% if year %} ({{year}}){% endif %}{% if tmdbid %} [tmdbid={{tmdbid}}]{% endif %}/Season {{season}}/{{title}} - {{season_episode}}{% if part %}-{{part}}{% endif %}{% if episode %} - 第{{episode}}集{% endif %}{% if videoFormat %} - {{videoFormat}}{% endif %}{% if edition %}.{{edition}}{% endif %}{% if videoCodec %}.{{videoCodec}}{% endif %}{% if audioCodec %}.{{audioCodec}}{% endif %}{% if releaseGroup %}-{{releaseGroup}}{% endif %}{{fileExt}}

    本模块的写法

        {title}< ({year})>< [tmdbid={tmdbid}]>/Season {season}/{title} - {season_episode}<-{part}>< - 第{episode}集>< - {videoFormat}><.{edition}><.{videoCodec}><.{audioCodec}><-{releaseGroup}>{fileExt}


    jinja2 的写法

        {{title}}{% if year %} ({{year}}){% endif %}{% if tmdbid %} [tmdbid={{tmdbid}}]{% endif %}/{{title}}{% if year %} ({{year}}){% endif %}{% if part %}-{{part}}{% endif %}{% if videoFormat %} - {{videoFormat}}{% endif %}{% if edition %}.{{edition}}{% endif %}{% if videoCodec %}.{{videoCodec}}{% endif %}{% if audioCodec %}.{{audioCodec}}{% endif %}{% if releaseGroup %}-{{releaseGroup}}{% endif %}{{fileExt}}

    本模块的写法

        <{{prefix}}{title}< ({year})>>< [tmdbid={tmdbid}]>/{prefix}<-{part}>< - {videoFormat}><.{edition}><.{videoCodec}><.{audioCodec}><-{releaseGroup}>{fileExt}
    """
    block = Block()
    stack = [block]
    depth = 0
    chars = []
    chars_with_fstring = False
    for match in tokenize(pattern):
        match group := match.lastgroup:
            case "left_block" | "left_block_with_name":
                if chars:
                    block.append((FString if chars_with_fstring else String)("".join(chars)))
                    chars.clear()
                    chars_with_fstring = False
                block = Block(match["lbn"], bool(match["lbq"]))
                stack[depth].append(block)
                depth += 1
                try:
                    stack[depth] = block
                except IndexError:
                    stack.append(block)
            case "right_block":
                if chars:
                    block.append((FString if chars_with_fstring else String)("".join(chars)))
                    chars.clear()
                    chars_with_fstring = False
                depth -= 1
                if depth < 0:
                    raise SyntaxError(f"Mismatched pairs of '<' and '>', at {match.start()}.")
                block = stack[depth]
            case "less_than":
                chars.append("<")
            case "greater_than":
                chars.append(">")
            case "left_brace" | "right_brace" | "fstring_placeholder":
                chars_with_fstring = True
                chars.append(match[group])
            case "any":
                chars.append(match[group])
    else:
        if depth > 0:
            raise SyntaxError("Mismatched pairs of '<' and '>'.")
        if chars:
            block.append((FString if chars_with_fstring else String)("".join(chars)))
    return stack[0]


def render(block: str | Block, ns: Mapping):
    """插值
    """
    if isinstance(block, str):
        block = parse(block)
    return block.render(dict(ns))


# def jinja2_to_fstring

# TODO 支持语法 "{expr1||expr2||...}"，按顺序尝试表达式，返回第一个成功的（即使返回值为 "" 或 None）
# TODO: 支持把 jinja2 语法转换为此

