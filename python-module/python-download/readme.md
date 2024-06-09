# Python for download..

## Installation

You can install from [pypi](https://pypi.org/project/python-download/)

```console
pip install -U python-download
```

## Usage

### Module

```python
import download
```

### Command

```console
$ python-download -h
usage: python-download [-h] [-d SAVEDIR] [-r] [-hs HEADERS] [-rq] [-v] [url]

python url downloader

positional arguments:
  url                   URL(s) to be downloaded (one URL per line), if omitted, read from stdin

options:
  -h, --help            show this help message and exit
  -d SAVEDIR, --savedir SAVEDIR
                        path to the downloaded file
  -r, --resume          skip downloaded data
  -hs HEADERS, --headers HEADERS
                        dictionary of HTTP Headers to send with
  -rq, --use-requests   use `requests` module
  -v, --version         print the current version
```
