# Python hash tools.

## Installation

You can install from [pypi](https://pypi.org/project/python-hashtools/)

```console
pip install -U python-hashtools
```

## Usage

### Module

```python
import hashtools
```

### Command

```console
$ hashtools -h
usage: hashtools [-h] [-hs [hash ...]] [-s START] [-t STOP] [-v] [path ...]

calculate file hashes

positional arguments:
  path                  file path(s) to be downloaded, if omitted, read from stdin (one path per line)

options:
  -h, --help            show this help message and exit
  -hs [hash ...], --hashs [hash ...]
                        hash algorithms, default to 'md5'
  -s START, --start START
                        start from file offset, default to 0 (start of file)
  -t STOP, --stop STOP  stop until file offset, default to None (end of file)
  -v, --version         print the current version
```
