__all__ = [
    'make_repl_using_render', 'make_repl_using_template', 'make_repl_using_mod_format', 
    'make_repl_using_format_map', 'make_repl_using_format', 'make_repl_using_match_expand', 
    'wrap_repl_with_predicate', 
]

from collections import ChainMap
from functools import update_wrapper
from re import Match
from string import Template
from typing import Callable, Mapping, Protocol, Union


class SupportRender(Protocol):
    def render(self, context: Mapping) -> str:
        ...


def _render_match_mapping(
    render: Callable[[Mapping], str], 
    extra: Mapping = {}, 
) -> Callable[[Match], str]:
    count = 0
    def repl(match: Match) -> str:
        nonlocal count
        count += 1
        return render(ChainMap(
            {'_i': count, '_0': match.group()}, 
            dict(('_%d' % i, v) for i, v in enumerate(match.groups(), 1)), 
            match.groupdict(), 
            extra, 
        ))
    return repl


def make_repl_using_render(
    template: SupportRender, 
    extra: Mapping = {}, 
) -> Callable[[Match], str]:
    return _render_match_mapping(template.render, extra)


def make_repl_using_template(
    template: Union[str, Template], 
    extra: Mapping = {}, 
    safe: bool = False, 
) -> Callable[[Match], str]:
    if isinstance(template, str):
        template = Template(template)
    render = template.safe_substitute if safe else template.substitute
    return _render_match_mapping(render, extra)


def make_repl_using_mod_format(
    template: str, 
    extra: Mapping = {}, 
) -> Callable[[Match], str]:
    return _render_match_mapping(template.__mod__, extra)


def make_repl_using_format_map(
    template: str, 
    extra: Mapping = {}, 
) -> Callable[[Match], str]:
    return _render_match_mapping(template.format_map, extra)


def make_repl_using_format(
    template: str, 
    extra: Mapping = {}, 
) -> Callable[[Match], str]:
    if extra is None:
        extra = {}
    count = 0
    render = template.format
    def repl(match: Match) -> str:
        nonlocal count
        count += 1
        return render(
            match.group(), *match.groups(), 
                **ChainMap(
                {'_i': count, '_0': match.group()}, 
                dict(('_%d' % i, v) for i, v in enumerate(match.groups(), 1)), 
                match.groupdict(), 
                extra, 
            )
        )
    return repl


def make_repl_using_match_expand(template: str) -> Callable[[Match], str]:
    def repl(match: Match) -> str:
        return match.expand(template)
    return repl


def wrap_repl_with_predicate(
    repl: Callable[[Match], str], 
    predicate: Callable[[Match], bool] = lambda _: True
) -> Callable[[Match], str]:
    def wrapper(match: Match) -> str:
        if predicate(match):
            return repl(match)
        return match.group()
    return update_wrapper(wrapper, repl)

