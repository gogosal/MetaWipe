"""Progressive processing shared by the GUI and CLI."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from .engine import scan_image
from .cleaner import clean_image
from .classification import privacy_counts
from .files import checkpoint, Cancelled, unique_output


@dataclass
class BatchItem:
    file: str
    status: str = 'Pending'
    metadata_count: int | None = None
    sensitive_count: int = 0
    potentially_sensitive_count: int = 0
    gps_count: int = 0
    device_count: int = 0
    output: str | None = None
    removed_count: int = 0
    error: str | None = None
    format: str | None = None
    file_hash: str | None = None
    remaining: list[str] | None = None

    def to_dict(self):
        return asdict(self)


def process_batch(paths, operation='scan', output_dir=None, *, cancel=None,
                  progress=None, clean_options=None):
    """Keep only the current file and its metadata in memory.

    progress(completed, total, filename, stage) reflects actual work, without delays.
    File errors do not cancel the batch. Cancelled propagates to the caller.
    """
    if operation not in {'scan', 'clean'}:
        raise ValueError('Unknown operation.')
    total = len(paths)
    output_dir = Path(output_dir).expanduser().resolve() if output_dir else None
    if output_dir and not output_dir.is_dir():
        raise ValueError('The output folder does not exist.')
    for index, path in enumerate(paths):
        checkpoint(cancel)
        path = Path(path)
        def emit(stage):
            if progress:
                progress(index, total, path.name, stage)
        item = BatchItem(str(path))
        report = result = None
        try:
            if operation == 'scan':
                report = scan_image(path, progress=emit, cancel=cancel)
                item.status = 'Analyzed'
            else:
                options = dict(clean_options or {})
                result = clean_image(path, output_dir=output_dir, progress=emit,
                                     cancel=cancel, **options)
                report = result.before
                item.status = 'Cleaned' if result.verified else 'Partial'
                item.output = str(result.path)
                item.removed_count = sum(c.status == 'REMOVED' for c in result.changes)
                item.remaining = result.remaining
            counts = privacy_counts(report)
            for name in ('sensitive_count', 'potentially_sensitive_count', 'gps_count', 'device_count'):
                setattr(item, name, counts[name])
            item.metadata_count = len(report.entries)
            item.format, item.file_hash = report.format, report.file_hash
        except Cancelled:
            raise
        except Exception as exc:
            item.status = 'Error'
            item.error = str(exc) or type(exc).__name__
        if progress:
            progress(index + 1, total, path.name, item.status)
        yield item, report, result


def batch_summary(items):
    analysed = [i for i in items if i.metadata_count is not None]
    return {
        'files': len(items), 'analysed': len(analysed),
        'with_sensitive_metadata': sum(bool(i.sensitive_count or i.potentially_sensitive_count) for i in analysed),
        'with_gps': sum(bool(i.gps_count) for i in analysed),
        'with_device': sum(bool(i.device_count) for i in analysed),
        'errors': sum(i.status == 'Error' for i in items),
        'pending': sum(i.status == 'Pending' for i in items),
    }
