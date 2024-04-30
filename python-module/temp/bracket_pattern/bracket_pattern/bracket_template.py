__all__ = ['BracketTemplate']

from string import Template


class BracketTemplate(Template):
    flags = 0
    pattern = '\[(?P<named>[^\d\W]\w*)\]'

