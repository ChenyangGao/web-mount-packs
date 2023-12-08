#!/usr/bin/env python3
# encoding: utf-8

__all__ = ["AuthenticationError", "BadRequest", "LoginError"]


class LoginError(Exception):
    ...


class AuthenticationError(LoginError):
    ...


class BadRequest(ValueError):
    ...

