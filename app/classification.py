"""Objective classification of detected fields; no pixel analysis."""
from dataclasses import dataclass
import re

SENSITIVE = "Sensitive"
POTENTIAL = "Potentially sensitive"
TECHNICAL = "Technical"


@dataclass(frozen=True)
class Classification:
    level: str
    group: str
    description: str
    privacy: str


# Describe documented fields only. Never infer absent values.
DESCRIPTIONS = {
    "gpslatitude": "Latitude of the location recorded in GPS metadata.",
    "gpslongitude": "Longitude of the location recorded in GPS metadata.",
    "gpslatituderef": "Indicates whether the latitude is north or south of the equator.",
    "gpslongituderef": "Indicates whether the longitude is east or west of the prime meridian.",
    "make": "Manufacturer of the device that captured the image.",
    "model": "Model of the device that captured the image.",
    "software": "Software declared as having created or edited the image.",
    "artist": "Author or creator name declared in the metadata.",
    "author": "Author name declared in the metadata.",
    "copyright": "Copyright information declared in the file.",
    "datetime": "Modification date and time declared by the image.",
    "datetimeoriginal": "Original capture date and time declared in the metadata.",
    "datetimedigitized": "Digitization date and time declared in the metadata.",
    "usercomment": "Text comment associated with the image.",
    "imagedescription": "Text description associated with the image.",
    "xresolution": "Defines the horizontal resolution declared by the image.",
    "yresolution": "Defines the vertical resolution declared by the image.",
    "resolutionunit": "Unit used for the horizontal and vertical resolution.",
    "orientation": "Orientation used to display the image correctly.",
    "ycbcrpositioning": "Defines the positioning of chrominance components.",
    "phys": "Physical pixel density information in a PNG image.",
    "colorspace": "Color space declared in EXIF metadata.",
    "iccprofile": "Color profile used to display the image colors.",
    "iccp": "ICC color profile embedded in a PNG image.",
    "gama": "Gamma information used to display colors.",
    "srgb": "Identifies color rendering in the sRGB color space.",
    "chrm": "Chromaticity coordinates used to represent colors.",
    "exposuretime": "Exposure time declared by the camera.",
    "fnumber": "Lens aperture f-number declared by the camera.",
    "focallength": "Focal length declared by the camera.",
    "isospeedratings": "ISO sensitivity declared by the camera.",
}
CAPTURE_TECHNICAL = {"exposuretime", "fnumber", "focallength", "isospeedratings",
                     "exposureprogram", "meteringmode", "flash", "whitebalance",
                     "exposurebiasvalue", "shutterspeedvalue", "aperturevalue"}


def normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.rsplit(" / ", 1)[-1].casefold())


def classify(entry) -> Classification:
    key = normalise(entry.name)
    description = DESCRIPTIONS.get(key, "Technical field with no description available.")
    if entry.action == "Preserve" or key in CAPTURE_TECHNICAL:
        note = "Usually does not contain personal information."
        if key in {"iccprofile", "iccp"}:
            note += " The internal contents of the ICC profile are not inspected."
        return Classification(TECHNICAL, "technical", description, note)
    # An opaque block may include GPS; only use text actually read from it.
    if "gps" in key or re.search(r"\b(?:GPSLatitude|GPSLongitude)\b", entry.value, re.I):
        return Classification(SENSITIVE, "gps", description,
                              "May reveal the location associated with the image.")
    groups = (
        ("author", {"artist", "author", "creator", "copyright", "ownername", "cameraownername"}),
        ("software", {"software", "processingsoftware", "creatortool"}),
        ("device", {"make", "model", "lensmake", "lensmodel", "bodyserialnumber", "lensserialnumber", "serialnumber"}),
        ("dates", {"datetime", "datetimeoriginal", "datetimedigitized", "datecreated", "creationtime", "modificationdate"}),
        ("comments", {"usercomment", "comment", "comment", "imagedescription", "description", "title", "caption"}),
    )
    for group, names in groups:
        if key in names:
            return Classification(POTENTIAL, group, description,
                                  "May reveal authorship, tools, habits or personal details.")
    if "uniqueid" in key or "serial" in key or key in {"documentid", "instanceid"}:
        return Classification(SENSITIVE, "identifiers", description,
                              "An identifier that may allow images or devices to be linked.")
    if entry.category == "Provenance":
        return Classification(POTENTIAL, "provenance", description,
                              "May identify authorship or tools. Signatures are not validated.")
    return Classification(POTENTIAL, "other", description,
                          "Free-text field, opaque block or unrecognized field: may contain personal information. "
                          "Conservative classification; review the value before deciding.")


def privacy_counts(report) -> dict:
    classes = [classify(e) for e in report.entries]
    return {
        "sensitive_count": sum(c.level == SENSITIVE for c in classes),
        "potentially_sensitive_count": sum(c.level == POTENTIAL for c in classes),
        "technical_count": sum(c.level == TECHNICAL for c in classes),
        "gps_count": sum(c.group == "gps" for c in classes),
        "device_count": sum(c.group == "device" for c in classes),
    }


def privacy_summary(report) -> str:
    counts = privacy_counts(report)
    n, p = counts["sensitive_count"], counts["potentially_sensitive_count"]
    return (f"{n} sensitive · {p} potentially sensitive" if n or p else
            "No potentially sensitive metadata found.")
