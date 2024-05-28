#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__: list[str] = []

from . import exception
__all__.extend(exception.__all__)
from .exception import *

from . import cipher
__all__.extend(cipher.__all__)
from .cipher import *

from . import client
__all__.extend(client.__all__)
from .client import *

from . import fs
__all__.extend(fs.__all__)
from .fs import *

from . import fs_share
__all__.extend(fs_share.__all__)
from .fs_share import *

from . import fs_zip
__all__.extend(fs_zip.__all__)
from .fs_zip import *

from . import labellist
__all__.extend(labellist.__all__)
from .labellist import *

from . import offline
__all__.extend(offline.__all__)
from .offline import *

from . import recyclebin
__all__.extend(recyclebin.__all__)
from .recyclebin import *

from . import sharing
__all__.extend(sharing.__all__)
from .sharing import *

# TODO upload_tree 多线程和进度条，并且为每一个上传返回一个 task，可重试
# TODO 能及时处理文件已不存在
# TODO 为各个fs接口添加额外的请求参数
# TODO 115中多个文件可以在同一目录下同名，如何处理
# TODO 提供一个新的上传函数，上传如果失败，因为名字问题，则尝试用uuid名字，上传成功后，再进行改名，如果成功，删除原来的文件，不成功，则删掉上传的文件（如果上传成功了的话）
# TODO 如果压缩包尚未解压，则使用 zipfile 之类的模块，去模拟文件系统
# TODO: 为上传进度进行封装，创建 UploadTask 类
