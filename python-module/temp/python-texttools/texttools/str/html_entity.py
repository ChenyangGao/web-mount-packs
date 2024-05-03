import re


__all__ = ['parse_html_entity']


_cre_html_entity = re.compile(r'&#(?:(?P<base10>[0-9]*)|x(?P<base16>[0-9A-Fa-f]*));?')


def _repl_html_entity(match):
    groupdict = match.groupdict()
    if groupdict['base10']:
        return chr(int(groupdict['base10'], 10))
    elif groupdict['base16']:
        return chr(int(groupdict['base16'], 16))
    else:
        return ''


def parse_html_entity(string):
    return _cre_html_entity.sub(_repl_html_entity, string)

