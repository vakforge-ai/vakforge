"""Locale pack registry. Importing this package registers every shipped pack."""

from vakforge.locales import (  # noqa: F401  (registers packs on import)
    en,
    en_gb,
    en_in,
    en_us,
    hi_latn_in,
)
from vakforge.locales.base import LocalePack, get_pack, list_packs, register

__all__ = ["LocalePack", "get_pack", "list_packs", "register"]
