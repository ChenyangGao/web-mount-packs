#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["Block", "parse", "render"]

from collections.abc import Mapping
from re import compile as re_compile
from typing import Final


TOKEN_SPECIFICATION: Final[list[tuple[str, str]]] = [
    ("left_brace", r"\{\{"), 
    ("right_brace", r"\}\}"), 
    ("less_than", r"\\<"), 
    ("greater_than", r"\\>"), 
    ("left_block_with_name", r"<(?P<lbq>\?)?\{\{(?!\d)(?P<lbn>\w+)\}\}"), 
    ("left_block", r"<"), 
    ("right_block", r">"), 
    ("multi_fstring_placeholder", r"\{[^{}]*\}(?:\|\|\{[^{}]*\})+"), 
    ("fstring_placeholder", r"\{[^{}]*\}"), 
    ("any", r"(?s:.)")
]
tokenize = re_compile("|".join(f"(?P<{group}>{token})" for group, token in TOKEN_SPECIFICATION)).finditer


class Block(list):

    def __init__(
        self, 
        /, 
        name: None | str = None, 
        hidden: bool = False, 
        throw: bool = False, 
    ):
        self.name = name
        self.hidden = hidden
        self.throw = throw

    def render(self, ns: dict, /) -> str:
        try:
            s = "".join(part.render(ns) for part in self)
        except Exception:
            if self.throw:
                raise
            s = ""
        if self.name:
            ns[self.name] = s
        if self.hidden:
            return ""
        return s

    __call__ = render


class String(str):

    def __str__(self, /) -> str:
        return super().__str__()

    def render(self, ns: dict, /) -> str:
        return str(self)


class FString(str):

    def __init__(self, s, /):
        self.code = compile("f%r" % str(s), "", "eval")

    def __str__(self, /) -> str:
        return super().__str__()

    def __repr__(self, /) -> str:
        return "f%r" % str(self)

    def render(self, ns: dict, /) -> str:
        return eval(self.code, ns)


class AnyExpr(str):

    def __init__(self, exprs: str, /):
        self.codes = [compile(expr, "", "eval") for expr in exprs.strip("{}").split("}||{")]

    def render(self, ns: dict, /) -> str:
        excs = []
        for code in self.codes:
            try:
                return str(eval(code, ns))
            except Exception as e:
                excs.append(e)
        raise ExceptionGroup(self, excs)


def parse(template: str) -> Block:
    """Template parsing.

    :param template: The template string.

    :return: The parsing result.

    Syntax Overview::
        1. A string surrounded by "<" and ">" is called a block, and blocks can be nested, e.g., "<...>".
        2. The string inside a block is treated as a Python f-string for interpolation. 
           If interpolation fails, the block returns an empty string "".
        3. Blocks can have names (similar to capture groups in regular expressions), placed inside "{{" and "}}". 
           The syntax is "<{{name}}...>", and the value of this block can be referenced repeatedly using "{name}".
        4. Named blocks can be defined without output, allowing later references. The syntax is "<?{{name}}...>".
        5. If you want to use "<" and ">", but not as block indicators, write them as "\\<" and "\\>".
        6. Supports the binary operator "||". The syntax is "{expr1}||{expr2}", where the two placeholders must be adjacent. 
           If "{expr1}" doesn’t raise an error, its value is used; otherwise, "{expr2}" is executed, and its value is used or 
           raises an error. This operator can be chained indefinitely.

    Introduction to Python's f-strings::
        - https://docs.python.org/3/reference/lexical_analysis.html#formatted-string-literals
        - https://peps.python.org/pep-0498/
        - https://peps.python.org/pep-0701/

    Usage Example::

        1. When scraping with MoviePilot, files can be moved and renamed using Jinja2 syntax. 
           If you use this module, you can write about 2/3 fewer lines.

            Jinja2 Example:

                {{title}}{% if year %} ({{year}}){% endif %}{% if tmdbid %} [tmdbid={{tmdbid}}]{% endif %}/Season {{season}}/{{title}} - {{season_episode}}{% if part %}-{{part}}{% endif %}{% if episode %} - 第{{episode}}集{% endif %}{% if videoFormat %} - {{videoFormat}}{% endif %}{% if edition %}.{{edition}}{% endif %}{% if videoCodec %}.{{videoCodec}}{% endif %}{% if audioCodec %}.{{audioCodec}}{% endif %}{% if releaseGroup %}-{{releaseGroup}}{% endif %}{{fileExt}}

            Syntax of this module:

                {title}< ({year})>< [tmdbid={tmdbid}]>/Season {season}/{title} - {season_episode}<-{part}>< - 第{episode}集>< - {videoFormat}><.{edition}><.{videoCodec}><.{audioCodec}><-{releaseGroup}>{fileExt}

            ----

            Jinja2 Example:

                {{title}}{% if year %} ({{year}}){% endif %}{% if tmdbid %} [tmdbid={{tmdbid}}]{% endif %}/{{title}}{% if year %} ({{year}}){% endif %}{% if part %}-{{part}}{% endif %}{% if videoFormat %} - {{videoFormat}}{% endif %}{% if edition %}.{{edition}}{% endif %}{% if videoCodec %}.{{videoCodec}}{% endif %}{% if audioCodec %}.{{audioCodec}}{% endif %}{% if releaseGroup %}-{{releaseGroup}}{% endif %}{{fileExt}}

            Syntax of this module:

                <{{prefix}}{title}< ({year})>>< [tmdbid={tmdbid}]>/{prefix}<-{part}>< - {videoFormat}><.{edition}><.{videoCodec}><.{audioCodec}><-{releaseGroup}>{fileExt}
    """
    block = Block(throw=True)
    stack = [block]
    depth = 0
    chars: list[str] = []
    chars_with_fstring = False
    def join_chars():
        nonlocal chars_with_fstring
        if chars:
            block.append((FString if chars_with_fstring else String)("".join(chars)))
            chars.clear()
        chars_with_fstring = False
    for match in tokenize(template):
        
        match group := match.lastgroup:
            case "left_block" | "left_block_with_name":
                join_chars()
                block = Block(match["lbn"], bool(match["lbq"]))
                stack[depth].append(block)
                depth += 1
                try:
                    stack[depth] = block
                except IndexError:
                    stack.append(block)
            case "right_block":
                join_chars()
                depth -= 1
                if depth < 0:
                    raise SyntaxError(f"Mismatched pairs of '<' and '>', at {match.start()}.")
                block = stack[depth]
            case "less_than":
                chars.append("<")
            case "greater_than":
                chars.append(">")
            case "multi_fstring_placeholder":
                join_chars()
                block.append(AnyExpr(match[group]))
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


def render(block: str | Block, ns: Mapping) -> str:
    """Template interpolation.

    :param block: If it's a `str`, it is treated as the template string; otherwise, it's treated as the template parsing result object.
    :param ns: The namespace, which contains the values to be referenced.

    :return: The result string after template interpolation (replacing placeholders).
    """
    if isinstance(block, str):
        block = parse(block)
    if type(ns) is not dict:
        ns = dict(ns)
    return block.render(ns)

