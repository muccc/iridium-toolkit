#!/usr/bin/python

from .iridium_matplotlib import add_chanel_lines_to_axis, ALL_CHANELS, DUPLEX_CHANELS, SIMPLEX_CHANELS  # noqa: F401

__all__ = [x if isinstance(x, str) else x.__name__ for x in (add_chanel_lines_to_axis, 'ALL_CHANELS', 'DUPLEX_CHANELS', 'SIMPLEX_CHANELS')]
