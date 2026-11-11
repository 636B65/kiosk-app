def money(value) -> float:
    """Round an amount to cents; every service formats money the same way."""
    return round(float(value or 0.0), 2)
