# Python urlopen wrapper.

## Installation

You can install via [pypi](https://pypi.org/project/python-urlopen/)

```console
pip install -U python-urlopen
```

## Usage

### Module

```python
from urlopen import urlopen
```

### Command

```console
$ python -m urlopen -h
usage: __main__.py [-h] [-d SAVEDIR] [-r] [-hs HEADERS] [-v] [url ...]

python url downloader

positional arguments:
  url                   URL(s) to be downloaded (one URL per line), if omitted, read from stdin

options:
  -h, --help            show this help message and exit
  -d SAVEDIR, --savedir SAVEDIR
                        directory to the downloading files
  -r, --resume          skip downloaded data
  -hs HEADERS, --headers HEADERS
                        dictionary of HTTP Headers to send with
  -v, --version         print the current version
```

