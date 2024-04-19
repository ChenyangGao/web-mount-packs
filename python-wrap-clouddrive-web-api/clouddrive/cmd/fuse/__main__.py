#!/usr/bin/env python3
# encoding: utf-8

from pathlib import Path
from runpy import run_path

run_path(str(Path(__file__).with_name("__init__.py")), run_name="__main__")
