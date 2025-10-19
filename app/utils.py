def normalize_email(email: str) -> str:
    """Normaliza correos minúsculas sin espacios."""
    return (email or "").strip().lower()


__all__ = ["normalize_email"]
