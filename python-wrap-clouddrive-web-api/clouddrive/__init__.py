#!/usr/bin/env python3
# encoding: utf-8

"""This module provides some utilities for encapsulating and using CloudDrive's web APIs.

- `CloudDrive official website <https://www.clouddrive2.com/index.html>` 
"""

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 1)

from .client import *
from .fs import *

__all__ = client.__all__ + fs.__all__ # type: ignore
