#!/usr/bin/env python3
"""PNG, JPEG and WebP container analysis, derived from the 2.3 engine.

Metadata selection changes only container blocks. The cleaner verifies
compressed data and supported display information. Scan does not classify
the origin of pixels or authenticate C2PA signatures.
"""
from __future__ import annotations

import hashlib
import re
import struct
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path

VERSION = "3.0.1"
MAX_FILE = 256 * 1024 * 1024
MAX_TEXT = 1024 * 1024
MAX_ROWS = 5000
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TECHNICAL = "Presentation"
DESCRIPTIVE = "Descriptive"
PROVENANCE = "Provenance"
REMOVE = "Remove"
KEEP = "Preserve"

# Textual indicators only, never probabilities or verdicts about the image.
AI_TERMS = (
    "stable diffusion", "stablediffusion", "automatic1111", "comfyui",
    "midjourney", "dall-e", "dall·e", "dalle", "gpt-image", "gpt image",
    "a1111", "invokeai", "novelai", "fooocus", "c2pa.created_by.ai",
    "trainedalgorithmicmedia", "compositewithtrainedalgorithmicmedia",
    "negative prompt", "cfg scale", "sampler", "ai-generated", "ai generated",
    "flux.1", "flux-dev", "flux-schnell", "sdxl", "latent_image",
    "chatgpt", "openai", "adobe firefly", "black forest labs", "leonardo.ai",
)


class MetadataError(ValueError):
    """Invalid file, unsupported extension or unsafe operation."""


@dataclass
class Entry:
    source: str
    name: str
    value: str
    category: str = DESCRIPTIVE
    action: str = REMOVE
    ai_hint: bool = False
    id: str = ""
    value_hash: str = ""
    truncated: bool = False


@dataclass
class Report:
    format: str
    width: int = 0
    height: int = 0
    bits: int = 8
    frames: int = 1
    size: int = 0
    entries: list[Entry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    image_hash: str = ""
    file_hash: str = ""
    path: str = ""

    @property
    def removable(self) -> int:
        return sum(e.action == REMOVE for e in self.entries)

    @property
    def technical(self) -> int:
        from .classification import privacy_counts
        return privacy_counts(self)["technical_count"]

    @property
    def ai_hints(self) -> int:
        return sum(e.ai_hint for e in self.entries)

    def to_dict(self) -> dict:
        from .classification import classify, privacy_counts
        metadata = [{**asdict(e), **asdict(classify(e))} for e in self.entries]
        return {**asdict(self), "file": self.path, "metadata_count": len(self.entries),
                **privacy_counts(self), "metadata": metadata, "removable": self.removable,
                "technical": self.technical, "ai_hints": self.ai_hints,
                "scope": "Embedded metadata; no visual AI detection or signature validation."}


@dataclass
class CleanResult:
    path: Path
    before: Report
    after: Report
    identical_image_data: bool
    remaining: list[str] = field(default_factory=list)
    changes: list = field(default_factory=list)
    profile: str = "full"

    @property
    def verified(self):
        return self.identical_image_data and not self.remaining


def _text(data: bytes) -> str:
    data = data[:MAX_TEXT]
    # EXIF comments can be UTF-16 with an eight-byte prefix.
    if data.startswith(b"UNICODE\x00"):
        return data[8:].decode("utf-16", errors="replace")
    if data.startswith(b"ASCII\x00\x00\x00"):
        data = data[8:]
    return data.decode("utf-8", errors="replace").replace("\x00", " ")


def _hint(name: str, value: str) -> bool:
    content = (name + " " + value).casefold()
    return any(term in content for term in AI_TERMS) or name.casefold() in {
        "prompt", "negative_prompt", "negative prompt", "workflow", "seed"
    }


def _add(report: Report, source: str, name: str, value: str,
         category: str = DESCRIPTIVE, action: str = REMOVE) -> Entry:
    if len(report.entries) >= MAX_ROWS:
        raise MetadataError("Too many metadata fields to analyze this file.")
    # Search for indicators before shortening the text shown in the interface.
    occurrence = sum(e.source == source and e.name == name for e in report.entries)
    identity = hashlib.sha256(f"{source}\0{name}\0{occurrence}".encode()).hexdigest()[:20]
    entry = Entry(source, name, value[:16000], category, action,
                  action == REMOVE and _hint(name, value), identity,
                  hashlib.sha256(value.encode(errors="replace")).hexdigest(), len(value) > 16000)
    report.entries.append(entry)
    return entry


def _inflate(data: bytes) -> bytes:
    dec = zlib.decompressobj()
    try:
        result = dec.decompress(data, MAX_TEXT + 1)
    except zlib.error as exc:
        raise MetadataError("Invalid compressed text.") from exc
    if len(result) > MAX_TEXT or not dec.eof:
        raise MetadataError("Compressed text is too large or incomplete.")
    return result


def _png_text(kind: bytes, payload: bytes) -> tuple[str, str]:
    key, rest = payload.split(b"\x00", 1)
    name = key.decode("latin-1")
    if kind == b"tEXt":
        return name, rest[:MAX_TEXT].decode("latin-1")
    if kind == b"zTXt":
        if not rest or rest[0] != 0:
            raise MetadataError("Unsupported PNG compression method.")
        return name, _inflate(rest[1:]).decode("latin-1")
    if len(rest) < 2 or rest[0] not in (0, 1) or rest[1] != 0:
        raise MetadataError("Invalid iTXt field.")
    compressed = rest[0]
    _, _, content = rest[2:].split(b"\x00", 2)
    return name, _text(_inflate(content) if compressed else content)


def _exif(payload: bytes, report: Report, source: str, policy=None) -> tuple[bytes | None, bytes | None]:
    """Rebuild selected EXIF; calculate display data separately.

    An empty selection preserves the original block byte for byte. Selective
    rewriting rejects opaque structures it cannot faithfully reconstruct.
    """
    from PIL import ExifTags, Image
    original = payload if payload.startswith(b"Exif\x00\x00") else b"Exif\x00\x00" + payload
    choose = policy or (lambda entry: entry.action == REMOVE)
    try:
        exif = Image.Exif()
        exif.load(original)
        technical, kept = Image.Exif(), Image.Exif()
        technical_tags = {274, 282, 283, 296, 531}
        nested = {34665, 34853, 40965, 330}
        decisions = []
        opaque_retained = []
        start = len(report.entries)
        for tag, value in exif.items():
            if tag in {34665, 34853}:
                continue
            name = ExifTags.TAGS.get(tag, f"Tag {tag}")
            protected = tag in technical_tags
            if tag == 274 and (not isinstance(value, int) or value not in range(1, 9)):
                raise MetadataError("Invalid EXIF orientation; lossless cleaning is blocked.")
            entry = _add(report, source, name, _text(value) if isinstance(value, bytes) else str(value),
                         TECHNICAL if protected else DESCRIPTIVE, KEEP if protected else REMOVE)
            remove = choose(entry)
            decisions.append(remove)
            if protected:
                technical[tag] = value
            if not remove:
                if tag in nested or tag in {37500, 50341} or tag not in ExifTags.TAGS:
                    opaque_retained.append(name)
                else:
                    kept[tag] = value
        for tag in (34665, 34853):
            if tag not in exif:
                continue
            values = {}
            for child_tag, value in exif.get_ifd(tag).items():
                protected = tag == 34665 and child_tag == 40961
                names = ExifTags.GPSTAGS if tag == 34853 else ExifTags.TAGS
                name = ("GPS / " if tag == 34853 else "") + names.get(child_tag, f"Tag {child_tag}")
                entry = _add(report, source, name, _text(value) if isinstance(value, bytes) else str(value),
                             TECHNICAL if protected else DESCRIPTIVE, KEEP if protected else REMOVE)
                remove = choose(entry)
                decisions.append(remove)
                if protected:
                    technical[34665] = {40961: value}
                if not remove:
                    if child_tag in nested or child_tag == 37500 or child_tag not in names:
                        opaque_retained.append(name)
                    else:
                        values[child_tag] = value
            if values:
                kept[tag] = values
        # IFD1 can contain a thumbnail and private values not exposed by Pillow.
        tiff = original[6:]
        endian = "little" if tiff[:2] == b"II" else "big"
        ifd = int.from_bytes(tiff[4:8], endian)
        count = int.from_bytes(tiff[ifd:ifd + 2], endian)
        next_pos = ifd + 2 + count * 12
        thumbnail = int.from_bytes(tiff[next_pos:next_pos + 4], endian)
        if thumbnail:
            entry = _add(report, source, "Secondary IFD / thumbnail", "Secondary EXIF block; removed as a whole.")
            remove = choose(entry)
            decisions.append(remove)
            if not remove:
                opaque_retained.append(entry.name)
        canonical = technical.tobytes() if len(technical) else None
        if original[6:] != (canonical or b"").removeprefix(b"Exif\x00\x00") and not any(e.action == REMOVE for e in report.entries[start:]):
            entry = _add(report, source, "Additional EXIF structure", "EXIF structure not required for display; rebuilt in canonical form.")
            decisions.append(choose(entry))
        if not any(decisions):
            return original, canonical
        if opaque_retained:
            raise MetadataError("Selective cleaning cannot preserve these opaque EXIF blocks: " +
                                ", ".join(opaque_retained) + ". Select them too or use Full clean.")
        return kept.tobytes() if len(kept) else None, canonical
    except MetadataError:
        raise
    except Exception as exc:
        report.blockers.append("Unreadable EXIF: orientation cannot be safely preserved.")
        _add(report, source, "Unreadable EXIF", f"{len(payload):,} bytes; {type(exc).__name__}")
        return original, original


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def riff_chunk(kind: bytes, payload: bytes) -> bytes:
    return kind + struct.pack("<I", len(payload)) + payload + (b"\x00" if len(payload) & 1 else b"")


def _hash_piece(hasher, kind: bytes, payload: bytes) -> None:
    hasher.update(struct.pack(">I", len(kind)) + kind + struct.pack(">Q", len(payload)))
    hasher.update(payload)


def _parse_png(data: bytes, policy=None, progress=None) -> tuple[Report, bytes]:
    report = Report("PNG", size=len(data))
    choose = policy or (lambda entry: entry.action == REMOVE)
    preserved = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"cHRM", b"gAMA", b"iCCP",
                 b"sBIT", b"sRGB", b"bKGD", b"pHYs", b"hIST", b"sPLT", b"cICP", b"mDCV",
                 b"cLLI", b"acTL", b"fcTL", b"fdAT", b"sTER", b"oFFs", b"sCAL"}
    structural = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"acTL", b"fcTL", b"fdAT", b"tRNS"}
    output = [PNG_SIGNATURE]
    hasher = hashlib.sha256()
    pos, count, idats, seen_end = 8, 0, 0, False
    while pos < len(data):
        if pos + 12 > len(data):
            raise MetadataError("Truncated PNG.")
        length = struct.unpack_from(">I", data, pos)[0]
        end = pos + 12 + length
        if end > len(data) or count > 100000:
            raise MetadataError("Invalid or incomplete PNG chunk.")
        kind, payload = data[pos + 4:pos + 8], data[pos + 8:end - 4]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != struct.unpack_from(">I", data, end - 4)[0]:
            raise MetadataError(f"Invalid CRC in PNG chunk {kind!r}.")
        if count == 0 and (kind != b"IHDR" or length != 13):
            raise MetadataError("Invalid PNG header.")
        if kind == b"IHDR":
            if count:
                raise MetadataError("PNG contains duplicate headers.")
            report.width, report.height, report.bits = struct.unpack_from(">IIB", payload)
        if kind == b"IDAT":
            idats += 1
        if kind == b"acTL":
            if length != 8:
                raise MetadataError("Invalid APNG header.")
            report.frames = struct.unpack_from(">I", payload)[0]
        if kind in preserved:
            output.append(data[pos:end])
            _hash_piece(hasher, kind, payload)
            if kind not in structural:
                value = f"{length:,} bytes; color/display data"
                if kind == b"pHYs" and length == 9:
                    x, y, unit = struct.unpack(">IIB", payload)
                    value = f"{x} × {y} " + ("pixels/meter" if unit == 1 else "relative units")
                _add(report, "PNG", kind.decode("ascii"), value, TECHNICAL, KEEP)
        elif kind == b"eXIf":
            if progress:
                progress("Checking EXIF…")
            exif, tech = _exif(payload, report, "PNG / EXIF", policy)
            if exif:
                output.append(png_chunk(kind, exif[6:]))
            if tech:
                _hash_piece(hasher, kind, tech[6:])
        elif kind in {b"tEXt", b"zTXt", b"iTXt"}:
            try:
                name, value = _png_text(kind, payload)
            except (ValueError, MetadataError) as exc:
                name, value = kind.decode(), f"Unreadable text ({length:,} bytes): {exc}"
                report.warnings.append("A text field could not be fully read; cleaning removes its entire block.")
            entry = _add(report, f"PNG / {kind.decode()}", name, value)
            if not choose(entry):
                output.append(data[pos:end])
        elif kind in {b"caBX", b"dSIG"}:
            entry = _add(report, "PNG", "C2PA / JUMBF" if kind == b"caBX" else "dSIG signature",
                         _text(payload), PROVENANCE)
            if not choose(entry):
                output.append(data[pos:end])
        elif kind == b"tIME":
            entry = _add(report, "PNG", "Modification date", payload.hex())
            if not choose(entry):
                output.append(data[pos:end])
        else:
            # An unknown extension may be essential for correct display.
            name = kind.decode("ascii", errors="replace")
            report.blockers.append(f"PNG extension {name} is not supported for lossless cleaning.")
            _add(report, "PNG", name, f"{length:,} bytes; unknown extension")
            output.append(data[pos:end])
            _hash_piece(hasher, kind, payload)
        pos, count = end, count + 1
        if kind == b"IEND":
            if length:
                raise MetadataError("Invalid IEND.")
            seen_end = True
            break
    if not seen_end or not idats or not report.width or not report.height:
        raise MetadataError("Incomplete PNG structure.")
    if pos < len(data):
        entry = _add(report, "PNG", "Data after IEND", f"{len(data) - pos:,} additional bytes")
        if not choose(entry):
            output.append(data[pos:])
    report.image_hash = hasher.hexdigest()
    return report, b"".join(output)


def _jpeg_parts(data: bytes):
    """Split JPEG into segments, including every scan in progressive files."""
    pos = 2
    while pos < len(data):
        start = pos
        if data[pos] != 0xFF:
            raise MetadataError("Invalid JPEG marker.")
        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos == len(data):
            raise MetadataError("Truncated JPEG.")
        marker = data[pos]
        pos += 1
        if marker == 0xD9:
            yield marker, data[start:pos], b""
            if pos < len(data):
                yield -1, data[pos:], data[pos:]
            return
        if marker in (0x00, 0xD8) or 0xD0 <= marker <= 0xD7:
            raise MetadataError("Unexpected JPEG marker outside a scan.")
        if marker == 0x01:
            yield marker, data[start:pos], b""
            continue
        if pos + 2 > len(data):
            raise MetadataError("Truncated JPEG.")
        length = struct.unpack_from(">H", data, pos)[0]
        end = pos + length
        if length < 2 or end > len(data):
            raise MetadataError("Truncated JPEG segment.")
        yield marker, data[start:end], data[pos + 2:end]
        pos = end
        if marker == 0xDA:
            start = pos
            while True:
                found = data.find(b"\xff", pos)
                if found < 0:
                    raise MetadataError("JPEG is missing its end marker.")
                next_pos = found + 1
                while next_pos < len(data) and data[next_pos] == 0xFF:
                    next_pos += 1
                if next_pos == len(data):
                    raise MetadataError("Truncated JPEG scan.")
                following = data[next_pos]
                if following == 0 or 0xD0 <= following <= 0xD7:
                    pos = next_pos + 1
                    continue
                yield 0, data[start:found], data[start:found]
                pos = found
                break
    raise MetadataError("JPEG is missing its end marker.")


def _parse_jpeg(data: bytes, policy=None, progress=None) -> tuple[Report, bytes]:
    report = Report("JPEG", size=len(data))
    choose = policy or (lambda entry: entry.action == REMOVE)
    output = [b"\xff\xd8"]
    hasher = hashlib.sha256()
    scans = 0
    for marker, raw, payload in _jpeg_parts(data):
        keep = True
        image_piece = True
        if marker in {0xC0, 0xC1, 0xC2}:
            if len(payload) < 6:
                raise MetadataError("Invalid JPEG header.")
            report.bits, report.height, report.width = struct.unpack_from(">BHH", payload)
        elif marker in {0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            raise MetadataError("This JPEG variant is not supported.")
        elif marker == 0xDA:
            scans += 1
        elif marker == -1:
            keep = False
            entry = _add(report, "JPEG", "Data after EOI", f"{len(payload):,} additional bytes")
            keep, image_piece = not choose(entry), False
            if b"\xff\xd8" in payload:
                report.blockers.append("JPEG contains additional images; it will not be modified.")
        elif marker == 0xFE:
            keep = False
            entry = _add(report, "JPEG / COM", "Comment", _text(payload))
            keep, image_piece = not choose(entry), False
        elif 0xE0 <= marker <= 0xEF:
            keep = False
            label = f"JPEG / APP{marker - 0xE0}"
            lower = payload[:MAX_TEXT].lower()
            if payload.startswith(b"MPF\x00") or b"hdrgm" in lower or b"gainmap" in lower or b"hdr_gain_map" in lower:
                report.blockers.append("JPEG contains MPF/HDR/gain map data: cleaning is blocked to preserve its appearance.")
            if marker == 0xE0 and payload.startswith(b"JFIF\x00"):
                if len(payload) < 14:
                    raise MetadataError("Truncated JFIF header.")
                _add(report, label, "JFIF / presentation",
                     f"Density {int.from_bytes(payload[8:10], 'big')} × {int.from_bytes(payload[10:12], 'big')}; JFIF unit {payload[7]}", TECHNICAL, KEEP)
                canonical = payload[:12] + b"\x00\x00"
                if len(payload) > 14 or payload[12:14] != b"\x00\x00":
                    entry = _add(report, label, "JFIF thumbnail", f"{len(payload) - 14} bytes; thumbnail or additional data.")
                    if choose(entry):
                        output.append(b"\xff\xe0" + struct.pack(">H", len(canonical) + 2) + canonical)
                    else:
                        output.append(raw)
                else:
                    output.append(raw)
                _hash_piece(hasher, b"JFIF", canonical)
            elif marker == 0xE0 and payload.startswith(b"JFXX\x00"):
                entry = _add(report, label, "JFXX thumbnail", f"{len(payload)} bytes; additional JPEG thumbnail.")
                keep, image_piece = not choose(entry), False
            elif marker == 0xE2 and payload.startswith(b"ICC_PROFILE\x00"):
                keep = True
                _add(report, label, "ICC profile", f"{len(payload):,} bytes; original colors", TECHNICAL, KEEP)
            elif marker == 0xEE and payload.startswith(b"Adobe"):
                keep = True
                _add(report, label, "Adobe transform", "Color component interpretation", TECHNICAL, KEEP)
            elif marker == 0xE1 and payload.startswith(b"Exif\x00\x00"):
                if progress:
                    progress("Checking EXIF…")
                exif, tech = _exif(payload, report, label + " / EXIF", policy)
                if exif:
                    output.append(b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif)
                if tech:
                    _hash_piece(hasher, b"EXIF", tech)
            else:
                name = "XMP" if b"xap/1.0/" in payload[:80] or b"xmp/extension/" in payload[:80] else "Additional data"
                category = DESCRIPTIVE
                if marker == 0xED:
                    name = "IPTC / Photoshop"
                elif marker == 0xEB and payload.startswith(b"JP"):
                    name, category = "JUMBF / possible C2PA", PROVENANCE
                entry = _add(report, label, name, _text(payload), category)
                keep, image_piece = not choose(entry), False
        if keep:
            output.append(raw)
            if image_piece:
                _hash_piece(hasher, str(marker).encode(), raw)
    if not scans or not report.width or not report.height:
        raise MetadataError("JPEG contains no supported image data.")
    report.image_hash = hasher.hexdigest()
    return report, b"".join(output)


def _parse_webp(data: bytes, policy=None, progress=None) -> tuple[Report, bytes]:
    report = Report("WebP", size=len(data))
    choose = policy or (lambda entry: entry.action == REMOVE)
    end = 8 + struct.unpack_from("<I", data, 4)[0]
    if end > len(data) or end < 12:
        raise MetadataError("Truncated WebP container.")
    parts, pos, frame_count = [], 12, 0
    hasher = hashlib.sha256()
    for _ in range(100000):
        if pos == end:
            break
        if pos + 8 > end:
            raise MetadataError("Truncated WebP chunk.")
        kind = data[pos:pos + 4]
        length = struct.unpack_from("<I", data, pos + 4)[0]
        stop = pos + 8 + length + (length & 1)
        if stop > end:
            raise MetadataError("Invalid WebP chunk.")
        payload, raw = data[pos + 8:pos + 8 + length], data[pos:stop]
        if kind == b"VP8X":
            if length != 10:
                raise MetadataError("Invalid VP8X header.")
            report.width = 1 + int.from_bytes(payload[4:7], "little")
            report.height = 1 + int.from_bytes(payload[7:10], "little")
            # Only change the EXIF and XMP presence bits.
            parts.append((kind, payload, raw))
            _hash_piece(hasher, kind, bytes([payload[0] & ~0x0C]) + payload[1:])
        elif kind in {b"VP8 ", b"VP8L", b"ALPH", b"ANIM", b"ANMF", b"ICCP"}:
            parts.append((kind, payload, raw))
            _hash_piece(hasher, kind, payload)
            if kind == b"ICCP":
                _add(report, "WebP", "ICC profile", f"{length:,} bytes; original colors", TECHNICAL, KEEP)
            if kind == b"ANMF":
                frame_count += 1
                _check_webp_frame(payload, report)
            if not report.width and kind == b"VP8 " and len(payload) >= 10:
                if payload[3:6] != b"\x9d\x01\x2a":
                    raise MetadataError("Invalid VP8 header.")
                report.width = struct.unpack_from("<H", payload, 6)[0] & 0x3FFF
                report.height = struct.unpack_from("<H", payload, 8)[0] & 0x3FFF
            elif not report.width and kind == b"VP8L" and len(payload) >= 5:
                if payload[0] != 0x2F:
                    raise MetadataError("Invalid VP8L header.")
                value = int.from_bytes(payload[1:5], "little")
                report.width, report.height = (value & 0x3FFF) + 1, ((value >> 14) & 0x3FFF) + 1
        elif kind == b"EXIF":
            if progress:
                progress("Checking EXIF…")
            exif, tech = _exif(payload, report, "WebP / EXIF", policy)
            if exif:
                parts.append((kind, exif, riff_chunk(kind, exif)))
            if tech:
                _hash_piece(hasher, kind, tech)
        elif kind in {b"XMP ", b"C2PA", b"JUMB"}:
            entry = _add(report, "WebP", kind.decode().strip(), _text(payload),
                         DESCRIPTIVE if kind == b"XMP " else PROVENANCE)
            if not choose(entry):
                parts.append((kind, payload, raw))
        else:
            _add(report, "WebP", kind.decode(errors="replace"), f"{length:,} bytes; unknown extension")
            report.blockers.append("WebP contains an unknown extension; lossless cleaning is blocked.")
            parts.append((kind, payload, raw))
            _hash_piece(hasher, kind, payload)
        pos = stop
    if pos != end or not report.width or not report.height:
        raise MetadataError("Invalid WebP structure.")
    if not any(kind in {b"VP8 ", b"VP8L", b"ANMF"} for kind, _, _ in parts):
        raise MetadataError("WebP contains no image data.")
    if end < len(data):
        trailing_entry = _add(report, "WebP", "Data after RIFF", f"{len(data) - end:,} additional bytes")
    report.frames = frame_count or 1
    has_exif = any(kind == b"EXIF" for kind, _, _ in parts)
    has_xmp = any(kind == b"XMP " for kind, _, _ in parts)
    output = []
    for kind, payload, raw in parts:
        if kind == b"VP8X":
            flags = (payload[0] & ~0x0C) | (0x08 if has_exif else 0) | (0x04 if has_xmp else 0)
            raw = riff_chunk(kind, bytes([flags]) + payload[1:])
        output.append(raw)
    body = b"WEBP" + b"".join(output)
    report.image_hash = hasher.hexdigest()
    trailing = data[end:] if end < len(data) and not choose(trailing_entry) else b""
    return report, b"RIFF" + struct.pack("<I", len(body)) + body + trailing


def _check_webp_frame(payload: bytes, report: Report) -> None:
    if len(payload) < 16:
        raise MetadataError("Truncated WebP frame.")
    pos = 16
    while pos < len(payload):
        if pos + 8 > len(payload):
            raise MetadataError("Truncated WebP subchunk.")
        kind = payload[pos:pos + 4]
        size = int.from_bytes(payload[pos + 4:pos + 8], "little")
        pos += 8 + size + (size & 1)
        if pos > len(payload):
            raise MetadataError("Invalid WebP subchunk.")
        if kind not in {b"ALPH", b"VP8 ", b"VP8L"}:
            report.blockers.append("Animated WebP contains additional subchunks; cleaning is blocked.")


def analyse_bytes(data: bytes, policy=None, progress=None) -> tuple[Report, bytes]:
    if len(data) > MAX_FILE:
        raise MetadataError("The per-image limit is 256 MiB.")
    if data.startswith(PNG_SIGNATURE):
        if progress:
            progress("Checking PNG metadata…")
        report, cleaned = _parse_png(data, policy, progress)
    elif data.startswith(b"\xff\xd8"):
        if progress:
            progress("Checking JPEG metadata…")
        report, cleaned = _parse_jpeg(data, policy, progress)
    elif len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        if progress:
            progress("Checking WebP metadata…")
        report, cleaned = _parse_webp(data, policy, progress)
    else:
        raise MetadataError("Unsupported format. Use PNG, JPG/JPEG or WebP.")
    report.file_hash = hashlib.sha256(data).hexdigest()
    return report, cleaned


def _read(path: Path) -> bytes:
    with Path(path).expanduser().open("rb") as file:
        data = file.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise MetadataError("The per-image limit is 256 MiB.")
    return data


def scan_image(path: str | Path, *, progress=None, cancel=None) -> Report:
    from .files import checkpoint
    from .classification import privacy_counts
    emit = progress or (lambda message: None)
    checkpoint(cancel)
    path = Path(path).expanduser().resolve()
    emit("Reading image…")
    data = _read(path)
    checkpoint(cancel)
    emit("Analyzing structure and metadata…")
    report, _ = analyse_bytes(data, progress=emit)
    report.path = str(path)
    checkpoint(cancel)
    emit("Checking known AI references…")
    report.ai_hints
    emit("Looking for potentially sensitive information…")
    privacy_counts(report)
    emit("Analysis complete.")
    return report


def human_size(size: int) -> str:
    for unit in ("B", "KiB", "MiB"):
        if size < 1024 or unit == "MiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return str(size)

