"""Settings-only themes. The HUD keeps its existing accent and visual choice."""
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
