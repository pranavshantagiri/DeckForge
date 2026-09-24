"""PowerPoint theme/master generation (Phase 1G).

Public API: brief -> :class:`StyleProfile` (generator), WCAG colour helpers
(contrast), safe font stacks (fonts), and PowerPoint theme XML application
(theme_builder).
"""

from deckforge_core.theme.contrast import (  # noqa: F401
    accessible_text_colors,
    contrast_ratio,
    is_pass,
    relative_luminance,
)
from deckforge_core.theme.fonts import (  # noqa: F401
    FONT_NAMES,
    SAFE_FONTS,
    font_kind,
    look_contrast,
    pair_for_brief,
)
from deckforge_core.theme.generator import (  # noqa: F401
    darken_hex,
    hex_to_hls,
    hls_to_hex,
    palette_from_brief,
    shade_hex,
    style_from_brief,
)
from deckforge_core.theme.theme_builder import (  # noqa: F401
    THEME_XML_TEMPLATE,
    apply_theme,
    set_theme,
)

__all__ = [
    "accessible_text_colors",
    "contrast_ratio",
    "is_pass",
    "relative_luminance",
    "FONT_NAMES",
    "SAFE_FONTS",
    "font_kind",
    "look_contrast",
    "pair_for_brief",
    "darken_hex",
    "hls_to_hex",
    "hex_to_hls",
    "palette_from_brief",
    "shade_hex",
    "style_from_brief",
    "THEME_XML_TEMPLATE",
    "apply_theme",
    "set_theme",
]
