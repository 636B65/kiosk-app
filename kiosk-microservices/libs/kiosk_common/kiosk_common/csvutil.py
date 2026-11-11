def csv_safe(value):
    """Neutralise spreadsheet formulas (CSV injection) in text cells."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value
