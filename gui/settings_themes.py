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
        '#f3f6fb', '#ffffff', '#f8faff', '#18273d', '#52627b', '#245bd8', '#ccd6e5', '#e5edff', 8),
    'nature_ui': SettingsTheme('Nature UI', 'Tons naturais e formas suaves.',
        '#f2ecdf', '#fcf8ee', '#f5efdf', '#293d30', '#626954', '#36704b', '#d4d1b9', '#dfe9d6', 18),
    'titanium_dark': SettingsTheme('Titanium Dark', 'Grafite, precisão e laranja.',
        '#17191c', '#24272c', '#1c1f23', '#f0f1f3', '#aeb4be', '#ffad60', '#454b54', '#3d3026', 2),
    'cyber_hud': SettingsTheme('Cyber HUD', 'Ciano e a identidade futurista da JINX.',
        '#07121d', '#0d2030', '#091925', '#e1f6ff', '#9ab9cb', '#51d8ff', '#284a60', '#123a50', 6),
    'neon_glass': SettingsTheme('Neon Glass', 'Violeta, magenta e luz.',
        '#19132e', '#29203f', '#211a36', '#f4edff', '#c0afd9', '#e59bff', '#634779', '#48305f', 16),
}


def settings_theme_id(value):
    return value if isinstance(value, str) and value in SETTINGS_THEMES else DEFAULT_SETTINGS_THEME
