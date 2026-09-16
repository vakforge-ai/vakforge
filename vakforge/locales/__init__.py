"""Locale pack registry. Importing this package registers every shipped pack."""

from vakforge.locales import en  # noqa: F401  (registers packs on import)
from vakforge.locales.base import LocalePack, get_pack, list_packs, register

__all__ = ["LocalePack", "get_pack", "list_packs", "register"]
