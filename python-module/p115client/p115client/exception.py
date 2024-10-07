#!/usr/bin/env python3
# encoding: utf-8

__all__ = [
    "P115Warning", "P115OSError", "AuthenticationError", "BusyOSError", "DataError", 
    "LoginError", "MultipartUploadAbort", "NotSupportedError", "OperationalError", 
]

from collections.abc import Mapping
from functools import cached_property

from .type import MultipartResumeData


class P115Warning(UserWarning):
    pass


class P115OSError(OSError):

    def __init__(self, /, *args):
        super().__init__(*args)

    def __getattr__(self, attr, /):
        message = self.message
        try:
            if isinstance(message, Mapping):
                return message[attr]
        except KeyError as e:
            raise TypeError(attr) from e
        else:
            raise TypeError(attr)

    def __getitem__(self, key, /):
        message = self.message
        if isinstance(message, Mapping):
            return message[key]
        return message

    @cached_property
    def message(self, /):
        args = self.args
        if len(args) >= 2:
            if not isinstance(args[0], int):
                return args[1]
        if args:
            return args[0]


class AuthenticationError(P115OSError):
    pass


class BusyOSError(P115OSError):
    pass


class DataError(P115OSError):
    pass


class LoginError(AuthenticationError):
    pass


class MultipartUploadAbort(P115OSError):

    def __init__(self, ticket: MultipartResumeData, /):
        self.ticket = ticket


class NotSupportedError(P115OSError):
    pass


class OperationalError(P115OSError):
    pass

