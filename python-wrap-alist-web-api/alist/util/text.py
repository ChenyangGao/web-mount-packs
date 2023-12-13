#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["extract_origin", "complete_base_url"]

from re import compile as re_compile
from urllib.parse import urlsplit, urlunsplit

CRE_URL_SCHEME = re_compile(r"^(?i:[a-z][a-z0-9.+-]*)://")


def extract_origin(url: str, /) -> str:
    if url.startswith("://"):
        url = "http" + url
    elif CRE_URL_SCHEME.match(url) is None:
        url = "http://" + url
    urlp = urlsplit(url)
    scheme, netloc = urlp.scheme, urlp.netloc
    if not netloc:
        netloc = "localhost"
    return f"{scheme}://{netloc}"


def complete_base_url(url: str, /) -> str:
    if url.startswith("://"):
        url = "http" + url
    elif CRE_URL_SCHEME.match(url) is None:
        url = "http://" + url
    urlp = urlsplit(url)
    repl = {"query": "", "fragment": ""}
    if not urlp.netloc:
        repl["path"] = "localhost"
    return urlunsplit(urlp._replace(**repl)).rstrip("/")

