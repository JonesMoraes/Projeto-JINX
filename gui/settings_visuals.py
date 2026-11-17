"""Five distinctive native Qt skins inspired by the JINX reference images.

These are *real* controls, not a static screenshot. All live settings and
embedded runtime forms retain their existing behaviour and persistence.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Skin:
    background: str
    background_end: str
    header: str
    surface: str
    surface_end: str
    field: str
    rail: str
    border: str
    strong_border: str
    accent: str
    accent_secondary: str
    text: str
    muted: str
    selected: str
    radius: int


def visual_skin(theme_id, t):
    if theme_id == 'titanium_dark':
        return Skin('#090a0b', '#191919', '#0f1011',
                    '#202122', '#121314', '#171819', '#0b0c0d',
                    '#515357', '#ff9a00', '#ff9900', '#ffc064',
                    '#f6f6f6', '#b9bbbd', '#382407', 9)
    if theme_id == 'nature_ui':
        return Skin('#f7ebd8', '#e8ddc8', '#faf2e6',
                    '#fffaf1', '#f0e5d5', '#fff9ee', '#f8eedc',
                    '#cbbb9e', '#6c8745', '#607c36', '#bc7044',
                    '#30251c', '#726952', '#dce5c5', 22)
    if theme_id == 'neon_glass':
        return Skin('#100b2b', '#13275c', '#1d1547',
                    '#31235a', '#172b5f', '#251c53', '#25174f',
                    '#6e61aa', '#e85aff', '#d54dff', '#2bd4ff',
                    '#f5f2ff', '#c7b9e6', '#5c328b', 20)
    if theme_id == 'minimal_light':
        return Skin('#f4f7fd', '#eaf1fb', '#edf4ff',
                    '#ffffff', '#f6f9ff', '#f8faff', '#eef4fd',
                    '#d5dfec', '#3583ff', '#1474ff', '#64a9ff',
                    '#15213a', '#64738b', '#deebff', 16)
    # The Cyber skin tracks C through resolved_settings_theme, including
    # any custom HUD accent selected by the user.
    return Skin(t.bg, t.panel, t.panel, t.panel, t.field, t.field,
                t.bg, t.border, t.accent, t.accent, t.muted,
                t.text, t.muted, t.selected, 8)


def _gradient(a, b, *, diagonal=False):
    x2 = 1 if diagonal else 0
    return ('qlineargradient(x1:0, y1:0, x2:' + str(x2)
            + ', y2:1, stop:0 ' + a + ', stop:1 ' + b + ')')


def settings_stylesheet(theme_id, theme, font_css):
    s = visual_skin(theme_id, theme)
    bg = _gradient(s.background, s.background_end, diagonal=True)
    card = _gradient(s.surface, s.surface_end, diagonal=theme_id in ('neon_glass', 'nature_ui'))
    selected = (_gradient(s.selected, s.surface_end, diagonal=True)
                if theme_id == 'neon_glass' else s.selected)
    is_light = theme_id in ('minimal_light', 'nature_ui')
    primary_text = '#ffffff' if theme_id == 'neon_glass' else ('#10151b' if theme_id == 'titanium_dark' else s.text)
    accent_button = theme_id in ('titanium_dark', 'nature_ui', 'minimal_light')
    primary_bg = (s.accent_secondary if theme_id == 'nature_ui' else s.accent)
    return f"""
        QDialog#SettingsCentral {{
            background: {bg};
            color: {s.text};
            font-family: {font_css};
        }}
        QWidget {{ color: {s.text}; font-family: {font_css}; }}
        QLabel {{ background: transparent; }}
        QWidget#SettingsHeader {{
            background: {_gradient(s.header, s.background_end, diagonal=True)};
            border: 1px solid {s.border};
            border-radius: {min(s.radius, 7)}px;
        }}
        QLabel#SettingsBrand {{
            color: {s.text};
            font-weight: 700;
        }}
        QLabel#SettingsKicker, QLabel#SettingsSubtitle, QLabel#SettingsHint {{
            color: {s.muted};
        }}
        QLabel#SettingsHeading {{ color: {s.text}; font-weight: 700; }}
        QPushButton#SettingsWindowClose {{
            background: transparent;
            color: {s.muted};
            border: 1px solid transparent;
            border-radius: 3px;
            padding: 0;
            font-weight: 700;
        }}
        QPushButton#SettingsWindowClose:hover {{
            color: {s.text};
            background: #7c2430;
            border-color: #d24a5b;
        }}
        QWidget#SettingsPage, QScrollArea, QScrollArea > QWidget,
        QStackedWidget {{ background: transparent; border: none; }}
        QWidget#SettingsHome {{ background: transparent; }}
        QPushButton#SettingsHomeTile {{
            background: {card};
            color: {s.text};
            border: 1px solid {s.border};
            border-radius: {min(s.radius, 12)}px;
            text-align: left;
            padding: 8px 12px;
            min-height: 86px;
        }}
        QPushButton#SettingsHomeTile:hover {{
            background: {selected};
            border: 1px solid {s.accent};
        }}
        QLabel#SettingsHomeTileTitle {{ color: {s.text}; font-weight: 700; }}
        QLabel#SettingsHomeTileDescription {{ color: {s.muted}; }}
        QListWidget#SettingsNavigation {{
            background: {_gradient(s.rail, s.background_end)};
            color: {s.text};
            border: 1px solid {s.border};
            border-radius: {s.radius}px;
            padding: 6px 5px;
            outline: none;
        }}
        QListWidget#SettingsNavigation::item {{
            padding: 9px 10px;
            border-radius: {min(s.radius, 12)}px;
            margin-bottom: 3px;
            color: {s.text};
        }}
        QListWidget#SettingsNavigation::item:hover {{
            background: {s.surface};
        }}
        QListWidget#SettingsNavigation::item:selected {{
            background: {selected};
            border: 1px solid {s.strong_border};
            color: {s.accent if is_light else s.text};
        }}
        QListWidget#SettingsPluginList {{
            background: {s.rail};
            color: {s.text};
            border: 1px solid {s.border};
            border-radius: {min(s.radius, 10)}px;
            padding: 5px;
            outline: none;
        }}
        QListWidget#SettingsPluginList::item {{
            padding: 8px 9px;
            margin-bottom: 2px;
            border-radius: {min(s.radius, 8)}px;
        }}
        QListWidget#SettingsPluginList::item:hover {{ background: {s.surface}; }}
        QListWidget#SettingsPluginList::item:selected {{
            background: {selected};
            border: 1px solid {s.strong_border};
        }}
        QWidget#SettingsCard {{
            background: {card};
            border: 1px solid {s.border};
            border-radius: {s.radius}px;
        }}
        QLabel#SettingsCardTitle {{
            color: {s.text};
            font-weight: 700;
            border: none;
            background: transparent;
        }}
        QWidget#SettingsFooter {{
            background: {s.header};
            border: 1px solid {s.border};
            border-radius: {s.radius}px;
        }}
        QPushButton {{
            background: {s.surface};
            color: {s.text};
            border: 1px solid {s.border};
            border-radius: {min(s.radius, 13)}px;
            padding: 4px 10px;
            min-height: 18px;
        }}
        QPushButton:hover, QPushButton:focus {{
            border: 1px solid {s.accent};
            background: {s.selected};
        }}
        QPushButton:checked {{
            background: {selected};
            color: {s.text};
            border: 2px solid {s.strong_border};
        }}
        QPushButton#SettingsThemeCard {{
            background: {card};
            border: 1px solid {s.border};
            border-radius: {s.radius}px;
        }}
        QPushButton#SettingsThemeCard:checked {{
            background: {selected};
            border: 2px solid {s.accent};
        }}
        QPushButton#SettingsPrimary {{
            background: {primary_bg};
            color: {primary_text if accent_button else s.background};
            border: 1px solid {s.strong_border};
            font-weight: 700;
            padding: 5px 14px;
        }}
        QPushButton#SettingsPrimary:hover {{
            background: {s.accent_secondary};
            color: {s.background if not is_light else '#ffffff'};
        }}
        QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox,
        QDoubleSpinBox, QTableWidget {{
            background: {s.field};
            color: {s.text};
            border: 1px solid {s.border};
            border-radius: {min(s.radius, 12)}px;
            padding: 5px 8px;
            selection-background-color: {s.accent};
        }}
        QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
            border: 1px solid {s.accent};
        }}
        QComboBox QAbstractItemView {{
            background: {s.surface}; color: {s.text};
            selection-background-color: {s.selected};
            border: 1px solid {s.border};
        }}
        QCheckBox {{ color: {s.text}; spacing: 9px; }}
        QCheckBox::indicator {{
            width: 18px; height: 18px;
            border: 1px solid {s.border};
            border-radius: 6px;
            background: {s.field};
        }}
        QCheckBox::indicator:checked {{
            background: {s.accent};
            border: 1px solid {s.strong_border};
        }}
        QProgressBar {{
            background: {s.field};
            border: 1px solid {s.border};
            border-radius: 5px;
        }}
        QProgressBar::chunk {{ background: {s.accent}; border-radius: 5px; }}
        QScrollBar:vertical {{
            background: {s.background};
            width: 9px; border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {s.border};
            min-height: 28px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {s.accent}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
    """
