# MetaWipe

**Inspect, understand, compare and remove image metadata. Locally, without recompression.**

MetaWipe is a Python and Qt desktop privacy tool with an English interface, dark and light themes, and a CLI powered by the same analysis and cleaning engines. It builds on the existing application and its PNG, JPEG and WebP parsers.

![MetaWipe desktop interface](docs/home.png)

![Metadata explorer and privacy classification](docs/scan.png)

Screenshots show the real application. Example metadata comes from synthetic images; the app does not preload demonstration results.

## Features

- **Scan and Metadata Explorer:** searchable fields, filters, values, sources, explanations and a sliding details panel.
- **Objective privacy classification:** sensitive, potentially sensitive and technical fields, without arbitrary scores.
- **Quick clean:** choose a profile and review planned removals before saving.
- **Before/after comparison:** sizes, formats, counts and exact removed, preserved, changed or added fields.
- **Batch and folders:** multiple selection, drag and drop, optional subfolders, real progress and safe cancellation.
- **Four profiles:** Privacy, Full clean, Keep technical metadata and Custom.
- **Reports:** copy JSON or export TXT, JSON and CSV, including cleaning diffs.
- **Optional local history:** off by default; no image copies or metadata values.
- **CLI:** images and folders, profiles, JSON, configurable output and quiet mode.

## Supported formats

| Format | Support |
| --- | --- |
| PNG / APNG | Transparency, palettes, 16-bit images, color profiles and animation |
| JPEG / JPG | Baseline and progressive images, orientation, ICC and Adobe CMYK interpretation |
| WebP | Lossy, lossless, transparency and animation |

Output keeps the original format. Cleaning does not convert, resize or re-encode the image. HEIC, AVIF, TIFF and RAW are not supported.

## Installation

Requires **Python 3.10–3.14** and a graphical session for the desktop interface.

On Windows, run **install_windows.bat**, then **start_windows.bat**.

For manual setup on Windows, Linux or macOS:

```bash
python -m venv .venv
```

Activate with `.venv\Scripts\activate.bat` in CMD, `.\.venv\Scripts\Activate.ps1` in PowerShell, or `source .venv/bin/activate` on Linux/macOS. Then:

```bash
python -m pip install -e ".[gui]"
metawipe
```

For CLI use without Qt: `python -m pip install -e .`. To run from the project folder without installing a command: `python -m metawipe`. Dependency installation needs Internet access; scanning and cleaning work offline. Linux also needs the native libraries required by Qt.

### Updating an existing checkout

1. Close the app and preserve any uncommitted changes in your repository.
2. Copy the complete release contents into your project folder, including **metawipe/**. Do not replace only an entry script. Releases do not include a `.git` directory.
3. Run `install_windows.bat`, then `start_windows.bat`.
4. If you use an executable, rebuild it with `build_windows.bat`; an old executable does not load updated source files.

Version 3.0.1 adopts the MetaWipe name and English interface. Existing PixelGuard preferences are reused on first launch if no MetaWipe preferences exist. An existing history database is reused in place, avoiding duplicate private records.

Previous Python imports and the old CLI command remain compatibility aliases for the same engine. `remover_metadados.py`, `instalar_windows.bat`, `iniciar_windows.bat` and `criar_exe_windows.bat` continue to work.

## Usage

### Scan

Select or drop an image and choose **Analyze metadata**. Select a row to inspect its value, source, explanation, privacy classification and removal availability.

- `Ctrl+O`: choose an image on the current page.
- `Ctrl+K`: search Scan results.
- `Ctrl+1`: Quick clean; `Ctrl+2`: Scan.
- **Report ▾**: copy JSON or export a file.

Counts represent fields or blocks exposed by the reader, not every possible property inside opaque blocks. GPSLatitude and GPSLatitudeRef count as two fields. Removable and technical counts may overlap: technical capture settings can be removable, while data required for display stays protected.

### Cleaning profiles

Selecting an image in Quick clean analyzes it in the background and prepares the cleaning plan. Choose a profile, review the selection, and save the copy.

| Profile | Behavior |
| --- | --- |
| Privacy | Removes sensitive and potentially sensitive fields and opaque blocks. Keeps recognized technical information. |
| Full clean | Removes every removable item, including technical capture settings that can be removed without changing the image appearance. |
| Keep technical metadata | Keeps recognized technical fields and removes the rest. With the current classification, it intentionally selects the same fields as Privacy. |
| Custom | Select individual fields or categories for one image; select categories for batches. |

Orientation, resolution/density, ICC and other data required for supported image display are **protected**. XMP, IPTC and provenance are handled as whole blocks rather than individual XML properties. Exposed EXIF, JFIF and JFXX thumbnails can be removed. Removing provenance or signatures removes that information from the file; the app does not authenticate signatures.

After saving, **View changes** opens the complete diff; **Inspect cleaned copy** scans the result.

### Batches and folders

Open **Batch & folders**, add images or select **Scan folder**, and enable **Include subfolders** when needed. Selecting a folder or dropping multiple files starts analysis after discovery.

- **Analyze all** refreshes results for the list.
- **Clean selected** processes rows selected with Ctrl/Shift.
- **Clean all** processes the complete list.
- **Cancel** stops at a safe point; completed results stay valid.
- **View** opens Scan; cleaned rows also offer the copy and comparison.

Progress counts completed files in the current job. Privacy summaries refer to the originals analyzed. Individual errors do not stop the batch. Background workers process one image at a time.

Copies use `photo_clean.jpg`, `photo_clean_2.jpg`, and so on. A shared output folder receives numbered filenames for collisions; source subfolder structure is not recreated. Discovery finishes before cleaning, so new copies do not re-enter that batch. Copies from previous runs may appear in a later scan.

### Reports and history

**Reports** shows the latest scan, clean or batch summary. Batch summaries contain per-file counts and status; individual reports include field values. Full reports are not automatically written to disk.

TXT and JSON preserve detected text. CSV prefixes an apostrophe to cells that spreadsheets could interpret as formulas. Oversized values are marked as truncated. Reports may contain personal information and local paths. Export saves only to the chosen location and never overwrites an existing file.

**History** stores only basename, operation, counts and timestamp, up to 5,000 records. Turning it off prevents new entries; **Clear history** deletes previous entries. History is not encrypted and contains no images or metadata values.

Default locations:

- Windows: `%LOCALAPPDATA%\MetaWipe\history.sqlite3`.
- Linux: `$XDG_DATA_HOME/MetaWipe/history.sqlite3`, or `~/.local/share/MetaWipe/history.sqlite3`.
- macOS: `~/Library/Application Support/MetaWipe/history.sqlite3`.

Upgrades reuse an existing database in the corresponding `PixelGuard` directory when no MetaWipe database exists. **Clear history** clears the active database, including a reused one.

## CLI

Use `python -m metawipe` instead of `metawipe` when running directly from source.

```bash
metawipe --help
metawipe scan image.png
metawipe scan image.png --json
metawipe scan ./photos --recursive --json --output report.json
metawipe clean image.png
metawipe clean image.png --profile privacy
metawipe clean image.png --profile full --output image_clean.png
metawipe clean ./photos --recursive --profile technical --output ./copies
metawipe clean image.png --profile custom --remove gps --remove software
metawipe clean image.png --profile custom --remove-id ID_FROM_SCAN
metawipe scan ./photos --json --quiet
```

The output folder must exist. For one image, `--output` accepts a file or existing folder. For folder cleaning, it accepts an existing folder; without it, each copy stays beside its source. For Scan, `--output` saves the report. Folder reports use JSON with `--json`, otherwise a text summary.

`--quiet` suppresses normal messages; `--json` still produces explicitly requested output. Errors remain visible. The CLI does not write GUI history. `Ctrl+C` cancels while preserving completed results.

| Exit code | Meaning |
| --- | --- |
| 0 | Complete |
| 1 | File, validation or write error; at least one error in a batch |
| 2 | Invalid arguments |
| 3 | At least one partial clean, with no other errors |
| 130 | Canceled |

Original script commands remain available:

```bash
python remover_metadados.py image.png
python remover_metadados.py image.webp --scan
python remover_metadados.py image.png -o copy.png
python remover_metadados.py --gui image.png
```

Legacy cleaning uses Full clean, matching the original behavior. New commands and the GUI default to Privacy.

## PRIVACY

**Images and metadata are processed on your computer. The application does not send them to servers.** Application code has no network clients, uploads, analytics or tracking.

History is off by default; preferences stay local. Images are read one at a time. Limited previews do not affect saved images. Cleaning temporarily writes in the output folder, removing the temporary file after success, an error or normal cancellation. An abrupt system interruption can leave a temporary file but does not publish an incomplete copy.

Classification describes risks of **detected fields**. Unknown and opaque fields are conservatively classified as potentially sensitive. The details panel says “Technical field with no description available.” when no documented description exists. An absence of detected fields is not a certification of anonymity.

AI references are text matches in metadata only. There is no pixel-based AI detection, invented probability, C2PA authentication or visual watermark removal. C2PA alone does not prove AI generation.

## Safe saving and image integrity

The engine edits containers and copies compressed image data. Cleaning does not call `Image.save` to create the result. It preserves format, dimensions, bit depth, animation and supported display data.

Before publishing a copy, the engine:

1. Compares hashes of image and display data before and after cleaning.
2. Writes a temporary file, flushes it to disk and validates decoding frame by frame.
3. Scans saved bytes again and compares the complete file hash with the expected result.
4. Checks whether selected fields were removed.
5. Publishes atomically and exclusively, without replacing originals or existing destinations.

An integrity failure prevents publication. Valid output that still contains selected fields is marked **partial** and lists them. This version does not offer an option to overwrite originals.

## Limitations

- **256 MiB per file**; cleaning validation limits images to **64 million pixels** and respects Pillow's decompression safeguards.
- Decompressed text is limited to 1 MiB, with up to 5,000 entries and 16,000 displayed characters per entry. Some binary blocks appear as excerpts; proprietary formats are not fully parsed.
- Classification does not inspect internal descriptions of preserved ICC profiles or every property within opaque blocks.
- Unknown PNG/WebP extensions, unreadable EXIF and JPEG MPF/HDR/gain maps block cleaning. Scan may still inspect a readable structure.
- Selective EXIF rebuilding can be blocked when preserving MakerNotes, secondary IFDs or other opaque data. The error identifies these blocks; selecting them too, or using Full clean, may allow cleaning.
- XMP editing instructions are not applied. This is not an editor project exporter.
- Visual content and filenames may reveal personal information. The app does not modify them or promise to prevent identification by other platforms.
- Cancellation is cooperative and waits for a safe point in the current file.
- Exclusive publication uses hard links on the same filesystem. Unsupported destinations produce an error rather than a less safe write.
- Development validation used **Linux with Qt offscreen**. Native Windows/macOS behavior and executable builds still require validation on those systems.

## Development and tests

```bash
python -m pip install -r requirements.txt
python -m unittest discover -v
```

For Linux without a display:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -v
```

Tests generate synthetic images in temporary directories. Coverage includes metadata reading, classification, selective removal, decoded pixels/frames, orientation, ICC, 16-bit PNG, progressive JPEG, WebP/APNG, invalid files, duplicate names, publication races, post-write failures, batches, cancellation, exports, history and Qt workflows in both themes. GUI tests are skipped if Qt is unavailable.

### Architecture

GUI and CLI share the `metawipe` package. The `pixelguard` package is a compatibility shim with no separate engine.

| Module | Responsibility |
| --- | --- |
| `engine.py` | Container parsers, reports and image/display invariants |
| `cleaner.py` | Profile application, validation and safe publication |
| `classification.py` | Documented descriptions and privacy classification |
| `profiles.py` | Shared selection rules |
| `files.py` | Discovery, available output names and cancellation points |
| `batch.py` | Progressive iterator and summaries, independent of Qt |
| `diff.py` | Field comparison, including repeated names |
| `reports.py` | TXT, JSON and CSV |
| `history.py` | Optional local SQLite history |
| `gui.py` | Existing Qt components, pages and background jobs |
| `cli.py` | Arguments, console output and shared engine access |

### Windows executables

Run `build_windows.bat` on Windows after installation. It produces `dist\MetaWipe.exe` and `dist\metawipe-cli.exe` with the included application icon. The build needs Internet access to install PyInstaller. No prebuilt executables are included.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md). Keep builds, caches, personal images, reports, history, credentials and API keys out of the repository.

Licensed under the [MIT License](LICENSE).
