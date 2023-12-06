#!/usr/bin/env python3
# encoding: utf-8

"""Python clouddrive web API wrapper.

This is a web API wrapper works with the running "clouddrive" server, and provide some methods, which refer to `os` and `shutil` modules.

- `clouddrive official website <https://www.clouddrive2.com/index.html>` 
"""

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 2)

from .client import *
from .fs import *

__all__ = client.__all__ + fs.__all__ # type: ignore
