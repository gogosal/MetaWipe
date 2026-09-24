"""Cleaning policy shared by all interfaces."""
from dataclasses import dataclass
from .classification import classify, TECHNICAL

PROFILE_LABELS = {
    'privacy': 'Privacy',
    'full': 'Full clean',
    'technical': 'Keep technical metadata',
    'custom': 'Custom',
}
GROUP_LABELS = {
    'gps': 'GPS location', 'author': 'Author and copyright',
    'software': 'Software', 'device': 'Device', 'dates': 'Dates and times',
    'comments': 'Comments and descriptions', 'identifiers': 'Identifiers',
    'provenance': 'Provenance and signatures', 'other': 'Other fields / opaque blocks',
    'technical': 'Removable technical data (e.g. exposure)',
}
RECOMMENDED = frozenset(GROUP_LABELS) - {'technical'}


@dataclass(frozen=True)
class CleaningPolicy:
    profile: str = 'full'
    groups: frozenset[str] = frozenset()
    entry_ids: frozenset[str] = frozenset()

    def __post_init__(self):
        if self.profile not in PROFILE_LABELS:
            raise ValueError('Unknown cleaning profile.')
        unknown = set(self.groups) - set(GROUP_LABELS)
        if unknown:
            raise ValueError('Unknown categories: ' + ', '.join(sorted(unknown)))

    def __call__(self, entry):
        if entry.action == 'Preserve':
            return False  # Never remove data required for correct display.
        if self.profile == 'full':
            return True
        if self.profile == 'custom':
            return entry.id in self.entry_ids or classify(entry).group in self.groups
        return classify(entry).level != TECHNICAL
