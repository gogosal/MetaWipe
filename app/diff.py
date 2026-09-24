"""Diff actual fields, treating repeated values as multisets."""
from dataclasses import dataclass, asdict
from collections import defaultdict


@dataclass(frozen=True)
class Change:
    source: str
    name: str
    status: str
    before: str | None
    after: str | None
    entry_id: str

    def to_dict(self):
        return asdict(self)


def metadata_diff(before, after):
    remaining = defaultdict(list)
    for entry in after.entries:
        remaining[(entry.source, entry.name)].append(entry)
    changes = []
    unmatched = []
    # Match preserved values first so reordered duplicates do not appear changed.
    for entry in before.entries:
        values = remaining[(entry.source, entry.name)]
        same = next((e for e in values if e.value_hash == entry.value_hash), None)
        if same:
            values.remove(same)
            changes.append(Change(entry.source, entry.name, 'PRESERVED', entry.value, same.value, entry.id))
        else:
            unmatched.append(entry)
    for entry in unmatched:
        values = remaining[(entry.source, entry.name)]
        other = values.pop(0) if values else None
        changes.append(Change(entry.source, entry.name, 'CHANGED' if other else 'REMOVED',
                              entry.value, other.value if other else None, entry.id))
    for values in remaining.values():
        changes.extend(Change(e.source, e.name, 'ADDED', None, e.value, e.id) for e in values)
    order = {e.id: i for i, e in enumerate(before.entries)}
    return sorted(changes, key=lambda c: order.get(c.entry_id, len(order)))
