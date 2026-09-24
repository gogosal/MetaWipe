"""MetaWipe CLI. Console operations do not import Qt."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
from .engine import VERSION, scan_image, MetadataError
from .cleaner import clean_image
from .files import discover, Cancelled
from .batch import process_batch
from .profiles import PROFILE_LABELS, GROUP_LABELS
from .reports import render_report, report_data, export_report


def build_parser():
    parser = argparse.ArgumentParser(prog='metawipe', description=
        'Inspect and remove image metadata locally, without recompression. Opens the GUI when run without arguments.')
    parser.add_argument('--version', action='version', version=f'MetaWipe {VERSION}')
    commands = parser.add_subparsers(dest='command')
    for operation, description in [('scan', 'Scan an image or folder.'),
                                   ('clean', 'Clean an image or folder, saving new copies.')]:
        command = commands.add_parser(operation, help=description, description=description)
        command.add_argument('path', type=Path, help='PNG, JPEG, WebP image or folder.')
        command.add_argument('-o', '--output', type=Path,
                             help='Scan: output report. Clean: output file or folder for copies.')
        command.add_argument('--saida', dest='output', type=Path, help=argparse.SUPPRESS)
        command.add_argument('-r', '--recursive', action='store_true', help='Include subfolders; symbolic links are not followed.')
        command.add_argument('--json', action='store_true', help='Print a structured JSON report (even with --quiet).')
        command.add_argument('-q', '--quiet', action='store_true', help='Suppress progress and success messages.')
        if operation == 'clean':
            command.add_argument('--profile', choices=list(PROFILE_LABELS), default='privacy', help='Cleaning profile (default: privacy).')
            command.add_argument('--remove', action='append', choices=list(GROUP_LABELS), default=[],
                                 help='Category to remove with the custom profile; repeatable.')
            command.add_argument('--remove-id', action='append', default=[],
                                 help='Exact field ID returned by Scan; one image only with --profile custom.')
    gui = commands.add_parser('gui', help='Open the graphical interface.')
    gui.add_argument('path', type=Path, nargs='?', help='Image to open in Scan.')
    return parser


def run_gui(path=None):
    try:
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication
        from .gui import create_window
    except ImportError:
        print('Install the GUI: python -m pip install -e ".[gui]"', file=sys.stderr)
        return 1
    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setApplicationName('MetaWipe')
    application.setOrganizationName('MetaWipe')
    application.setFont(QFont('Segoe UI', 10))
    window = create_window()
    window.show()
    if path:
        window.inspect_output(Path(path))
    return application.exec()


@contextmanager
def output_stream(path=None):
    """Stream batch results; publish report files atomically and exclusively."""
    if path is None:
        yield sys.stdout
        return
    path = Path(path).expanduser().absolute()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                        prefix='.metawipe-report-', delete=False) as file:
            temporary = Path(file.name)
            yield file
            file.flush()
            os.fsync(file.fileno())
        os.link(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def execute(args):
    path = args.path.expanduser()
    folder = path.is_dir()
    paths = list(discover([path], args.recursive))
    if args.command == 'clean':
        if args.profile != 'custom' and (args.remove or args.remove_id):
            raise ValueError('--remove and --remove-id require --profile custom.')
        if folder and args.remove_id:
            raise ValueError('--remove-id applies to one image; use --remove for batches.')
    if not folder:
        if args.command == 'scan':
            result = scan_image(paths[0])
            if args.output:
                fmt = 'json' if args.json else args.output.suffix.lower().lstrip('.')
                export_report(result, args.output, fmt if fmt in {'csv', 'json', 'txt'} else 'txt')
            elif args.json or not args.quiet:
                print(render_report(result, 'json' if args.json else 'txt'))
            return 0
        destination = args.output
        output_dir = destination if destination and destination.is_dir() else None
        result = clean_image(paths[0], None if output_dir else destination, output_dir=output_dir,
                             profile=args.profile, groups=args.remove, entry_ids=args.remove_id)
        if args.json:
            print(render_report(result))
        elif not args.quiet:
            print(('Cleaning complete: ' if result.verified else 'Partial clean: ') + str(result.path))
            print(f'{sum(c.status == "REMOVED" for c in result.changes)} metadata fields removed; image data is identical.')
            if result.remaining:
                print('Remaining: ' + ', '.join(result.remaining), file=sys.stderr)
        return 0 if result.verified else 3
    if args.command == 'clean' and args.output and not args.output.is_dir():
        raise ValueError('When cleaning folders, --output must point to an existing folder.')
    report_path = args.output if args.command == 'scan' else None
    errors = partial = done = 0
    cancelled = False
    options = {'profile': args.profile, 'groups': args.remove} if args.command == 'clean' else {}
    # Finish discovery first so outputs cannot be processed again in this run.
    with output_stream(report_path) as out:
        if args.json:
            out.write('{"schema_version": 1, "type": "batch", "results": [\n')
        try:
            for item, report, result in process_batch(paths, args.command,
                    args.output if args.command == 'clean' else None, clean_options=options):
                errors += item.status == 'Error'
                partial += item.status == 'Partial'
                if args.json:
                    if done:
                        out.write(',\n')
                    payload = report_data(result or report) if report is not None else item.to_dict()
                    out.write(json.dumps(payload, ensure_ascii=False))
                elif not args.quiet or report_path:
                    out.write(f'{item.status} · {item.file}' + (f' → {item.output}' if item.output else '') +
                              (f' · {item.error}' if item.error else '') + '\n')
                elif item.error:
                    print(f'{item.file}: {item.error}', file=sys.stderr)
                done += 1
        except (KeyboardInterrupt, Cancelled):
            cancelled = True
        if args.json:
            out.write(f'\n], "processed": {done}, "total": {len(paths)}, "errors": {errors}, '
                      f'"partial": {partial}, "cancelled": {str(cancelled).lower()}}}\n')
        elif not args.quiet or report_path:
            out.write(f'{done} / {len(paths)} processed · {errors} errors · {partial} partial\n')
    return 130 if cancelled else 1 if errors else 3 if partial else 0


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in {None, 'gui'}:
        return run_gui(getattr(args, 'path', None))
    try:
        return execute(args)
    except (KeyboardInterrupt, Cancelled):
        print('Canceled. Completed files have been preserved.', file=sys.stderr)
        return 130
    except (OSError, ValueError, ImportError) as exc:
        if args.json:
            print(json.dumps({'file': str(args.path), 'error': str(exc)}, ensure_ascii=False))
        else:
            print(f'Error: {exc}', file=sys.stderr)
        return 1


def legacy_main(argv=None):
    """Support original 2.x script commands alongside the new subcommands."""
    values = list(sys.argv[1:] if argv is None else argv)
    if '--gui' in values:
        values.remove('--gui')
        return main(['gui', *values])
    if values and values[0] not in {'scan', 'clean', 'gui', '-h', '--help', '--version'} and not values[0].startswith('-'):
        scan = '--scan' in values
        if scan:
            values.remove('--scan')
        values = ['scan' if scan else 'clean', *values]
        if scan:
            values.append('--json')
        else:
            values.extend(['--profile', 'full'])
    return main(values)


if __name__ == '__main__':
    raise SystemExit(main())
