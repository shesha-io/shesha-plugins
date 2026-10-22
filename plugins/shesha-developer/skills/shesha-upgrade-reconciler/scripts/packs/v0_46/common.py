"""Small helpers shared by the 0.46 rule modules."""


def flush(ctx, notes):
    """Forward notes collected by a rule's helpers to the context (one ctx.note per entry; INFO-prefixed ones stay informational)."""
    for text in notes:
        ctx.note(text)


def edit_mode_dicts(o):
    """yield every dict that carries an `editMode` (components, button-group items and tab items), depth first."""
    if isinstance(o, dict):
        if 'editMode' in o:
            yield o
        for v in o.values():
            yield from edit_mode_dicts(v)
    elif isinstance(o, list):
        for v in o:
            yield from edit_mode_dicts(v)
