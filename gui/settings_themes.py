"""Shared JINX visual themes with an independently persisted HUD accent."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SettingsTheme:
    name: str
    description: str
    bg: str
    panel: str
    field: str
    text: str
    muted: str
    accent: str
    border: str
    selected: str
    radius: int


DEFAULT_SETTINGS_THEME = 'cyber_hud'
SETTINGS_THEMES = {
    'minimal_light': SettingsTheme('Minimal Light', 'Claro, direto e essencial.',
        '#f4f7fd', '#ffffff', '#f8faff', '#15213a', '#64738b', '#1474ff', '#d5dfec', '#deebff', 16),
    'nature_ui': SettingsTheme('Nature UI', 'Tons naturais e formas suaves.',
        '#f7ebd8', '#fffaf1', '#fff9ee', '#30251c', '#726952', '#607c36', '#cbbb9e', '#dce5c5', 22),
    'titanium_dark': SettingsTheme('Titanium Dark', 'Grafite, precisão e laranja.',
        '#090a0b', '#202122', '#171819', '#f6f6f6', '#b9bbbd', '#ff9900', '#515357', '#382407', 9),
    'cyber_hud': SettingsTheme('Cyber HUD', 'Ciano e a identidade futurista da JINX.',
        '#07121d', '#0d2030', '#091925', '#e1f6ff', '#9ab9cb', '#51d8ff', '#284a60', '#123a50', 6),
    'neon_glass': SettingsTheme('Neon Glass', 'Violeta, magenta e luz.',
        '#100b2b', '#31235a', '#251c53', '#f5f2ff', '#c7b9e6', '#d54dff', '#6e61aa', '#5c328b', 20),
}


def settings_theme_id(value):
    return value if isinstance(value, str) and value in SETTINGS_THEMES else DEFAULT_SETTINGS_THEME


def resolved_settings_theme(value):
    """Cyber HUD inherits the actual, possibly customized, JINX palette.

    Other four themes intentionally remain independent user choices.
    Reading the live palette here (instead of persisting a second color) keeps
    the default settings window visually consistent with the HUD.
    """
    key = settings_theme_id(value)
    if key != DEFAULT_SETTINGS_THEME:
        return SETTINGS_THEMES[key]
    from gui.theme import C
    return SettingsTheme('Cyber HUD', 'Aparência atual da interface JINX.',
        C.BG, C.PANEL, C.DARK, C.WHITE, C.TEXT_MED,
        C.PRI, C.BORDER_B, C.PRI_GHO, 6)


def apply_settings_theme_palette(value, ui_color=None):
    """Apply a selected visual theme to the shared JINX palette.

    The caller re-themes existing widgets with the returned before/after
    snapshots. Cyber HUD deliberately restores the user's independent accent.
    """
    from gui.theme import C, DEFAULT_UI_COLOR, apply_ui_accent, current_palette, current_ui_color

    key = settings_theme_id(value)
    before = current_palette()
    if key == DEFAULT_SETTINGS_THEME:
        accent = ui_color or current_ui_color() or DEFAULT_UI_COLOR
        if not apply_ui_accent(accent):
            apply_ui_accent(DEFAULT_UI_COLOR)
    else:
        theme = SETTINGS_THEMES[key]
        palette = {
            'BG': theme.bg,
            'PANEL': theme.panel,
            'PANEL2': theme.panel,
            'BORDER': theme.border,
            'BORDER_B': theme.border,
            'BORDER_A': theme.border,
            'PRI': theme.accent,
            'PRI_DIM': theme.muted,
            'PRI_GHO': theme.selected,
            'TEXT': theme.accent,
            'TEXT_DIM': theme.muted,
            'TEXT_MED': theme.muted,
            'WHITE': theme.text,
            'DARK': theme.field,
            'BAR_BG': theme.panel,
        }
        for name, color in palette.items():
            setattr(C, name, color)
    return before, current_palette()
