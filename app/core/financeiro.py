import unicodedata


def normalize_material_name(value):
    """Return a comparison key without changing the historical display value."""
    text = " ".join(str(value or "").split()).casefold()
    return unicodedata.normalize("NFKC", text)
