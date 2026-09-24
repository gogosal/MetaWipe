# Contributing to MetaWipe

Contributions should improve privacy, reliability or usability while keeping the application simple and local.

## Setup

Create a virtual environment and install `requirements.txt`. Launch with `python -m metawipe` and inspect CLI options with `python -m metawipe --help`.

## Development principles

- Share analysis, classification and cleaning between GUI and CLI. Keep parsers and privacy decisions out of widgets.
- Preserve compressed data and correct image display. Cleaning must not re-encode images.
- Never overwrite originals or existing destinations. Fail with a useful explanation when preservation cannot be guaranteed.
- Do not introduce network calls, telemetry, invented AI probabilities or results unsupported by detected data.
- Document sources for new descriptions and classifications. Unknown fields must remain explicitly unknown.
- Use English for the interface, messages and documentation. Never translate metadata values read from a user's file.
- Reuse existing Qt components and theme tokens. Check both themes and narrow windows.
- Update widgets through Qt signals, never directly from workers. Keep cancellation cooperative.
- Keep compatibility entry points as wrappers around the same implementation.

## Tests

```bash
python -m unittest discover -v
```

On headless Linux, set `QT_QPA_PLATFORM=offscreen`. Use synthetic images in temporary directories. Engine changes should verify compressed data, decoded pixels/frames, selected metadata and the original file. Interface changes should exercise real workflows.

Pull requests should explain the problem, change, resulting behavior, validation and relevant limitations. Include a real screenshot for UI changes. Do not publish personal photographs, private reports or identifying paths.

## Reporting issues

Include MetaWipe version, operating system, Python version, reproduction steps and exact error. Prefer a small synthetic file. If the issue only reproduces with a private photograph, do not attach it publicly.

Do not commit builds, virtual environments, caches, keys, credentials, personal reports or local history.
