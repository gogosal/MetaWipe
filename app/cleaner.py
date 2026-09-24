"""Container-based cleaning, exclusive output and post-write verification."""
from __future__ import annotations
import os
import tempfile
import warnings
from pathlib import Path
from .engine import analyse_bytes, _read, scan_image, MetadataError, CleanResult, REMOVE
from .files import unique_output, checkpoint, Cancelled
from .diff import metadata_diff
from .profiles import CleaningPolicy


def validate_decode(path: Path, cancel=None):
    """Validate compressed data without re-encoding, one frame at a time."""
    from PIL import Image
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        try:
            with Image.open(path) as image:
                if image.width * image.height > 64_000_000:
                    raise MetadataError('Image exceeds the safe validation limit of 64 million pixels.')
                for index in range(getattr(image, 'n_frames', 1)):
                    checkpoint(cancel)
                    image.seek(index)
                    image.load()
        except (MetadataError, Cancelled):
            raise
        except Exception as exc:
            raise MetadataError(f'Invalid or unsupported image data: {exc}') from exc


def clean_image(source, destination=None, *, output_dir=None, profile="full", groups=(), entry_ids=(), expected_hash=None, progress=None, cancel=None) -> CleanResult:
    emit = progress or (lambda message: None)
    source = Path(source).expanduser().resolve()
    automatic = destination is None
    destination = unique_output(source, output_dir) if automatic else Path(destination).expanduser().absolute()
    if source == destination.resolve():
        raise MetadataError('Choose another name to keep the original intact.')
    checkpoint(cancel)
    emit('Reading image…')
    policy = CleaningPolicy(profile, frozenset(groups), frozenset(entry_ids))
    data = _read(source)
    before, _ = analyse_bytes(data)
    if expected_hash is not None and before.file_hash != expected_hash:
        raise MetadataError("The file has changed since the scan. Select it again before cleaning.")
    known = {e.id for e in before.entries if e.action == REMOVE}
    if set(entry_ids) - known:
        raise MetadataError("The selection contains missing or protected fields. Scan and select again.")
    emit("Applying cleaning profile…")
    if any(policy(e) for e in before.entries):
        _, cleaned = analyse_bytes(data, policy)
    else:
        cleaned = data
    del data
    before.path = str(source)
    if before.blockers:
        raise MetadataError('\n'.join(dict.fromkeys(before.blockers)))
    extensions = {'PNG': {'.png', '.apng'}, 'JPEG': {'.jpg', '.jpeg', '.jpe'}, 'WebP': {'.webp'}}
    if destination.suffix.lower() not in extensions[before.format]:
        raise MetadataError(f'Keep the {before.format} format: conversion is not supported.')
    emit('Checking image data…')
    after, _ = analyse_bytes(cleaned)
    expected_output_hash = after.file_hash
    if after.image_hash != before.image_hash or after.blockers:
        raise MetadataError('Integrity verification failed. No copy was saved.')
    if destination.is_symlink() or destination.exists():
        raise MetadataError('The destination already exists. Choose a different name.')
    if not destination.parent.is_dir():
        raise MetadataError('The output folder does not exist.')
    checkpoint(cancel)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.metawipe-', suffix=destination.suffix,
                                         dir=destination.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(cleaned)
            file.flush()
            os.fsync(file.fileno())
        del cleaned
        emit('Validating saved file…')
        validate_decode(temporary, cancel)
        after = scan_image(temporary)
        if after.image_hash != before.image_hash or after.file_hash != expected_output_hash or after.blockers:
            raise MetadataError('Post-write verification failed. No copy was published.')
        changes = metadata_diff(before, after)
        remaining = [c.name for c in changes if c.status != 'REMOVED' and
                     any(e.id == c.entry_id and policy(e) for e in before.entries)]
        checkpoint(cancel)
        # Hard linking publishes atomically without overwriting, even in a race.
        while True:
            try:
                os.link(temporary, destination)
                break
            except FileExistsError:
                if not automatic:
                    raise MetadataError('Another process created the destination. Nothing was overwritten.')
                destination = unique_output(source, destination.parent)
        after.path = str(destination)
        result = CleanResult(destination, before, after, True)
        result.profile = profile
        result.remaining = remaining
        result.changes = changes
        emit('Cleaning partially completed.' if remaining else 'Cleaning complete.')
        return result
    except OSError as exc:
        raise MetadataError(f'Could not save the copy safely: {exc}') from exc
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def remover_metadados(origem, destino=None):
    """Original script compatibility; preserve the image format."""
    return clean_image(origem, destino).path
