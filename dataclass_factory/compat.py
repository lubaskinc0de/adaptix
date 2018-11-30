#!/usr/bin/env python
# -*- coding: utf-8 -*-
from typing import Dict, Any, Callable

from .parsers import ParserFactory


def parse(
        data,
        cls,
        trim_trailing_underscore: bool = True,
        debug_path: bool = False,
        type_factories: Dict[Any, Callable] = None,
):
    return ParserFactory(
        trim_trailing_underscore=trim_trailing_underscore,
        debug_path=debug_path,
        type_factories=type_factories,
    ).get_parser(cls)(data)