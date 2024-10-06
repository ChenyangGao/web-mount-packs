#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["RequestKeywords", "MultipartResumeData", "P115Cookies", "P115URL"]

from collections.abc import Callable
from functools import cached_property
from http.cookiejar import CookieJar
from re import compile as re_compile
from types import MappingProxyType
from typing import Any, Final, NotRequired, Self, TypedDict

from cookietools import cookies_str_to_dict


CRE_UID_FORMAT_match: Final = re_compile("(?P<user_id>[1-9][0-9]*)_(?P<login_ssoent>[A-Z][1-9][0-9]*)_(?P<login_timestamp>[1-9][0-9]{9,})").fullmatch
CRE_CID_FORMAT_match: Final = re_compile("[0-9a-f]{32}").fullmatch
CRE_SEID_FORMAT_match: Final = re_compile("[0-9a-f]{120}").fullmatch


class RequestKeywords(TypedDict):
    url: str
    method: str
    data: Any
    headers: Any
    parse: Callable


class MultipartResumeData(TypedDict):
    bucket: str
    object: str
    token: NotRequired[dict]
    callback: dict
    upload_id: str
    partsize: int
    parts: NotRequired[list[dict]]
    filesize: NotRequired[int]


class P115Cookies(str):

    def __getattr__(self, attr: str, /):
        try:
            return self.mapping[attr]
        except KeyError as e:
            raise AttributeError(attr) from e

    def __getitem__(self, key, /): # type: ignore
        if isinstance(key, str):
            return self.mapping[key]
        return super().__getitem__(key)

    def __repr__(self, /) -> str:
        cls = type(self)
        if (module := cls.__module__) == "__main__":
            name = cls.__qualname__
        else:
            name = f"{module}.{cls.__qualname__}"
        return f"{name}({str(self)!r})"

    def __setattr__(self, attr, value, /):
        raise TypeError("can't set attribute")

    @cached_property
    def mapping(self, /) -> MappingProxyType:
        return MappingProxyType(cookies_str_to_dict(str(self)))

    @cached_property
    def uid(self, /) -> str:
        return self.mapping["UID"]

    @cached_property
    def cid(self, /) -> str:
        return self.mapping["CID"]

    @cached_property
    def seid(self, /) -> str:
        return self.mapping["SEID"]

    @cached_property
    def user_id(self, /) -> int:
        d: dict = CRE_UID_FORMAT_match(self.uid).groupdict() # type: ignore
        self.__dict__.update(d)
        return d["user_id"]

    @cached_property
    def login_ssoent(self, /) -> int:
        d: dict = CRE_UID_FORMAT_match(self.uid).groupdict() # type: ignore
        self.__dict__.update(d)
        return d["login_ssoent"]

    @cached_property
    def login_timestamp(self, /) -> int:
        d: dict = CRE_UID_FORMAT_match(self.uid).groupdict() # type: ignore
        self.__dict__.update(d)
        return d["login_timestamp"]

    @cached_property
    def is_well_formed(self, /) -> bool:
        return (
            CRE_UID_FORMAT_match(self.uid) and 
            CRE_CID_FORMAT_match(self.cid) and 
            CRE_SEID_FORMAT_match(self.seid)
        ) is not None

    @cached_property
    def cookies(self, /) -> str:
        """115 登录的 cookies，包含 UID, CID 和 SEID 这 3 个字段
        """
        return f"UID={self.uid}; CID={self.cid}; SEID={self.seid}"

    @classmethod
    def from_cookiejar(cls, cookiejar: CookieJar, /) -> Self:
        return cls("; ".join(
            f"{cookie.name}={cookie.value}" 
            for cookie in cookiejar 
            if cookie.domain == "115.com" or cookie.domain.endswith(".115.com")
        ))


class P115URL(str):

    def __new__(cls, url: Any = "", /, *args, **kwds):
        return super().__new__(cls, url)

    def __init__(self, url: Any = "", /, *args, **kwds):
        self.__dict__.update(*args, **kwds)

    def __getattr__(self, attr: str, /):
        try:
            return self.__dict__[attr]
        except KeyError as e:
            raise AttributeError(attr) from e

    def __delitem__(self, key: str, /):
        del self.__dict__[key]

    def __getitem__(self, key: str, /): # type: ignore
        if isinstance(key, str):
            return self.__dict__[key]
        return super().__getitem__(key)

    def __setitem__(self, key: str, val, /):
        self.__dict__[key] = val

    def __repr__(self, /) -> str:
        cls = type(self)
        if (module := cls.__module__) == "__main__":
            name = cls.__qualname__
        else:
            name = f"{module}.{cls.__qualname__}"
        return f"{name}({str(self)!r}, {self.__dict__!r})"

    @property
    def mapping(self, /) -> dict[str, Any]:
        return self.__dict__

    def geturl(self, /) -> str:
        return str(self)

    url = property(geturl)

