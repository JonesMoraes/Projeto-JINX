"""gui/style.py — the JINX "Aurora Glass" look: type, colour mixing, shapes.

Everything visual that more than one panel needs lives here, so the HUD has
one voice instead of forty slightly different ones.

The language is futuristic but quiet, following Apple's design cues: hairline
(1px) borders, generous soft radii, low-contrast glass surfaces and a single
luminous accent. Shapes come from `rounded_rect` / `glass_panel`; buttons from
`btn_css`. Nothing paints hard chamfers or thick lit edges any more.

Type. No font files ship with the app, and none are downloaded: each role
names a list of families and Qt takes the first one the system has. Windows
has Bahnschrift, a DIN-style face that suits a HUD; macOS and Linux fall
through to their own sans. Numbers use a monospace so they do not jitter
while they change.

Colour. Stylesheets only ever use the palette's own hex values, because the
live re-theme (theme.retheme_all_widgets) works by replacing those exact
strings. Anything mixed or translucent is painted, and painting reads the
palette at paint time, so it re-themes for free.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QFont, QPainterPath, QPolygonF

from gui.theme import C

DISPLAY_FAMILIES = ["SF Pro Display", "-apple-system", "Segoe UI Variable Display",
                    "Segoe UI", "Helvetica Neue", "Inter", "Noto Sans",
                    "DejaVu Sans"]
MONO_FAMILIES = ["SF Mono", "Cascadia Mono", "Consolas", "Menlo",
                 "DejaVu Sans Mono", "Courier New"]
DISPLAY_CSS = ("'SF Pro Display', -apple-system, 'Segoe UI Variable Display', "
               "'Segoe UI', 'Helvetica Neue', 'Inter', 'Noto Sans', "
               "'DejaVu Sans', sans-serif")
MONO_CSS = "'SF Mono', 'Cascadia Mono', 'Consolas', 'Menlo', 'DejaVu Sans Mono', monospace"

# Apple-style soft radii. Everything in the window rounds with one of these;
# a hairline (1px) border is the only ornament a surface gets.
RADIUS_S  = 8    # chips, small buttons, progress chunks
RADIUS_M  = 12   # inputs, rows, ordinary panels
RADIUS_L  = 16   # cards, drawers, content panel
RADIUS_XL = 20   # dialogs and hero surfaces


def _apply_weight(f: QFont, weight) -> None:
    if weight is None:
        return
    try:
        if int(getattr(weight, "value", weight)) < 0:
            return
    except (TypeError, ValueError):
        return
    f.setWeight(weight)


def hud_font(size: float, weight=None, italic: bool = False) -> QFont:
    """The display face at a point size — the drop-in for the old
    QFont("Courier New", size, weight). One point larger, because Courier
    New's letters are wide and light and the same size reads bigger."""
    f = QFont()
    f.setFamilies(DISPLAY_FAMILIES)
    f.setPointSizeF(float(size) + 1.0)
    _apply_weight(f, weight)
    f.setItalic(bool(italic))
    return f


def mono_font(size: float, weight=None) -> QFont:
    """A monospace at a point size, for keys, codes and columns of figures."""
    f = QFont()
    f.setFamilies(MONO_FAMILIES)
    f.setPointSizeF(float(size))
    _apply_weight(f, weight)
    return f


def px_font(px: float, weight=QFont.Weight.Normal, mono: bool = False,
            spacing: float = 0.0) -> QFont:
    """A face at a pixel size, for painted widgets that lay text out by pixel."""
    f = QFont()
    f.setFamilies(MONO_FAMILIES if mono else DISPLAY_FAMILIES)
    f.setPixelSize(max(1, int(px)))
    _apply_weight(f, weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, float(spacing))
    return f


def blend(col, a: float, base=None) -> QColor:
    """`col` mixed onto the background (or `base`) by `a` — opaque, so it is
    drawn on the raster engine's fast path."""
    col, bg = QColor(col), QColor(base if base is not None else C.BG)
    k = max(0.0, min(1.0, float(a)))
    return QColor(int(bg.red() + (col.red() - bg.red()) * k),
                  int(bg.green() + (col.green() - bg.green()) * k),
                  int(bg.blue() + (col.blue() - bg.blue()) * k))


def with_alpha(col, a: float) -> QColor:
    c = QColor(col)
    c.setAlphaF(max(0.0, min(1.0, float(a))))
    return c


def chamfer(r: QRectF, cut: float, corners=("tl", "br")) -> QPolygonF:
    """Legacy hard-cut polygon. Kept only so old imports keep working; the
    Aurora Glass redesign draws every surface with `rounded_rect` instead."""
    x0, y0, x1, y1 = r.left(), r.top(), r.right(), r.bottom()
    pts = [QPointF(x0 + cut, y0)] if "tl" in corners else [QPointF(x0, y0)]
    pts += ([QPointF(x1 - cut, y0), QPointF(x1, y0 + cut)] if "tr" in corners
            else [QPointF(x1, y0)])
    pts += ([QPointF(x1, y1 - cut), QPointF(x1 - cut, y1)] if "br" in corners
            else [QPointF(x1, y1)])
    pts += ([QPointF(x0 + cut, y1), QPointF(x0, y1 - cut)] if "bl" in corners
            else [QPointF(x0, y1)])
    if "tl" in corners:
        pts.append(QPointF(x0, y0 + cut))
    return QPolygonF(pts)


def rounded_rect(r: QRectF, radius: float = RADIUS_M) -> QPainterPath:
    """The one shape language of the app: a softly rounded rectangle.
    Painted widgets use this instead of the old 45° chamfers."""
    path = QPainterPath()
    path.addRoundedRect(r, float(radius), float(radius))
    return path


def glass_panel(p, r: QRectF, radius: float = RADIUS_M, *, glow: float = 0.0,
                fill_top: float = 0.05, fill_bottom: float = 0.02):
    """Paint an Apple-style glass surface: faint vertical tint, a hairline
    1px border and — when `glow` > 0 — a slightly brighter edge, e.g. focus.

    Reads the palette at paint time, so the live re-theme repaints it free.
    Callers must have antialiasing on and should end the painter afterwards
    (this leaves NoBrush + a fresh pen set)."""
    path = rounded_rect(r, radius)
    p.setBrush(_surface_gradient(r, fill_top, fill_bottom))
    edge = C.PRI if glow > 0.35 else C.BORDER
    p.setPen(_hairline(edge, 0.45 + 0.5 * glow))
    p.drawPath(path)


def _surface_gradient(r: QRectF, top: float, bottom: float):
    from PyQt6.QtGui import QLinearGradient
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0.0, blend(C.PRI, top))
    g.setColorAt(1.0, blend(C.PRI, bottom))
    return g


def _hairline(col_hex: str, a: float) -> QColor:
    """A 1px border colour: the palette colour at low alpha — quiet edges."""
    return with_alpha(col_hex, max(0.0, min(1.0, a)))


def btn_css(kind: str = "dim", align: str = "left") -> str:
    """Stylesheet for a drawer/panel button — soft pill, hairline border.

    kind: "primary" (the main action), "dim" (ordinary), "on" / "off" (a switch),
    "choice" (one of two equal options — neither reads as disabled)."""
    pad = "padding: 0 12px;" if align == "left" else "padding: 0 8px;"
    base = (f"text-align: {align}; {pad} border-width: 1px; "
            f"border-radius: {RADIUS_S}px;")
    if kind == "primary":
        return f"""
            QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; {base} }}
            QPushButton:hover {{ border-color: {C.PRI}; color: {C.WHITE}; }}
            QPushButton:disabled {{ color: {C.TEXT_DIM}; border-color: {C.BORDER}; }}"""
    if kind == "on":
        return f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.GREEN};
                border: 1px solid {C.GREEN_D}; {base} }}
            QPushButton:hover {{ border-color: {C.GREEN}; }}
            QPushButton:disabled {{ color: {C.TEXT_DIM}; border-color: {C.BORDER}; }}"""
    if kind == "choice":
        return f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.PRI};
                border: 1px solid {C.BORDER_A}; {base} }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}"""
    # "dim" and "off"
    return f"""
        QPushButton {{ background: {C.PANEL}; color: {C.TEXT_MED if kind == 'dim' else C.TEXT_DIM};
            border: 1px solid {C.BORDER}; {base} }}
        QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}
        QPushButton:disabled {{ color: {C.TEXT_DIM}; border-color: {C.BORDER}; }}"""


def scroll_css() -> str:
    return f"""
        QScrollBar:vertical {{ background: transparent; width: 6px; border: none; margin: 2px 0; }}
        QScrollBar::handle:vertical {{ background: {C.BORDER_B}; min-height: 20px; border-radius: 3px; }}
        QScrollBar::handle:vertical:hover {{ background: {C.PRI_DIM}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QScrollBar:horizontal {{ height: 0; }}"""
