# BitTorrent Tool Module

- [The BitTorrent Protocol Specification](http://www.bittorrent.org/beps/bep_0003.html)
- [Peer-to-Peer (P2P) Architecture](https://www.rfc-editor.org/rfc/rfc5694)
- [Peer-to-Peer Streaming Peer Protocol (PPSPP)](https://www.rfc-editor.org/rfc/rfc7574.txt)
- http://jonas.nitro.dk/bittorrent/bittorrent-rfc.html

## Installation

You can install from [pypi](https://pypi.org/project/torrent_tool/)

```console
pip install -U torrent_tool
```

## Usage

### As a Command Line

You can use this module to convert torrent files to magnet links.

```console
$ python -m torrent_tool -h
usage: torrent_tool.py [-h] [-f] [files ...]

torrent to magnet

positional arguments:
  files       paths to torrent files

options:
  -h, --help  show this help message and exit
  -f, --full  append more detailed queries
```

### As a Module

```python
>>> import torrent_tool
>>> help(torrent_tool)

Help on module torrent_tool:

NAME
    torrent_tool - # encoding: utf-8

FUNCTIONS
    bdecode(data, /) -> 'BDecodedType'
        Decode bencode formatted bytes object.
    
    bencode(o, fp=None, /)
        Encode `object` into the bencode format.
    
    dump = bencode(o, fp=None, /)
        Encode `object` into the bencode format.
    
    load = bdecode(data, /) -> 'BDecodedType'
        Decode bencode formatted bytes object.
    
    torrent_files(data, /, tree: 'bool' = False) -> 'dict'
        show all files and their lengths for a torrent
    
    torrent_to_magnet(data, /, full: 'bool' = False, infohash_alg: 'str' = 'btih') -> 'str'
        convert a torrent to a magnet link

DATA
    __all__ = ['bencode', 'bdecode', 'dump', 'load', 'torrent_files', 'tor...

VERSION
    (0, 0, 2, 1)

AUTHOR
    ChenyangGao <https://chenyanggao.github.io>

FILE
    /path/to/torrent_tool.py
```
