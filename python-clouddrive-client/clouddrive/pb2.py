#!/usr/bin/env python3
# encoding: utf-8

from .proto.CloudDrive_pb2 import *

def __getattr__(name):
    raise NameError(name)
