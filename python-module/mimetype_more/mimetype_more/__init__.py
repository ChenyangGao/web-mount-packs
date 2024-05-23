#!/usr/bin/env python
# coding: utf-8

"""MIME - Multipurpose Internet Mail Extension

##### Reference #####

https://www.iana.org/assignments/media-types/media-types.xhtml
https://www.rfc-editor.org/rfc/rfc2045
https://www.rfc-editor.org/rfc/rfc2046
https://www.rfc-editor.org/rfc/rfc2047
https://www.rfc-editor.org/rfc/rfc2048
https://www.rfc-editor.org/rfc/rfc2049
https://docs.python.org/3/library/mimetypes.html
https://en.wikipedia.org/wiki/Media_type
https://www.w3.org/publishing/epub3/epub-spec.html#sec-cmt-supported
https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types
https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types
https://mimetype.io/all-types/
https://mimeapplication.net
https://stackoverflow.com/questions/1735659/list-of-all-mimetypes-on-the-planet-mapped-to-file-extensions

https://datatypes.net
https://extensionfile.net
https://fileinfo.com
https://filext.com
https://mimeapplication.net
https://whatext.com
https://www.filedesc.com
https://www.file-extension.org

https://pypi.org/project/filetype/
https://pypi.org/project/python-magic/
https://github.com/robert8888/mime-file-extension
https://github.com/sindresorhus/file-type
https://github.com/samuelneff/MimeTypeMap
https://www.htmlstrip.com/mime-file-type-checker
"""

__author__  = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["load"]

from . import _001_http_common_mime_types
from . import _002_mime_all_types
from . import _003_mime_extra

def load(overwrite=False):
    _001_http_common_mime_types.load(overwrite)
    _002_mime_all_types.load(overwrite)
    _003_mime_extra.load(overwrite)

load()

