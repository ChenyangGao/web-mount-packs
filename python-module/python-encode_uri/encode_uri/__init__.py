#!/usr/bin/env python3
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 3)
__all__ = ["encode_uri", "encode_uri_component", "encode_uri_component_loose"]

from urllib.parse import quote


translate = str.translate
TRANSTAB_ESCAPE2 = {c: f"%{c:02x}" for c in b'% '}
TRANSTAB_ESCAPE4 = TRANSTAB_ESCAPE2 | {c: f"%{c:02x}" for c in b'#?'}
TRANSTAB_ESCAPE5 = TRANSTAB_ESCAPE4 | {c: f"%{c:02x}" for c in b'/'}
TRANSTAB_HTML = {c: f"%{c:02x}" for c in b'{}<>\\|`"^'}
TRANSTAB_ESCAPE2_AND_HTML = TRANSTAB_ESCAPE2 | TRANSTAB_HTML
TRANSTAB_ESCAPE4_AND_HTML = TRANSTAB_ESCAPE4 | TRANSTAB_HTML
TRANSTAB_ESCAPE5_AND_HTML = TRANSTAB_ESCAPE5 | TRANSTAB_HTML


def encode_uri(
    uri: str, 
    /, 
    ensure_ascii: bool = False, 
    html_escape: bool = False, 
) -> str:
    if ensure_ascii:
        safe = "@()[],:;!/$&'+*=?#"
        if not html_escape:
            safe += '{}<>\\|`"^'
        return quote(uri, safe)
    elif html_escape:
        return translate(uri, TRANSTAB_ESCAPE2_AND_HTML)
    else:
        return translate(uri, TRANSTAB_ESCAPE2)


def encode_uri_component(
    uri: str, 
    /, 
    ensure_ascii: bool = False, 
    html_escape: bool = False, 
    safe_extra: str = "", 
) -> str:
    if ensure_ascii:
        safe = "()!'*"
        if not html_escape:
            safe += '{}<>\\|`"^'
        if safe_extra:
            safe += safe_extra
        return quote(uri, safe)
    if html_escape:
        transtab = TRANSTAB_ESCAPE5_AND_HTML
    else:
        transtab = TRANSTAB_ESCAPE5
    if safe_extra:
        safes = set(map(ord, safe_extra))
        transtab = {k: v for k, v in transtab.items() if k not in safes}
    return translate(uri, transtab)


def encode_uri_component_loose(
    uri: str, 
    /, 
    ensure_ascii: bool = False, 
    html_escape: bool = False, 
    quote_slash: bool = True, 
) -> str:
    if ensure_ascii:
        safe = "@()[],:;!$&'+*="
        if not quote_slash:
            safe += "/"
        if not html_escape:
            safe += '{}<>\\|`"^'
        return quote(uri, safe)
    elif html_escape:
        if quote_slash:
            return translate(uri, TRANSTAB_ESCAPE5_AND_HTML)
        else:
            return translate(uri, TRANSTAB_ESCAPE4_AND_HTML)
    elif quote_slash:
        return translate(uri, TRANSTAB_ESCAPE5)
    else:
        return translate(uri, TRANSTAB_ESCAPE4)

