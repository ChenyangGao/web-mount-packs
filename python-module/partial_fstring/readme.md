# Python fstring-based template interpolation.

## Installation

You can install from [pypi](https://pypi.org/project/partial_fstring/)

```console
pip install -U partial_fstring
```

## Usage

```python
from partial_fstring import parse, render

block = parse("<{a}>{b}")
block.render({"b": 1}) # get '1'

# OR
render("<{a}>{b}", {"b": 1})
```
