"""GUI entry point for the MetaWipe desktop executable."""
import sys
from app.cli import main

if __name__ == '__main__':
    raise SystemExit(main(['gui', *sys.argv[1:]]))
