#!/usr/bin/env python
# coding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"

# See: 
#   - https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types
#   - https://www.w3.org/TR/epub/#sec-core-media-types
#   - https://developer.mozilla.org/en-US/docs/Web/Media/Formats/Containers#flac
#   - https://www.iana.org/assignments/media-types/media-types.xhtml
#   - https://github.com/gabriel-vasile/mimetype/blob/master/supported_mimes.md
#   - https://mimetype.io/all-types
ext_to_mime = [
 (".aac", "audio/aac"),
 (".abw", "application/x-abiword"),
 (".aif", "audio/aiff"),
 (".aifc", "audio/aiff"),
 (".aiff", "audio/aiff"),
 (".ape", "audio/ape"),
 (".arc", "application/x-freearc"),
 (".asf", "video/x-ms-asf"),
 (".avif", "image/avif"),
 (".avi", "video/x-msvideo"),
 (".azw", "application/vnd.amazon.ebook"),
 (".bin", "application/octet-stream"),
 (".bmp", "image/bmp"),
 (".bz", "application/x-bzip"),
 (".bz2", "application/x-bzip2"),
 (".cda", "application/x-cdf"),
 (".csh", "application/x-csh"),
 (".css", "text/css"),
 (".csv", "text/csv"),
 (".doc", "application/msword"),
 (".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
 (".eot", "application/vnd.ms-fontobject"),
 (".epub", "application/epub+zip"),
 (".flac", "audio/flac"),
 (".flv", "video/x-flv"),
 (".gz", "application/gzip"),
 (".gif", "image/gif"),
 (".htm", "text/html"),
 (".html", "text/html"),
 (".ico", "image/vnd.microsoft.icon"),
 (".ics", "text/calendar"),
 (".jar", "application/java-archive"),
 (".jpeg", "image/jpeg"),
 (".jpg", "image/jpeg"),
 (".js", "text/javascript"), # OR "application/javascript" "application/ecmascript"
 (".json", "application/json"),
 (".jsonld", "application/ld+json"),
 (".m3u8", "application/x-mpegURL"),
 (".m4a", "audio/mp4"),
 (".m4v", "video/mp4"),
 (".mid", "audio/midi"),
 (".midi", "audio/midi"),
 (".mjs", "text/javascript"),
 (".mov", "video/quicktime"),
 (".mp3", "audio/mpeg"),
 (".mp4", "video/mp4"),
 (".mpc", "audio/musepack"),
 (".mpeg", "video/mpeg"),
 (".mpg", "video/mpeg"),
 (".mpkg", "application/vnd.apple.installer+xml"),
 (".ncx", "application/x-dtbncx+xml"),
 (".odp", "application/vnd.oasis.opendocument.presentation"),
 (".ods", "application/vnd.oasis.opendocument.spreadsheet"),
 (".odt", "application/vnd.oasis.opendocument.text"),
 (".oga", "audio/ogg"),
 (".ogg", "application/ogg"),
 (".ogv", "video/ogg"),
 (".ogx", "application/ogg"),
 (".opf", "application/oebps-package+xml"),
 (".opus", "audio/opus"),
 (".otf", "font/otf"), # OR "application/font-sfnt" "application/vnd.ms-opentype"
 (".png", "image/png"),
 (".pdf", "application/pdf"),
 (".php", "application/x-httpd-php"),
 (".ppt", "application/vnd.ms-powerpoint"),
 (".pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
 (".psd", "image/vnd.adobe.photoshop"),
 (".rar", "application/vnd.rar"),
 (".rtf", "application/rtf"),
 (".sh", "application/x-sh"),
 (".smil", "application/smil+xml"),
 (".smi", "application/smil+xml"),
 (".sml", "application/smil+xml"),
 (".svg", "image/svg+xml"),
 (".tar", "application/x-tar"),
 (".tif", "image/tiff"),
 (".tiff", "image/tiff"),
 (".ts", "video/mp2t"),
 (".ttf", "font/ttf"), # OR "application/font-sfnt"
 (".txt", "text/plain"),
 (".vsd", "application/vnd.visio"),
 (".wav", "audio/wav"),
 (".weba", "audio/webm"),
 (".webm", "video/webm"),
 (".webp", "image/webp"),
 (".wma", "audio/x-ms-wma"),
 (".wmv", "video/x-ms-wmv"),
 (".woff", "font/woff"), # OR "application/font-woff"
 (".woff2", "font/woff2"),
 (".xht", "application/xhtml+xml"),
 (".xhtml", "application/xhtml+xml"),
 (".xls", "application/vnd.ms-excel"),
 (".xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
 (".xml", "application/xml"),
 (".xul", "application/vnd.mozilla.xul+xml"),
 (".zip", "application/zip"),
 (".3gp", "video/3gpp"),
 (".3g2", "video/3gpp2"),
 (".7z", "application/x-7z-compressed"),
]

import mimetypes

if not mimetypes.inited:
    mimetypes.init()
types_map, add_type = mimetypes._db.types_map, mimetypes._db.add_type # type: ignore
for ext, mime in ext_to_mime:
    if ext not in types_map:
        add_type(mime, ext)

