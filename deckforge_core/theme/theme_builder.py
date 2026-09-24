"""PowerPoint (drawingML) theme XML generation and application to a pptx.

The theme part lives at ``ppt/theme/theme1.xml`` as a plain binary ``Part`` in
python-pptx, so rewriting its ``_blob`` is sufficient — the part graph and every
``themeReference`` rId in the master/layouts keeps resolving.
"""

from __future__ import annotations

import xml.sax.saxutils as sax

from pptx import Presentation

from deckforge_core.schemas.pack import StyleProfile
from deckforge_core.theme.generator import shade_hex

_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Standard minimal fmtScheme (fillStyleLst, lnStyleLst, effectStyleLst,
# bgFillStyleLst, exactly 3 children each) per the OOXML reference theme.
_FMT_SCHEME = """<a:fmtScheme name="DeckForge">
  <a:fillStyleLst>
    <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
    <a:solidFill><a:schemeClr val="phClr"><a:tint val="50000"/></a:schemeClr></a:solidFill>
    <a:solidFill><a:schemeClr val="phClr"><a:shade val="50000"/></a:schemeClr></a:solidFill>
  </a:fillStyleLst>
  <a:lnStyleLst>
    <a:ln w="9525" cap="flat" cmpd="sng" algn="ctr">
      <a:solidFill><a:schemeClr val="phClr"><a:shade val="95000"/></a:schemeClr></a:solidFill>
      <a:prstDash val="solid"/>
    </a:ln>
    <a:ln w="25400" cap="flat" cmpd="sng" algn="ctr">
      <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      <a:prstDash val="solid"/>
    </a:ln>
    <a:ln w="38100" cap="flat" cmpd="sng" algn="ctr">
      <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      <a:prstDash val="solid"/>
    </a:ln>
  </a:lnStyleLst>
  <a:effectStyleLst>
    <a:effectStyle><a:effectLst>
      <a:outerShdw blurRad="40000" dist="20000" dir="5400000" rotWithShape="0">
        <a:srgbClr val="000000"><a:alpha val="38000"/></a:srgbClr>
      </a:outerShdw>
    </a:effectLst></a:effectStyle>
    <a:effectStyle><a:effectLst>
      <a:outerShdw blurRad="40000" dist="23000" dir="5400000" rotWithShape="0">
        <a:srgbClr val="000000"><a:alpha val="35000"/></a:srgbClr>
      </a:outerShdw>
    </a:effectLst></a:effectStyle>
    <a:effectStyle><a:effectLst>
      <a:outerShdw blurRad="40000" dist="23000" dir="5400000" rotWithShape="0">
        <a:srgbClr val="000000"><a:alpha val="35000"/></a:srgbClr>
      </a:outerShdw>
    </a:effectLst></a:effectStyle>
  </a:effectStyleLst>
  <a:bgFillStyleLst>
    <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
    <a:gradFill rotWithShape="1">
      <a:gsLst>
        <a:gs pos="0"><a:schemeClr val="phClr"><a:tint val="50000"/><a:satMod val="300000"/></a:schemeClr></a:gs>
        <a:gs pos="100000"><a:schemeClr val="phClr"><a:tint val="15000"/><a:satMod val="350000"/></a:schemeClr></a:gs>
      </a:gsLst>
      <a:lin ang="16200000" scaled="1"/>
    </a:gradFill>
    <a:gradFill rotWithShape="1">
      <a:gsLst>
        <a:gs pos="0"><a:schemeClr val="phClr"><a:tint val="100000"/><a:satMod val="130000"/></a:schemeClr></a:gs>
        <a:gs pos="100000"><a:schemeClr val="phClr"><a:tint val="50000"/><a:satMod val="350000"/></a:schemeClr></a:gs>
      </a:gsLst>
      <a:lin ang="16200000" scaled="0"/>
    </a:gradFill>
  </a:bgFillStyleLst>
</a:fmtScheme>"""


def _esc(value: str) -> str:
    return sax.escape(value, {"'": "&apos;", '"': "&quot;"})


def _accent_hexes(style: StyleProfile) -> list[str]:
    """Fill accent1..accent6 from the palette, accent roles first, cycling."""
    palette = style.palette
    primary: list[str] = []
    for role in ("accent1", "accent2", "accent3"):
        if palette.has(role):
            primary.append(palette.hex(role))
    rest = [c.hex for c in palette.colors if c.hex not in primary]
    pool = primary + rest
    return [pool[i % len(pool)] for i in range(6)]


def THEME_XML_TEMPLATE(style: StyleProfile) -> str:
    """Return a valid drawingML ``a:theme`` XML string for ``style``."""
    palette = style.palette
    text = palette.hex("text")
    bg = palette.hex("bg")
    accent1 = palette.hex("accent1")
    accent2 = palette.hex("accent2")
    dk2 = shade_hex(accent2, 0.45)
    lt2 = palette.hex("neutral1") if palette.has("neutral1") else "#F2F2EE"

    accents = _accent_hexes(style)
    heading = _esc(style.fonts.heading)
    body = _esc(style.fonts.body)

    clr_entries = "".join(
        _clr_entry(tag, hex_color)
        for tag, hex_color in zip(("accent1", "accent2", "accent3", "accent4", "accent5", "accent6"), accents)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="{_A_NS}" xmlns:r="{_R_NS}" name="DeckForge Theme">
  <a:themeElements>
    <a:clrScheme name="DeckForge">
      <a:dk1><a:sysClr val="windowText" lastClr="{text[1:]}"/></a:dk1>
      <a:lt1><a:sysClr val="window" lastClr="{bg[1:]}"/></a:lt1>
      <a:dk2><a:srgbClr val="{dk2[1:]}"/></a:dk2>
      <a:lt2><a:srgbClr val="{lt2[1:]}"/></a:lt2>
      {clr_entries}
      <a:hlink><a:srgbClr val="{accent1[1:]}"/></a:hlink>
      <a:folHlink><a:srgbClr val="{accent2[1:]}"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="DeckForge">
      <a:majorFont>
        <a:latin typeface="{heading}"/>
        <a:ea typeface=""/>
        <a:cs typeface=""/>
        <a:font script="Latn" typeface="{heading}"/>
      </a:majorFont>
      <a:minorFont>
        <a:latin typeface="{body}"/>
        <a:ea typeface=""/>
        <a:cs typeface=""/>
        <a:font script="Latn" typeface="{body}"/>
      </a:minorFont>
    </a:fontScheme>
    {_FMT_SCHEME}
  </a:themeElements>
</a:theme>"""


def _clr_entry(tag: str, hex_color: str) -> str:
    return f'<a:{tag}><a:srgbClr val="{hex_color[1:]}"/></a:{tag}>'


def set_theme(prs: Presentation, style: StyleProfile) -> list[str]:
    """Replace the ``theme/theme1.xml`` part blob; return warning messages."""
    warnings: list[str] = []
    theme_xml = THEME_XML_TEMPLATE(style)
    blob = theme_xml.encode("utf-8")
    package = getattr(getattr(prs, "part", None), "package", None)
    if package is None:
        return ["Presentation has no package; theme not applied."]

    for part in package.iter_parts():
        partname = getattr(part, "partname", None)
        partname_str = str(partname) if partname is not None else ""
        content_type = getattr(part, "content_type", "") or ""
        if partname_str.endswith("theme/theme1.xml") and "theme" in content_type:
            if hasattr(part, "_blob"):
                part._blob = blob
            else:
                setter = getattr(type(part), "blob", None)
                if isinstance(setter, property) and setter.fset is not None:
                    part.blob = blob
                else:
                    warnings.append(f"theme part {partname_str!r} has no writable blob; skipped.")
                    continue
            return warnings
    warnings.append("no theme/theme1.xml part found; theme not applied.")
    return warnings


def apply_theme(prs: Presentation, style: StyleProfile) -> list[str]:
    """``set_theme`` plus a resolution check of the first slide master."""
    warnings = set_theme(prs, style)
    masters = getattr(prs, "slide_masters", None)
    if not masters:
        return warnings + ["Presentation has no slide masters; theme reference not checked."]

    master = masters[0]
    rels = getattr(getattr(master, "part", None), "rels", None)
    if rels is None:
        return warnings + ["slide master has no rels; theme reference not checked."]
    targets = {str(getattr(r.target_part, "partname", "")) for r in rels.values()}
    if not any(p.endswith("theme/theme1.xml") for p in targets):
        warnings.append("slide master does not reference theme/theme1.xml.")
    return warnings
