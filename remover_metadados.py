#!/usr/bin/env python3
"""Compatibility entry point for MetaWipe; requires the metawipe package."""
from app.engine import *
from app.cleaner import clean_image, remover_metadados
from app.gui import create_window
from app.cli import legacy_main as main

if __name__ == '__main__':
    raise SystemExit(main())
