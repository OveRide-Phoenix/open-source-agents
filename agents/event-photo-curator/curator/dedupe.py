"""Connected perceptual-hash groups, keeping the sharpest eligible member."""
from .loader import Photo


def group_duplicates(photos: list[Photo], distance: int) -> int:
    valid = [p for p in photos if p.phash is not None]
    parents = list(range(len(valid)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    # shortcut: pairwise O(n²) comparisons, use a hash index for very large events.
    for i, photo in enumerate(valid):
        for j in range(i):
            if photo.phash - valid[j].phash <= distance:
                parents[root(i)] = root(j)
    groups = {}
    for i, photo in enumerate(valid):
        groups.setdefault(root(i), []).append(photo)
    duplicates = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        group = f'burst-{members[0].path.name}'
        eligible = [p for p in members if not p.reasons]
        keeper = max(eligible, key=lambda p: p.sharpness) if eligible else None
        for photo in members:
            photo.duplicate_group = group
            if keeper is not None and photo is not keeper:
                photo.reasons.append(f'Near-duplicate of {keeper.path.name}')
                duplicates += 1
    return duplicates
