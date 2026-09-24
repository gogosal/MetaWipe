"""Reports derived exclusively from actual analysis results."""
from __future__ import annotations
import csv
import io
import json
from pathlib import Path
from .engine import Report, CleanResult
from .batch import BatchItem, batch_summary
from .classification import privacy_summary


def report_data(value):
    if isinstance(value, Report):
        return {'schema_version': 1, 'type': 'scan', **value.to_dict()}
    if isinstance(value, CleanResult):
        return {'schema_version': 1, 'type': 'clean', 'file': value.before.path,
                'output': str(value.path), 'profile': value.profile,
                'verified': value.verified, 'identical_image_data': value.identical_image_data,
                'remaining': value.remaining, 'before': value.before.to_dict(),
                'after': value.after.to_dict(), 'changes': [c.to_dict() for c in value.changes]}
    if isinstance(value, (list, tuple)) and all(isinstance(i, BatchItem) for i in value):
        return {'schema_version': 1, 'type': 'batch', 'summary': batch_summary(value),
                'files': [i.to_dict() for i in value],
                'scope': 'Per-file summary; privacy counts refer to the original files analyzed.'}
    raise TypeError('Unsupported report type.')


def _csv_cell(value):
    text = '' if value is None else str(value)
    # Prevent spreadsheet applications from executing formulas in metadata.
    if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')):
        return "'" + text
    return text


def render_report(value, format='json'):
    data = report_data(value)
    if format == 'json':
        return json.dumps(data, ensure_ascii=False, indent=2)
    if format == 'txt':
        if isinstance(value, Report):
            lines = [f'MetaWipe · {value.path}', f'{value.format} · {len(value.entries)} metadata fields',
                     privacy_summary(value), f'Textual AI references: {value.ai_hints}', '']
            for entry in data['metadata']:
                lines.extend([f"{entry['name']} [{entry['source']}] · {entry['level']} · {entry['action']}", entry['value'], ''])
            lines += ['WARNINGS: ' + note for note in value.warnings]
            lines += ['BLOCKED: ' + note for note in value.blockers]
            return '\n'.join(lines)
        return 'MetaWipe · report ' + data['type'] + '\n\n' + json.dumps(data, ensure_ascii=False, indent=2)
    if format != 'csv':
        raise ValueError('Available report formats: txt, json, csv.')
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    if isinstance(value, Report):
        writer.writerow(['file', 'source', 'name', 'value', 'privacy', 'category', 'action', 'ai_hint', 'truncated'])
        for entry in data['metadata']:
            writer.writerow([_csv_cell(x) for x in [value.path, entry['source'], entry['name'], entry['value'],
                             entry['level'], entry['group'], entry['action'], entry['ai_hint'], entry['truncated']]])
    elif isinstance(value, CleanResult):
        writer.writerow(['file', 'output', 'source', 'name', 'status', 'before', 'after'])
        for change in value.changes:
            writer.writerow([_csv_cell(x) for x in [value.before.path, value.path, change.source,
                                                   change.name, change.status, change.before, change.after]])
    else:
        fields = list(BatchItem('').to_dict())
        writer.writerow(fields)
        for row in data['files']:
            writer.writerow([_csv_cell(row.get(k)) for k in fields])
    return output.getvalue()


def export_report(value, path, format):
    """Publish a report without replacing an existing file."""
    import os
    import tempfile
    path = Path(path).expanduser().absolute()
    text = render_report(value, format)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.metawipe-report-', delete=False) as file:
            temporary = Path(file.name)
            file.write(text.encode('utf-8-sig' if format == 'csv' else 'utf-8'))
            file.flush()
            os.fsync(file.fileno())
        os.link(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return path
