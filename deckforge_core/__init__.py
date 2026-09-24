"""DeckForge core library.

Learns presentation formats from real .pptx decks and renders new decks that
look human-made. This package is UI-free: CLI and GUI are thin interfaces on
top of ``deckforge_core``.
"""

from deckforge_core.version import __version__

__all__ = ["__version__"]
