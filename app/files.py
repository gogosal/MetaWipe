"""Image discovery and exclusive output paths; never overwrite originals."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Callable

EXTENSIONS = {'.png', '.apng', '.jpg', '.jpeg', '.jpe', '.webp'}


class Cancelled(Exception):
    """Cooperative cancellation before publishing the next result."""


def checkpoint(cancel: Callable[[], bool] | None = None):
    if cancel and cancel():
        raise Cancelled('Operation canceled.')


def unique_output(source: Path, directory: Path | None = None) -> Path:
    folder = Path(directory) if directory else source.parent
    stem = source.stem + '_clean'
    target = folder / (stem + source.suffix)
    index = 2
    while target.exists() or target.is_symlink():
        target = folder / f'{stem}_{index}{source.suffix}'
        index += 1
    return target


def discover(inputs, recursive=False, cancel=None):
    """Keep only paths in memory; do not follow file or folder symlinks."""
    seen = set()
    for value in inputs:
        checkpoint(cancel)
        path = Path(value).expanduser()
        if path.is_symlink():
            raise ValueError(f'Symbolic links are not followed: {path}')
        if path.is_file():
            candidates = [path]
        elif path.is_dir():
            def walk():
                for root, dirs, files in os.walk(path, followlinks=False,
                                                onerror=lambda error: (_ for _ in ()).throw(error)):
                    checkpoint(cancel)
                    dirs[:] = sorted(d for d in dirs if not (Path(root) / d).is_symlink()) if recursive else []
                    for name in sorted(files):
                        item = Path(root) / name
                        if item.suffix.lower() in EXTENSIONS and not item.is_symlink():
                            yield item
            candidates = walk()
        else:
            raise FileNotFoundError(f'Path does not exist: {path}')
        for item in candidates:
            checkpoint(cancel)
            resolved = item.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield resolved
