"""Single Qt settings window: searchable navigation and existing runtime forms.

Forms are created on demand on the Qt thread. Each form retains its existing
save/reconnect contract; theme changes only write the settings_theme key.
"""
import os
import re
import unicodedata
from weakref import WeakKeyDictionary

from PyQt6.QtCore import QEvent, Qt, QTimer, QRectF
from PyQt6.QtGui import (QColor, QFont, QPainter, QPen, QPalette, QLinearGradient, QRadialGradient, QBrush,
                         QPainterPath)
from PyQt6.QtWidgets import (QApplication, QBoxLayout, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from gui.style import hud_font, DISPLAY_FAMILIES, DISPLAY_CSS
from gui.settings_visuals import settings_stylesheet, visual_skin
from gui.theme import C, retheme_all_widgets
from gui.settings_controls import ToggleSwitch, ToggleRow
from gui.settings_themes import (SETTINGS_THEMES, DEFAULT_SETTINGS_THEME,
                                 settings_theme_id, resolved_settings_theme,
                                 apply_settings_theme_palette)
from memory import config_manager as config


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.casefold())
                   if unicodedata.category(c) != 'Mn')


# Decorative emoji are removed only from displayed settings labels, never
# from editable values, plugin IDs, saved settings, or secret fields.
_EMOJI = re.compile(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0E\uFE0F\u200D\u20E3]')


def clean_settings_label(value):
    if not value:
        return value
    cleaned = _EMOJI.sub('', value)
    cleaned = re.sub(r'^[\s\u25C8\u25B8\u25B6\u25CF\u25C6]+', '', cleaned)
    return re.sub(r' {2,}', ' ', cleaned).strip()


# Search terms describe controls, not just category titles.
CATEGORIES = (
    ('general', 'Perfil', 'Nome e forma de tratamento da JINX.', 'nome usuario assistente identidade'),
    ('appearance', 'Aparência', 'Tema, ícone e aparência do HUD.', 'tema cyber minimal nature titanium neon hud visual'),
    ('audio', 'Voz e áudio', 'Voz da JINX, microfone e saída de som.', 'volume dispositivos teste entrada saida gemini previa'),
    ('ai', 'Serviços de IA', 'Escolha como a JINX escuta, responde e fala.', 'modelo stt llm tts api chave token ollama pipeline provedores'),
    ('memory', 'Memória', 'Revise e gerencie o que a JINX lembra.', 'esquecer excluir dados lembrancas'),
    ('learned_rules', 'Preferências da IA', 'Ajuste o estilo e as regras de resposta.',
     'learned rules regras preferencias comportamento estilo fluxo aprovar exportar importar backup'),
    ('automation', 'Comandos e rotinas', 'Agenda, ativação e controles por voz.', 'eventos calendario resumo gestos camera palavra de ativacao wake push to talk pressionar falar comando'),
    ('integrations', 'Integrações e contas', 'Conecte serviços e configure seus plugins.', 'plugins spotify discord google trello contas'),
    ('security', 'Acesso remoto', 'Acesso seguro do celular ao JINX.', 'celular chave acesso token remoto'),
    ('system', 'Inicialização e manutenção', 'Atalhos, início com o Windows e plugins.', 'atalho windows iniciar carregados plugins sistema manutenção'),
)

NAV_GROUPS = (
    ('COMECE AQUI', ('home',)),
    ('PERSONALIZAÇÃO', ('general', 'appearance', 'audio')),
    ('INTELIGÊNCIA', ('ai', 'memory', 'learned_rules')),
    ('AUTOMAÇÃO', ('automation', 'integrations')),
    ('SISTEMA', ('security', 'system')),
)
CATEGORY_GROUPS = {label: keys for label, keys in NAV_GROUPS}
NAV_TITLES = {
    'home': 'Início', 'general': 'Perfil', 'appearance': 'Aparência',
    'audio': 'Voz e áudio', 'ai': 'Serviços de IA', 'memory': 'Memória',
    'learned_rules': 'Regras e estilo', 'automation': 'Comandos e rotinas',
    'integrations': 'Integrações', 'security': 'Acesso remoto',
    'system': 'Inicialização',
}


class ThemePreview(QWidget):
    """Interactive theme catalog thumbnail painted natively in Qt.

    Each mini composition mirrors its reference: warm industrial dark, organic
    cream, violet neon, airy blue, or the HUD's live cyan/selected accent.
    """
    def __init__(self, theme, theme_id='', parent=None):
        super().__init__(parent)
        self.theme = theme
        self.theme_id = theme_id
        self.setFixedHeight(86)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        t = self.theme
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, w, h)
        g.setColorAt(0, QColor(t.bg))
        g.setColorAt(1, QColor(t.panel))
        p.fillRect(self.rect(), g)

        if self.theme_id == 'nature_ui':
            glow = QRadialGradient(w * 0.88, 3, h * 1.2)
            glow.setColorAt(0, QColor('#d7dcb8'))
            glow.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), QBrush(glow))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor('#9ba76f'))
            for x, y, angle in ((w-30, 11, 28), (w-48, 2, -22), (w-16, 30, -32)):
                p.save()
                p.translate(x, y)
                p.rotate(angle)
                p.drawEllipse(QRectF(-6, -13, 12, 24))
                p.restore()
        elif self.theme_id == 'neon_glass':
            glow = QRadialGradient(w * 0.78, 12, w * 0.6)
            glow.setColorAt(0, QColor(125, 50, 220, 175))
            glow.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), QBrush(glow))
        elif self.theme_id == 'titanium_dark':
            p.fillRect(0, 0, w, 3, QColor('#ff9a00'))
            p.fillRect(0, h-2, 48, 2, QColor(t.accent))
        elif self.theme_id == 'cyber_hud':
            p.setPen(QPen(QColor(t.accent), 1.2))
            p.drawLine(1, 12, 1, 1)
            p.drawLine(1, 1, 35, 1)
            p.drawLine(w - 32, h - 1, w-1, h-1)
            p.drawLine(w-1, h-1, w-1, h-13)

        radius = 9 if self.theme_id == 'minimal_light' else max(4, t.radius)
        p.setPen(QPen(QColor(t.border), 1))
        p.setBrush(QColor(t.panel))
        p.drawRoundedRect(QRectF(9, 11, 47, h-22), 7, 7)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.accent))
        p.drawRoundedRect(QRectF(16, 21, 31, 6), 3, 3)
        for ypos in (37, 49, 61):
            p.setBrush(QColor(t.muted))
            p.drawRoundedRect(QRectF(17, ypos, 22, 3), 1, 1)
        p.setPen(QPen(QColor(t.border), 1))
        p.setBrush(QColor(t.panel))
        p.drawRoundedRect(QRectF(64, 13, max(30, w-76), h-27), radius/2, radius/2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.text))
        p.drawRoundedRect(QRectF(73, 25, max(24, (w-95)*0.50), 5), 2, 2)
        p.setBrush(QColor(t.muted))
        p.drawRoundedRect(QRectF(73, 39, max(18, (w-100)*0.36), 3), 1, 1)
        p.setBrush(QColor(t.accent))
        p.drawRoundedRect(QRectF(73, 55, max(22, (w-95)*0.45), 8), 4, 4)
        p.end()


def _accent_luminance(accent):
    hexs = str(accent).lstrip('#')
    r, g, b = (int(hexs[i:i + 2], 16) for i in (0, 2, 4))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def _icon_ink(accent, mode):
    """Escolhe a tinta do icone a partir de uma cor de accent ja resolvida."""
    if mode == 'contrast':
        return QColor('#10151b') if _accent_luminance(accent) > 0.62 else QColor('#ffffff')
    return QColor(accent)


class SettingsIcon(QWidget):
    """Vector icon painted natively by QPainter — no font and no emoji.

    ``mode='accent'`` strokes the glyph in the theme accent (for badges on
    a subtle tinted tile); ``mode='contrast'`` picks white or dark ink so
    the glyph stays readable on a solid accent background.
    """
    def __init__(self, kind, dialog, mode='accent', size=20, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(size, size)
        # Cor resolvida UMA vez na construcao. O paintEvent nunca consulta
        # tema/QSS — repolir widgets durante o paint derrubava o app com
        # segfault nativo no modo offscreen (0xC0000409, sem traceback).
        accent = None
        try:
            skin = visual_skin(dialog.theme_id, resolved_settings_theme(dialog.theme_id))
            accent = skin.accent
        except Exception:
            accent = None
        if not accent:
            accent = '#67e8f9'
        self._ink = _icon_ink(accent, mode)

    def paintEvent(self, event):
        color = self._ink
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(color, 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        def seg(x1, y1, x2, y2):
            """Traca um segmento via QPainterPath. QPainter.drawLine pode
            segfaultar no Qt offscreen do Windows quando misturado com
            elipses preenchidas/antialias (ver nota no icone 'palette')."""
            path = QPainterPath()
            path.moveTo(x1, y1)
            path.lineTo(x2, y2)
            p.drawPath(path)

        k = self.kind
        if k == 'person':
            p.drawEllipse(QRectF(7, 2.5, 6, 6))
            p.drawArc(QRectF(3.5, 10.5, 13, 12), 0, 180 * 16)
        elif k == 'palette':
            # NB: um QPainter.drawLine(int, ...) logo apos elipses preenchidas
            # com antialias derruba o processo (segfault nativo no Qt offscreen
            # do Windows). Todo traco aqui usa drawPath/drawPolyline, nao
            # drawLine — testado com o repro do crash.
            p.drawEllipse(QRectF(3, 3, 14, 14))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            for x, y in ((6.5, 6.5), (11.5, 6.5), (6.5, 11.5)):
                p.drawEllipse(QRectF(x, y, 2, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(10, 10.5)
            path.lineTo(13.5, 13.5)
            p.setPen(QPen(color, 1.5))
            p.drawPath(path)
        elif k == 'mic':
            p.drawRoundedRect(QRectF(7.3, 2.5, 5.4, 9), 2.6, 2.6)
            p.drawArc(QRectF(4.5, 6, 11, 10.5), 185 * 16, 170 * 16)
            seg(10, 16, 10, 17.8)
            seg(7.4, 17.8, 12.6, 17.8)
        elif k == 'chip':
            p.drawRoundedRect(QRectF(5, 5, 10, 10), 2, 2)
            for x in (7.3, 10, 12.7):
                seg(x, 2.4, x, 5)
                seg(x, 15, x, 17.6)
        elif k == 'database':
            p.drawEllipse(QRectF(4, 2.8, 12, 4.6))
            seg(4, 5.1, 4, 15)
            seg(16, 5.1, 16, 15)
            p.drawArc(QRectF(4, 12.7, 12, 4.6), 180 * 16, 180 * 16)
            p.drawArc(QRectF(4, 8.8, 12, 4.6), 180 * 16, 180 * 16)
        elif k == 'rules':
            seg(5, 4.5, 15, 4.5)
            seg(5, 10, 15, 10)
            seg(5, 15.5, 11.5, 15.5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            for y in (3.2, 8.7, 14.2):
                p.drawEllipse(QRectF(2, y, 1.5, 1.5))
        elif k == 'clock':
            p.drawEllipse(QRectF(3, 3, 14, 14))
            seg(10, 10, 10, 5.6)
            seg(10, 10, 13.2, 11.6)
        elif k == 'plug':
            seg(7.5, 2.6, 7.5, 6)
            seg(12.5, 2.6, 12.5, 6)
            p.drawRoundedRect(QRectF(5.5, 6, 9, 6.5), 2.5, 2.5)
            p.drawArc(QRectF(6, 10.5, 8, 7), 150 * 16, 120 * 16)
            seg(13.5, 17.3, 15, 16.5)
        elif k == 'lock':
            p.drawArc(QRectF(6.2, 2.6, 7.6, 9), 0, 180 * 16)
            p.drawRoundedRect(QRectF(4, 9, 12, 8.6), 2, 2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawEllipse(QRectF(9.2, 11.6, 1.7, 1.7))
        elif k == 'power':
            p.drawArc(QRectF(3, 4, 14, 14), -40 * 16, 260 * 16)
            seg(10, 2.4, 10, 9.5)
        p.end()


class SettingsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setObjectName('SettingsCentral')
        self.setWindowTitle('JINX — Configurações')
        self.setFont(hud_font(9))
        # Drawer lateral: um terço da largura da tela, quase a altura toda.
        # Antes era 1080x740 — cobria metade da tela e duplicava a navegação
        # com os tiles do Início, o que a tornava difícil de ler.
        screen = window.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        if available is not None:
            width = max(1, min(520, max(380, available.width() // 3)))
            height = max(1, min(740, available.height() - 48))
        else:
            width, height = 455, 640
        self.setMinimumSize(min(380, width), min(420, height))
        self.resize(width, height)
        if available is not None:
            self.move(available.right() - width - 16,
                      available.top() + 24)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.theme_id = settings_theme_id(config.load_api_keys().get('settings_theme'))
        self._pages = {}
        self._embedded = []
        self._original_styles = WeakKeyDictionary()
        self._source_palettes = WeakKeyDictionary()
        self._styling = False
        self._current = 'general'
        self._drag_offset = None
        self._search_matches = None
        self._theme_buttons = {}
        self._theme_previews = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(7)
        header_host = QWidget()
        self._header_host = header_host
        header_host.setObjectName('SettingsHeader')
        header_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header_host.setCursor(Qt.CursorShape.SizeAllCursor)
        header_host.installEventFilter(self)
        header = QHBoxLayout(header_host)
        header.setContentsMargins(12, 7, 10, 7)
        header.setSpacing(8)
        self.back_btn = QPushButton('‹')
        self.back_btn.setObjectName('SettingsBack')
        self.back_btn.setAccessibleName('Voltar ao início das configurações')
        self.back_btn.setFixedSize(28, 27)
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setVisible(False)
        self.back_btn.clicked.connect(self.show_home)
        header.addWidget(self.back_btn)
        identity = QVBoxLayout()
        identity.setSpacing(0)
        brand = QLabel('JINX IA')
        brand.setObjectName('SettingsBrand')
        brand.setFont(hud_font(12, QFont.Weight.Bold))
        identity.addWidget(brand)
        kicker = QLabel('CONFIGURAÇÕES')
        kicker.setObjectName('SettingsKicker')
        kicker.setFont(hud_font(7))
        identity.addWidget(kicker)
        header.addLayout(identity)
        header.addStretch()
        self.search = QLineEdit()
        self.search.setObjectName('SettingsSearch')
        self.search.setPlaceholderText('Buscar…')
        self.search.setAccessibleName('Buscar configurações')
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(190)
        self.search.setToolTip('Buscar configurações (Ctrl+F)')
        header.addWidget(self.search)
        header_close = QPushButton('✕')
        header_close.setObjectName('SettingsWindowClose')
        header_close.setAccessibleName('Fechar configurações')
        header_close.setFixedSize(28, 27)
        header_close.clicked.connect(self.close)
        header.addWidget(header_close)
        root.addWidget(header_host)
        right = QVBoxLayout()
        self.breadcrumb = QLabel()
        self.breadcrumb.setObjectName('SettingsBreadcrumb')
        self.breadcrumb.setFont(hud_font(7))
        right.addWidget(self.breadcrumb)
        self.heading = QLabel()
        self.heading.setObjectName('SettingsHeading')
        self.heading.setFont(hud_font(17, QFont.Weight.Bold))
        self.subtitle = QLabel()
        self.subtitle.setObjectName('SettingsSubtitle')
        self.subtitle.setWordWrap(True)
        right.addWidget(self.heading)
        right.addWidget(self.subtitle)
        right.addSpacing(6)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        self.empty = QLabel('Nenhuma configuração encontrada. Tente outro termo.')
        self.empty.setWordWrap(True)
        self.stack.addWidget(self.empty)
        self._home_page = None
        root.addLayout(right, 1)
        footer_host = QWidget()
        footer_host.setObjectName('SettingsFooter')
        footer_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        footer = QHBoxLayout(footer_host)
        footer.setContentsMargins(12, 6, 12, 6)
        self.status = QLabel('Alterações salvas automaticamente. Esc volta, Ctrl+F busca.')
        self.status.setObjectName('SettingsHint')
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        close = QPushButton('Concluir')
        close.setObjectName('SettingsPrimary')
        close.setAccessibleName('Fechar configurações')
        close.setMinimumWidth(96)
        close.clicked.connect(self.close)
        footer.addWidget(close)
        root.addWidget(footer_host)
        self.search.textChanged.connect(self._search)
        self.search.returnPressed.connect(self._open_first_result)
        self._show_group('home')
        self._apply_theme()
        from PyQt6.QtGui import QKeySequence, QShortcut
        find = QShortcut(QKeySequence('Ctrl+F'), self)
        find.setContext(Qt.ShortcutContext.WindowShortcut)
        find.activated.connect(self._focus_search)
        escape = QShortcut(QKeySequence('Esc'), self)
        escape.setContext(Qt.ShortcutContext.WindowShortcut)
        escape.activated.connect(self._escape)
        QApplication.instance().installEventFilter(self)

    def _focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def _escape(self):
        """Esc desescada: limpa a busca, volta ao Início e só então fecha."""
        if self.search.text() or self._current != 'home':
            self.show_home()
        else:
            self.close()

    def _open_first_result(self):
        """Enter na busca abre a primeira área visível nos tiles."""
        for key, _title, _description, _terms in CATEGORIES:
            tile = self._home_tiles.get(key) if hasattr(self, '_home_tiles') else None
            if tile is not None and tile.isVisible():
                self.show_home()
                self.show_category(key)
                return
        self.status.setText('Nada encontrado para \"' + self.search.text() + '\".')

    def _card(self, layout, title, description=''):
        """Real responsive Qt panel; all controls keep their callbacks."""
        card = QWidget()
        card.setObjectName('SettingsCard')
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setMinimumWidth(0)
        card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        body = QVBoxLayout(card)
        body.setContentsMargins(14, 11, 14, 12)
        body.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName('SettingsCardTitle')
        heading.setFont(hud_font(12, QFont.Weight.Bold))
        body.addWidget(heading)
        if description:
            hint = QLabel(description)
            hint.setObjectName('SettingsHint')
            hint.setWordWrap(True)
            body.addWidget(hint)
        layout.addWidget(card)
        return body

    def _button(self, layout, title, callback, description=''):
        button = QPushButton(title)
        button.setFixedHeight(32)
        button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda checked=False: callback())
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)
        if description:
            note = QLabel(description)
            note.setWordWrap(True)
            layout.addWidget(note)
        return button

    def show_home(self):
        """Botão ‹: limpa a busca e volta ao início da central."""
        if self.search.text():
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
            self._search_matches = None
        self.show_category('home')

    def _show_group(self, group):
        aliases = {'home': ('home',), 'visual': ('appearance',), 'voice': ('audio',),
                   'ai': ('ai', 'learned_rules'), 'commands': ('automation',),
                   'integrations': ('integrations',), 'system': ('security', 'system')}
        pages = aliases.get(group, CATEGORY_GROUPS.get(group, ()))
        target = self._current if self._current in pages else (pages[0] if pages else 'home')
        self.show_category(target)

    def _category_matches(self, key, query):
        """Um tile do Início casa com a busca? Inclui termos dos plugins em Integrações."""
        if not query:
            return True
        entry = next((c for c in CATEGORIES if c[0] == key), None)
        if entry is not None:
            hay = f'{entry[1]} {entry[2]} {entry[3]}'
            if key == 'integrations':
                sections = (self.window.get_plugin_settings()
                            if self.window.get_plugin_settings else [])
                for section in sections:
                    hay += ' ' + str(section.get('title', '')) + ' ' \
                        + str(section.get('namespace', '')) + ' ' \
                        + ' '.join(str(f.get('label', ''))
                                   for f in section.get('fields', []))
        else:
            hay = NAV_TITLES.get(key, '')
        return all(word in normalized(hay) for word in query.split())

    def _apply_search_filter(self, query=''):
        """No Início, tiles e rótulos de grupo só aparecem se casarem com a busca."""
        if hasattr(self, '_home_tiles') is False:
            return
        query = normalized(query.strip()) if query else ''
        for key, tile in self._home_tiles.items():
            tile.setVisible(self._category_matches(key, query))
        labels = self._home_group_labels if hasattr(self, '_home_group_labels') else {}
        for group_title, label in labels.items():
            keys = CATEGORY_GROUPS.get(group_title, ())
            label.setVisible(any(self._home_tiles[k].isVisible()
                                 for k in keys if k in self._home_tiles))
        seps = self._home_separators if hasattr(self, '_home_separators') else {}
        for (_group, left, right), sep in seps.items():
            sep.setVisible(self._home_tiles[left].isVisible()
                           and self._home_tiles[right].isVisible())

    def show_category(self, key):
        if key != 'audio' and hasattr(self, 'preview'):
            self.preview.player.stop()
        self._current = key
        self.back_btn.setVisible(key != 'home')
        if key == 'home':
            self.breadcrumb.setText('')
            self.heading.setText('Configurações')
            self.subtitle.setText('Escolha uma área ou use a busca acima.')
            if self._home_page is None:
                self._home_page = self._build_home()
                self.stack.addWidget(self._home_page)
            self._apply_search_filter(self.search.text().strip())
            self.search.setVisible(True)
            self.stack.setCurrentWidget(self._home_page)
            self._home_page.verticalScrollBar().setValue(0)
            return
        group_title = next((label for label, keys in NAV_GROUPS if key in keys), '')
        _, title, description, _ = next(c for c in CATEGORIES if c[0] == key)
        # Breadcrumb mostra o caminho: em que seção do Início você está.
        self.breadcrumb.setText(f'INÍCIO  ›  {group_title}'.strip()
                                if group_title else 'INÍCIO')
        self.heading.setText(title)
        self.subtitle.setText(description)
        if key not in self._pages:
            page = QWidget()
            page.setObjectName('SettingsPage')
            layout = QVBoxLayout(page)
            layout.setContentsMargins(1, 0, 6, 3)
            layout.setSpacing(9)
            try:
                getattr(self, '_build_' + key)(layout)
            except Exception as exc:
                # Optional integrations must not take the settings window down.
                error = QLabel(f'Não foi possível abrir este painel: {exc}')
                error.setWordWrap(True)
                layout.addWidget(error)
            layout.addStretch(1)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(page)
            self._pages[key] = scroll
            self.stack.addWidget(scroll)
        self.stack.setCurrentWidget(self._pages[key])
        self._restyle_forms()

    # Ícones vetoriais das linhas do Início, no estilo dos apps de ajustes
    # modernos — desenhados com QPainter, portanto seguem o tema e não
    # dependem de fonte instalada nem usam emoji.
    CATEGORY_ICONS = {
        'general': 'person', 'appearance': 'palette', 'audio': 'mic',
        'ai': 'chip', 'memory': 'database', 'learned_rules': 'rules',
        'automation': 'clock', 'integrations': 'plug', 'security': 'lock',
        'system': 'power',
    }

    def _home_separator(self):
        line = QLabel()
        line.setObjectName('SettingsRowSeparator')
        line.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        line.setFixedHeight(1)
        return line

    def _home_row(self, key, title, description):
        tile = QPushButton()
        tile.setObjectName('SettingsHomeTile')
        tile.setMinimumHeight(56)
        tile.setCursor(Qt.CursorShape.PointingHandCursor)
        tile.setAccessibleName(title)
        row = QHBoxLayout(tile)
        row.setContentsMargins(10, 6, 12, 6)
        row.setSpacing(11)
        badge = QWidget()
        badge.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        badge.setObjectName('SettingsTileIcon')
        badge.setFixedSize(36, 36)
        badge_ev = QHBoxLayout(badge)
        badge_ev.setContentsMargins(0, 0, 0, 0)
        badge_ev.addStretch(1)
        badge_ev.addWidget(SettingsIcon(
            self.CATEGORY_ICONS.get(key, 'person'), self, mode='accent', size=20))
        badge_ev.addStretch(1)
        badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(badge)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name = QLabel(title)
        name.setObjectName('SettingsHomeTileTitle')
        name.setFont(hud_font(10, QFont.Weight.Bold))
        name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        text_col.addWidget(name)
        detail = QLabel(description)
        detail.setObjectName('SettingsHomeTileDescription')
        detail.setFont(hud_font(8))
        detail.setWordWrap(True)
        detail.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        text_col.addWidget(detail)
        row.addLayout(text_col, 1)
        arrow = QLabel('›')
        arrow.setObjectName('SettingsHomeTileArrow')
        arrow.setFont(hud_font(14, QFont.Weight.Bold))
        arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(arrow, 0, Qt.AlignmentFlag.AlignVCenter)
        tile.clicked.connect(lambda checked=False, k=key: self.show_category(k))
        return tile

    def _build_home(self):
        """Home no estilo dos ajustes modernos: perfil no topo e grupos
        de linhas em cartoes, com um divisor fino entre as linhas."""
        page = QWidget()
        page.setObjectName('SettingsHome')
        outer = QVBoxLayout(page)
        outer.setContentsMargins(2, 4, 8, 8)
        outer.setSpacing(9)
        cfg = config.load_api_keys()

        # Cartao de perfil: atalho direto para a pagina Perfil.
        hero = QPushButton()
        hero.setObjectName('SettingsHeroRow')
        hero.setMinimumHeight(64)
        hero.setCursor(Qt.CursorShape.PointingHandCursor)
        hero.setAccessibleName('Abrir perfil')
        hero_row = QHBoxLayout(hero)
        hero_row.setContentsMargins(12, 9, 12, 9)
        hero_row.setSpacing(12)
        avatar = QWidget()
        avatar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        avatar.setObjectName('SettingsAvatar')
        avatar.setFixedSize(42, 42)
        avatar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        avatar_layout = QHBoxLayout(avatar)
        avatar_layout.setContentsMargins(0, 0, 0, 0)
        avatar_layout.addStretch(1)
        avatar_layout.addWidget(SettingsIcon('person', self, mode='contrast', size=22))
        avatar_layout.addStretch(1)
        hero_row.addWidget(avatar)
        hero_col = QVBoxLayout()
        hero_col.setSpacing(2)
        hero_name = QLabel(cfg.get('assistant_name') or 'JINX')
        hero_name.setObjectName('SettingsHomeTileTitle')
        hero_name.setFont(hud_font(11, QFont.Weight.Bold))
        hero_name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        hero_col.addWidget(hero_name)
        user = (cfg.get('user_name') or '').strip()
        hero_sub = QLabel('Atendente de ' + user if user
                          else 'Toque para configurar seu perfil')
        hero_sub.setObjectName('SettingsHomeTileDescription')
        hero_sub.setFont(hud_font(8))
        hero_sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        hero_col.addWidget(hero_sub)
        hero_row.addLayout(hero_col, 1)
        hero_arrow = QLabel('›')
        hero_arrow.setObjectName('SettingsHomeTileArrow')
        hero_arrow.setFont(hud_font(16, QFont.Weight.Bold))
        hero_arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        hero_row.addWidget(hero_arrow, 0, Qt.AlignmentFlag.AlignVCenter)
        hero.clicked.connect(lambda checked=False: self.show_category('general'))
        outer.addWidget(hero)

        self._home_tiles = {}
        self._home_group_labels = {}
        self._home_separators = {}
        for group_title, keys in NAV_GROUPS:
            targets = [k for k in keys
                       if k != 'home' and any(c[0] == k for c in CATEGORIES)]
            if not targets:
                continue
            rotulo = QLabel(group_title)
            rotulo.setObjectName('SettingsSectionLabel')
            rotulo.setFont(hud_font(7))
            outer.addWidget(rotulo)
            self._home_group_labels[group_title] = rotulo
            card = QWidget()
            card.setObjectName('SettingsGroupCard')
            card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            col = QVBoxLayout(card)
            col.setContentsMargins(4, 4, 4, 4)
            col.setSpacing(0)
            previous = None
            for key in targets:
                if previous is not None:
                    sep = self._home_separator()
                    col.addWidget(sep)
                    self._home_separators[(group_title, previous, key)] = sep
                _, title, description, _ = next(c for c in CATEGORIES if c[0] == key)
                tile = self._home_row(key, title, description)
                col.addWidget(tile)
                self._home_tiles[key] = tile
                previous = key
            outer.addWidget(card)
        outer.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _search(self, text):
        query = normalized(text.strip())
        self._search_matches = None
        if not query:
            if self._current != 'home':
                self.show_category('home')
            else:
                self._apply_search_filter('')
            return
        matches = {key for key, *_ in CATEGORIES if self._category_matches(key, query)}
        self._search_matches = matches
        if self._current != 'home':
            self.show_category('home')
        else:
            self._apply_search_filter(query)
        if not matches:
            self.subtitle.setText(f'Nenhum resultado para \u201c{text.strip()}\u201d.')
        elif len(matches) == 1:
            self.subtitle.setText('1 área encontrada — Enter abre.')
        else:
            self.subtitle.setText(
                f'{len(matches)} áreas encontradas — Enter abre a primeira.')


    def _embed(self, layout, widget):
        widget.setProperty('settingsEmbedded', True)
        widget.setWindowFlags(Qt.WindowType.Widget)
        widget.setMinimumWidth(0)
        widget.setMaximumWidth(16777215)
        widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        # Provider/device lists may contain long model and hardware names;
        # their size hints must not force the entire settings page wider.
        for combo in widget.findChildren(QComboBox):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
            combo.setMinimumWidth(0)
            combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        # Existing forms retain their save logic. Closing belongs to this window.
        for button in widget.findChildren(QPushButton):
            if button.text().strip() in ('FECHAR', 'CANCELAR'):
                button.hide()
        self._embedded.append(widget)
        layout.addWidget(widget)
        widget.show()
        return widget

    def _build_general(self, layout):
        cfg = config.load_api_keys()
        layout = self._card(layout, 'Identidade da assistente',
                            'Defina como a JINX se apresenta e como fala com você.')
        layout.addWidget(QLabel('Nome do assistente'))
        self.assistant_name = QLineEdit(cfg.get('assistant_name') or 'JINX')
        layout.addWidget(self.assistant_name)
        layout.addWidget(QLabel('Como a JINX deve chamar você'))
        self.user_name = QLineEdit(cfg.get('user_name') or '')
        layout.addWidget(self.user_name)
        def save():
            # Persist first: the existing runtime callback is used only on success.
            name = self.assistant_name.text().strip() or 'JINX'
            user = self.user_name.text().strip()
            try:
                config.update_config(assistant_name=name, user_name=user)
                self.window._apply_name_update(name, user)
                self.status.setText('Identidade salva.')
            except Exception as exc:
                self.status.setText(f'Não foi possível salvar: {exc}')
        self._button(layout, 'Aplicar identidade', save)

    def _build_appearance(self, layout):
        themes_body = self._card(layout, 'Tema da central',
                                 'Escolha um estilo. Ele é aplicado e salvo na hora.')
        grid = QGridLayout()
        grid.setSpacing(9)
        columns = 3 if self.width() >= 900 else 2
        for index, (key, theme) in enumerate(SETTINGS_THEMES.items()):
            card = QPushButton()
            card.setObjectName('SettingsThemeCard')
            card.setCheckable(True)
            card.setFixedHeight(126)
            card.setAccessibleName(theme.name)
            card.setToolTip(theme.description)
            inner = QVBoxLayout(card)
            inner.setContentsMargins(12, 10, 12, 10)
            preview = ThemePreview(resolved_settings_theme(key), key)
            preview.setFixedHeight(64)
            self._theme_previews[key] = preview
            inner.addWidget(preview)
            label = QLabel(theme.name)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            inner.addWidget(label)
            card.clicked.connect(lambda checked=False, k=key: self.select_theme(k))
            self._theme_buttons[key] = card
            grid.addWidget(card, index // columns, index % columns)
            grid.setRowMinimumHeight(index // columns, 126)
        themes_body.addLayout(grid)
        self._button(themes_body, 'Restaurar Cyber HUD', lambda: self.select_theme(DEFAULT_SETTINGS_THEME))
        icon_body = self._card(layout, 'Ícone do aplicativo',
                               'O ícone é aplicado à janela e aos atalhos existentes.')
        icon_picker_button = QPushButton('Alterar ícone')
        icon_picker_button.setCheckable(True)
        icon_body.addWidget(icon_picker_button, alignment=Qt.AlignmentFlag.AlignLeft)
        from gui.app_icon_picker import AppIconPicker
        icon_picker = AppIconPicker(self.window)
        icon_body.addWidget(icon_picker)
        icon_picker.setVisible(False)
        icon_picker_button.toggled.connect(icon_picker.setVisible)
        layout = self._card(layout, 'Visual do HUD',
                            'As esferas e a cor do HUD são independentes dos outros quatro temas.')
        layout.addWidget(QLabel('Visual do assistente no HUD'))
        hud = QComboBox()
        names = {'face': 'Rosto animado', 'core': 'Núcleo reator', 'brahma_evo': 'EVO',
                 'brahma_echo': 'ECHO', 'qwen_neural': 'Orbe Neural'}
        for key in self.window.hud.available_styles():
            hud.addItem(names.get(key, key), key)
        hud.setCurrentIndex(max(0, hud.findData(self.window.hud.hud_style)))
        hud.activated.connect(lambda: self.window._set_hud_style(hud.currentData()))
        layout.addWidget(hud)
        from gui.overlays import HueWheel
        from gui.theme import DEFAULT_UI_COLOR
        cfg = config.load_api_keys()
        color = cfg.get('ui_color') or DEFAULT_UI_COLOR
        color_panel = QWidget()
        color_layout = QVBoxLayout(color_panel)
        wheel = HueWheel(color)
        color_layout.addWidget(wheel, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.hud_color = QLineEdit(color)
        self.hud_color.setAccessibleName('Cor do HUD em hexadecimal')
        wheel.hue_committed.connect(self.hud_color.setText)
        color_layout.addWidget(self.hud_color)
        self._button(color_layout, 'Aplicar cor do HUD', self._save_hud_color)
        toggle = self._button(layout, 'Cor personalizada do HUD', lambda: None,
                             'Os temas personalizam a central. O HUD mantém sua própria cor e visual.')
        toggle.setCheckable(True)
        toggle.toggled.connect(color_panel.setVisible)
        layout.addWidget(color_panel)
        color_panel.hide()
        self._build_orb_neural_card(layout)
        self._sync_theme_buttons()

    def _save_hud_color(self):
        color = self.hud_color.text().strip().lower()
        if not re.fullmatch(r'#[0-9a-f]{6}', color):
            self.status.setText('Use uma cor hexadecimal, como #00d4ff.')
            return
        try:
            config.update_config(ui_color=color)
            self.window._preview_ui_color(color)
            # The Cyber HUD settings style follows the same live accent.
            self._apply_theme()
            self.status.setText('Cor da JINX aplicada e salva.')
        except Exception as exc:
            self.status.setText(f'Não foi possível aplicar a cor: {exc}')

    _ORB_NEURAL_STOPS = (
        ('Paleta', 'palette', (('Nebulosa', 'nebula'), ('Plasma', 'plasma'),
                               ('Aurora', 'aurora'), ('Solar', 'solar'),
                               ('Fantasma', 'ghost'), ('Esmeralda', 'emerald'))),
        ('Qualidade', 'quality', (('Eco', 'eco'), ('Padrão', 'standard'),
                                  ('Alta', 'high'), ('Ultra', 'ultra'))),
        ('Partículas', 'count', (('8 mil', 8000), ('16 mil', 16000),
                                 ('24 mil', 24000), ('32 mil', 32000),
                                 ('40 mil', 40000))),
        ('Turbulência', 'turb', (('Suave', 0.5), ('Padrão', 0.9), ('Energética', 1.4))),
        ('Fluxo', 'flow', (('Lento', 0.7), ('Padrão', 1.0), ('Rápido', 1.3))),
        ('Escala', 'size', (('Compacta', 1.0), ('Padrão', 1.35), ('Grande', 1.8))),
        ('Brilho', 'glow', (('Suave', 0.7), ('Padrão', 1.0), ('Intenso', 1.4))),
        ('Sensibilidade à voz', 'sens', (('Baixa', 0.8), ('Padrão', 1.3), ('Alta', 2.0))),
    )

    def _build_orb_neural_card(self, layout):
        """Orbe Neural: tunables pushed live to the qwen_neural page and saved."""
        from gui import hud as hud_module
        if hud_module.QWebEngineView is None:
            self._card(layout, 'Orbe Neural',
                       'Exige o PyQt6-WebEngine declarado em requirements.txt.')
            return
        card = self._card(layout, 'Orbe Neural',
                          'Ajustes do Orbe Neural aplicados na hora e salvos; '
                          'o orbe reage à voz pelo próprio HUD.')
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        current = dict(config.get_plugin_config('hud_qwen_neural'))
        self._orb_combos = []
        self._orb_checks = []
        row = 0

        def add_combo(label, key, options):
            nonlocal row
            grid.addWidget(QLabel(label), row, 0)
            combo = QComboBox()
            for text, value in options:
                combo.addItem(text, value)
            value = current.get(key)
            if value is not None:
                idx = combo.findData(value)
                if idx < 0 and isinstance(value, (int, float)):
                    numeric = [(i, combo.itemData(i)) for i in range(combo.count())
                               if isinstance(combo.itemData(i), (int, float))]
                    if numeric:
                        idx = min(numeric, key=lambda t: abs(t[1] - float(value)))[0]
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.currentIndexChanged.connect(
                lambda _index, key=key, combo=combo: self._save_orb_setting(key, combo.currentData()))
            grid.addWidget(combo, row, 1)
            self._orb_combos.append((key, combo))
            row += 1

        for label, key, options in self._ORB_NEURAL_STOPS:
            add_combo(label, key, options)

        for label, key in (('Corona', 'corona'), ('Faíscas', 'sparkles')):
            chk = QCheckBox(label)
            chk.setChecked(bool(current.get(key, True)))
            chk.toggled.connect(lambda on, key=key: self._save_orb_setting(key, bool(on)))
            grid.addWidget(chk, row, 0, 1, 2)
            self._orb_checks.append((key, chk))
            row += 1

        buttons = QHBoxLayout()
        randomize = QPushButton('Aleatorizar')
        randomize.clicked.connect(self.window._orb_neural_randomize)
        reset = QPushButton('Restaurar padrão')
        reset.clicked.connect(self.window._orb_neural_reset)
        buttons.addWidget(randomize)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        grid.addLayout(buttons, row, 0, 1, 2)
        card.addLayout(grid)

    def _save_orb_setting(self, key, value):
        """Persist one Orbe Neural adjustment and push it to the live page."""
        try:
            config.save_plugin_config('hud_qwen_neural', {key: value})
        except Exception as exc:
            self.status.setText(f'Não foi possível salvar o ajuste do orbe: {exc}')
            return
        self.window._orb_neural_push(key, value)

    def select_theme(self, key):
        key = settings_theme_id(key)
        try:
            config.update_config(settings_theme=key)
        except Exception as exc:
            self.status.setText(f'Não foi possível salvar o tema: {exc}')
            self._sync_theme_buttons()
            return
        self.theme_id = key
        before, after = apply_settings_theme_palette(
            key, config.load_api_keys().get('ui_color'))
        retheme_all_widgets(before, after)
        self._apply_theme()
        self.status.setText(f'Tema {SETTINGS_THEMES[key].name} aplicado e salvo.')

    def _sync_theme_buttons(self):
        for key, button in self._theme_buttons.items():
            button.setChecked(key == self.theme_id)

    def _update_audio_columns(self):
        columns = getattr(self, '_audio_columns', None)
        integration_columns = getattr(self, '_integration_columns', None)
        direction = (QBoxLayout.Direction.LeftToRight if self.width() >= 980
                     else QBoxLayout.Direction.TopToBottom)
        if columns is not None and columns.direction() != direction:
            columns.setDirection(direction)
        voice_card = getattr(self, '_voice_card', None)
        devices_card = getattr(self, '_devices_card', None)
        if columns is not None and voice_card is not None and devices_card is not None:
            if direction == QBoxLayout.Direction.LeftToRight:
                voice_card.setMinimumWidth(300)
                devices_card.setMinimumWidth(365)
            else:
                voice_card.setMinimumWidth(0)
                devices_card.setMinimumWidth(0)
        if integration_columns is not None:
            integration_direction = (QBoxLayout.Direction.LeftToRight
                                     if self.width() >= 1000
                                     else QBoxLayout.Direction.TopToBottom)
            if integration_columns.direction() != integration_direction:
                integration_columns.setDirection(integration_direction)
            selector = getattr(self, '_integration_selector', None)
            if selector is not None:
                if integration_direction == QBoxLayout.Direction.LeftToRight:
                    selector.setFixedWidth(205)
                    selector.setMaximumHeight(16777215)
                else:
                    selector.setMinimumWidth(0)
                    selector.setMaximumWidth(16777215)
                    selector.setMaximumHeight(190)
        narrow = self.width() < 760
        self.search.setMaximumWidth(170 if narrow else 190)
        self.findChild(QLabel, 'SettingsKicker').setVisible(not narrow)

    def resizeEvent(self, event):
        self._update_audio_columns()
        super().resizeEvent(event)

    def _build_audio(self, layout):
        from gui.overlays import AudioDeviceOverlay
        from gui.voice_preview import VoicePicker, VoicePreviewController
        columns_host = QWidget()
        columns = QBoxLayout(QBoxLayout.Direction.LeftToRight, columns_host)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(14)
        layout.addWidget(columns_host)
        self._audio_columns = columns
        self._update_audio_columns()
        voice_body = self._card(columns, 'Voz da assistente',
                                'Escolha e ouça uma amostra antes de alterar a voz ativa.')
        voice_body.addWidget(QLabel('Modelo de voz Gemini'))
        self.voice = VoicePicker()
        from gui.voice_preview import fill_voice_picker
        fill_voice_picker(self.voice, config.get_voice())
        voice_body.addWidget(self.voice)
        self.voice_status = QLabel('Escolha uma voz e ouça antes de aplicar.')
        self.voice_status.setWordWrap(True)
        self.preview = VoicePreviewController(self, lambda active: (
            self.window.on_voice_preview_state(active) if self.window.on_voice_preview_state else None))
        self.voice.preview_theme = resolved_settings_theme(self.theme_id)
        self.preview.status.connect(lambda voice, msg: self.voice_status.setText(f'{voice}: {msg}'))
        self.voice.preview_requested.connect(self.preview.player.request)
        actions = QHBoxLayout()
        self._button(actions, 'Ouvir prévia', lambda: self._preview_voice())
        self._button(actions, 'Parar', self.preview.player.stop)
        self._button(actions, 'Aplicar voz', self._save_voice)
        voice_body.addLayout(actions)
        voice_body.addWidget(self.voice_status)
        voice_body.addStretch(1)
        devices_body = self._card(columns, 'Microfone e saída de áudio',
                                  'Selecione os dispositivos e teste antes de aplicar.')
        audio = self._embed(devices_body, AudioDeviceOverlay())
        audio.picked.connect(self.window._on_audio_devices_applied)
        # Without explicit stretches, long device names can steal the width
        # of the voice card when both panels are side by side.
        self._voice_card = voice_body.parentWidget()
        self._devices_card = devices_body.parentWidget()
        self._update_audio_columns()
        columns.setStretch(0, 1)
        columns.setStretch(1, 1)

    def _preview_voice(self):
        voice = self.voice.currentData()
        if voice is None:
            self.voice_status.setText('Selecione uma voz antes de ouvir a prévia.')
            return
        self.preview.player.request(voice)

    def _save_voice(self):
        try:
            voice = self.voice.currentData()
            if voice is None:
                self.voice_status.setText('Selecione uma voz antes de aplicar.')
                return
            changed = voice != config.get_voice()
            config.save_voice(voice)
            self.preview.player.stop()
            if changed and self.window.on_voice_change:
                self.window.on_voice_change()
            self.window._refresh_identity_rows()
            self.status.setText(f'Voz {voice} salva.')
        except Exception as exc:
            self.status.setText(f'Não foi possível aplicar a voz: {exc}')

    def _build_ai(self, layout):
        from gui.providers_panel import ProvidersOverlay
        panel = ProvidersOverlay()
        panel.set_settings_embedded()
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        panel = self._embed(layout, panel)
        panel.changed.connect(self.window._on_providers_applied)

    def _build_memory(self, layout):
        from gui.memory_proposals_panel import MemoryProposalsPanel
        self._embed(self._card(layout, 'Propostas de memória'), MemoryProposalsPanel())
        from gui.overlays import MemoryOverlay
        self._embed(self._card(layout, 'Memória da JINX'), MemoryOverlay())

    def _build_learned_rules(self, layout):
        from gui.learned_rules_panel import LearnedRulesPanel
        self._embed(self._card(layout, 'Learned Rules',
                               'Regras de estilo e fluxo. Nada é salvo sem a sua aprovação.'),
                    LearnedRulesPanel())

    def _runtime_toggle(self, layout, title, description, source, callback, getter):
        row = ToggleRow(title, description)
        layout.addWidget(row)
        def sync():
            try:
                active = bool(getter())
                row.switch.setChecked(active)
                row.switch.setEnabled(source.isEnabled())
                row.switch.setToolTip(clean_settings_label(source.text()))
            except Exception:
                row.switch.setEnabled(False)
                row.state.setText('Indisponível')
        def apply():
            try:
                callback()
            except Exception:
                if self is not None:
                    self.status.setText('Não foi possível alterar esta opção. Confira o estado atual.')
            finally:
                sync()
        # Programmatic refreshes never execute a user action.
        row.switch.clicked.connect(apply)
        timer = QTimer(row)
        timer.timeout.connect(sync)
        timer.start(1000)
        sync()
        return row

    def _build_automation(self, layout):
        actions = self._card(layout, 'Agenda e exibição')
        self._button(actions, 'Abrir agenda', lambda: self._open_extra('agenda'))
        if hasattr(self.window, '_toggle_fullscreen'):
            self._button(actions, 'Alternar tela cheia [F11]', self.window._toggle_fullscreen)
        controls = self._card(layout, 'Ativação e controles',
                              'As chaves refletem o estado atual. As alterações são aplicadas ao clicar.')
        from core.gesture_control import control
        specs = (
            ('Resumo da manhã', 'Receba um resumo ao iniciar o dia.', '_brief_btn', '_toggle_brief', config.get_brief_enabled),
            ('Palavra de ativação', 'Ative a escuta pelo nome. A preparação existente é mantida.', '_wake_btn', '_toggle_wake_word', config.get_wake_word_enabled),
            ('Pressionar para falar', 'Mantenha a tecla configurada pressionada para usar o microfone.', '_ptt_btn', '_toggle_ptt', config.get_push_to_talk_enabled),
            ('Controle por gestos', 'Use a câmera para controlar o ponteiro.', '_gesture_btn', '_toggle_gestures', lambda: control.status()['active']),
        )
        for title, description, attribute, callback, getter in specs:
            source = getattr(self.window, attribute, None)
            if source is not None:
                self._runtime_toggle(controls, title, description, source, getattr(self.window, callback), getter)
        source = getattr(self.window, '_wake_sleep_btn', None)
        if source is not None:
            button = self._button(actions, clean_settings_label(source.text()), self.window._tap_wake_manual)
            timer = QTimer(button)
            def sync_manual():
                button.setText(clean_settings_label(source.text()))
                button.setVisible(not source.isHidden())
            timer.timeout.connect(sync_manual)
            timer.start(1000)
            sync_manual()

    def _build_integrations(self, layout):
        layout = self._card(layout, 'Integrações instaladas',
                            'Pesquise e selecione um serviço. Credenciais permanecem ocultas.')
        sections = self.window.get_plugin_settings() if self.window.get_plugin_settings else []
        if not sections:
            layout.addWidget(QLabel('Nenhum plugin com configurações está carregado.'))
            return
        from gui.overlays import PluginSettingsOverlay
        selector = QWidget()
        selector_layout = QVBoxLayout(selector)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.setSpacing(7)
        plugin_search = QLineEdit()
        plugin_search.setObjectName('SettingsPluginSearch')
        plugin_search.setPlaceholderText('Buscar integração…')
        plugin_search.setAccessibleName('Buscar integração')
        self.plugin_search = plugin_search
        selector_layout.addWidget(plugin_search)
        plugin_list = QListWidget()
        plugin_list.setObjectName('SettingsPluginList')
        plugin_list.setAccessibleName('Integrações disponíveis')
        self.plugin_list = plugin_list
        self._plugin_sections = sections
        for section in sections:
            title = section.get('title') or section.get('namespace') or 'Plugin'
            item = QListWidgetItem(title.split(' / ')[0].split(' — ')[0])
            item.setToolTip(str(section.get('namespace') or title))
            plugin_list.addItem(item)
        selector_layout.addWidget(plugin_list, 1)
        columns_host = QWidget()
        columns = QBoxLayout(QBoxLayout.Direction.LeftToRight, columns_host)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(10)
        self._integration_columns = columns
        self._integration_selector = selector
        self._update_audio_columns()
        columns.addWidget(selector)
        stack = QStackedWidget()
        stack.setObjectName('SettingsPluginDetails')
        columns.addWidget(stack, 1)
        columns.setStretch(0, 0)
        columns.setStretch(1, 1)
        layout.addWidget(columns_host, 1)
        panels = {}
        def select(index):
            if index < 0 or index >= len(sections):
                if not stack.count():
                    stack.addWidget(QLabel('Nenhuma integração corresponde à busca.'))
                stack.setCurrentIndex(0)
                return
            if index not in panels:
                panel = PluginSettingsOverlay([sections[index]], compact=True)
                panel.setProperty('settingsEmbedded', True)
                for button in panel.findChildren(QPushButton):
                    if button.text().strip() == 'FECHAR':
                        button.hide()
                self._embedded.append(panel)
                panels[index] = panel
                stack.addWidget(panel)
            stack.setCurrentWidget(panels[index])
            self._restyle_forms()
        plugin_list.currentRowChanged.connect(select)
        plugin_search.textChanged.connect(self._filter_plugins)
        select(0)

    def _filter_plugins(self, query=''):
        plugin_list = getattr(self, 'plugin_list', None)
        sections = getattr(self, '_plugin_sections', ())
        if plugin_list is None:
            return
        global_query = self.search.text() if hasattr(self, 'search') else ''
        words = normalized(f'{query} {global_query}'.strip())
        matches = []
        for index, section in enumerate(sections):
            title = str(section.get('title') or '')
            namespace = str(section.get('namespace') or '')
            fields = ' '.join(str(field.get('label', ''))
                              for field in section.get('fields', []))
            visible = all(word in normalized(f'{title} {namespace} {fields}')
                          for word in words.split())
            plugin_list.item(index).setHidden(not visible)
            if visible:
                matches.append(index)
        current = plugin_list.currentRow()
        if matches and current not in matches:
            plugin_list.setCurrentRow(matches[0])
        elif not matches:
            plugin_list.setCurrentRow(-1)

    def _build_security(self, layout):
        layout = self._card(layout, 'Acesso e privacidade')
        self._security_layout = layout
        https = QCheckBox('Proteger o acesso remoto com HTTPS')
        https.setObjectName('RemoteHttpsToggle')
        https.setAccessibleName('Ativar HTTPS no acesso remoto')
        https.setChecked(config.load_api_keys().get('dashboard_https', True) is not False)
        self._remote_https_toggle = https
        https.toggled.connect(self._save_remote_https)
        layout.addWidget(https)
        note = QLabel(
            'HTTPS é o padrão, com certificado autoassinado local. O navegador pode '
            'mostrar um aviso: a criptografia depende de confiar no certificado do '
            'seu JINX. '
            'A preferência só entra em vigor ao reiniciar o JINX. Desativar HTTPS '
            'deixa tokens e comandos visíveis na rede local.'
        )
        note.setObjectName('SettingsHint')
        note.setWordWrap(True)
        layout.addWidget(note)
        self._button(layout, 'Gerenciar acesso remoto', self._remote,
                     'Abra o endereço, QR code e gerenciamento da chave de acesso pelo celular.')

    def _save_remote_https(self, enabled):
        try:
            config.update_config(dashboard_https=bool(enabled))
            self.status.setText(
                'Preferência HTTPS salva. Reinicie o JINX para aplicá-la.'
                if enabled else
                'HTTP sem criptografia salvo. Reinicie o JINX para aplicá-lo.'
            )
        except Exception as exc:
            previous = config.load_api_keys().get('dashboard_https', True) is not False
            self._remote_https_toggle.blockSignals(True)
            self._remote_https_toggle.setChecked(previous)
            self._remote_https_toggle.blockSignals(False)
            self.status.setText(f'Não foi possível salvar a segurança remota: {exc}')

    def _remote(self):
        self.window._open_remote()
        panel = getattr(self.window, '_remote_overlay', None)
        if panel is None:
            self.status.setText('Acesso remoto indisponível. Confira o log da JINX.')
            return
        self._embed(self._security_layout, panel)
        self._restyle_forms()

    def _build_system(self, layout):
        layout = self._card(layout, 'Inicialização e manutenção')
        self._button(layout, 'Escolher ícone da JINX', lambda: self.show_category('appearance'))
        self._button(layout, 'Criar atalho na área de trabalho', self.window._create_desktop_shortcut)
        self._runtime_toggle(layout, 'Iniciar com o Windows',
                             'Abra a JINX automaticamente ao entrar no computador.',
                             self.window._autostart_btn, self.window._toggle_autostart,
                             getattr(self.window, '_check_autostart', lambda: False))
        self._button(layout, 'Plugins carregados', lambda: self._open_extra('plugins'))

    def _open_extra(self, key):
        if key not in self._pages:
            page = QWidget()
            layout = QVBoxLayout(page)
            if key == 'agenda':
                from gui.agenda_panel import AgendaPanel
                panel = AgendaPanel(self)
            else:
                from gui.overlays import PluginManagerOverlay
                panel = PluginManagerOverlay(self.window.get_plugins() if self.window.get_plugins else [])
            self._embed(layout, panel)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(page)
            self._pages[key] = scroll
            self.stack.addWidget(scroll)
        self.heading.setText('Agenda' if key == 'agenda' else 'Plugins carregados')
        self.subtitle.setText('Use o menu lateral para voltar às categorias.')
        self.stack.setCurrentWidget(self._pages[key])
        self._restyle_forms()

    def _apply_theme(self):
        t = resolved_settings_theme(self.theme_id)
        # Update the Cyber preview when the user changes the HUD accent.
        cyber_preview = self._theme_previews.get(DEFAULT_SETTINGS_THEME)
        if cyber_preview is not None:
            cyber_preview.theme = resolved_settings_theme(DEFAULT_SETTINGS_THEME)
            cyber_preview.update()
        self._styling = True
        self.setStyleSheet(settings_stylesheet(self.theme_id, t, DISPLAY_CSS))
        self._styling = False
        palette = self.palette()
        for role, color in ((QPalette.ColorRole.Window, t.bg), (QPalette.ColorRole.Base, t.field),
                            (QPalette.ColorRole.Text, t.text), (QPalette.ColorRole.WindowText, t.text),
                            (QPalette.ColorRole.Button, t.panel), (QPalette.ColorRole.ButtonText, t.text),
                            (QPalette.ColorRole.Highlight, t.selected), (QPalette.ColorRole.HighlightedText, t.text)):
            palette.setColor(role, QColor(color))
        self.setPalette(palette)
        self._sync_theme_buttons()
        if hasattr(self, 'voice'):
            self.voice.preview_theme = t
        self._restyle_forms()

    def _restyle_widget(self, widget):
        if self._styling:
            return
        source = self._original_styles.setdefault(widget, widget.styleSheet())
        colors = self._source_palettes.setdefault(widget, {key: value for key, value in vars(C).items() if key.isupper()})
        t = resolved_settings_theme(self.theme_id)
        mapping = {}
        for role in ('BG', 'PANEL', 'PANEL2', 'DARK', 'BAR_BG'):
            mapping[colors[role].lower()] = t.field if role == 'DARK' else t.panel
        for role in ('TEXT', 'WHITE'):
            mapping[colors[role].lower()] = t.text
        for role in ('TEXT_DIM', 'TEXT_MED'):
            mapping[colors[role].lower()] = t.muted
        for role in ('PRI', 'PRI_DIM'):
            mapping[colors[role].lower()] = t.accent
        for role in ('BORDER', 'BORDER_A', 'BORDER_B'):
            mapping[colors[role].lower()] = t.border
        mapping[colors['PRI_GHO'].lower()] = t.selected
        mapping.update({'#000d12': t.field, '#00091a': t.field})
        style = re.sub(r'#[0-9a-fA-F]{6}', lambda m: mapping.get(m[0].lower(), m[0]), source)
        style = re.sub(r'rgba\(0,\s*6,\s*10,\s*\d+\)', t.panel, style)
        self._styling = True
        try:
            widget.setStyleSheet(style)
        finally:
            self._styling = False

    def _uniform_hud_labels(self):
        """Use HUD display families and plain text for all settings controls.

        Preserve each widget's font size/weight and never change edit contents.
        """
        for widget in [self, *self.findChildren(QWidget)]:
            if isinstance(widget, (QLabel, QPushButton, QComboBox, QLineEdit, QListWidget)):
                current = widget.font()
                if current.families() != DISPLAY_FAMILIES:
                    font = QFont(current)
                    font.setFamilies(DISPLAY_FAMILIES)
                    widget.setFont(font)
            if isinstance(widget, (QLabel, QPushButton)):
                value = widget.text()
                cleaned = clean_settings_label(value)
                if value != cleaned:
                    widget.setText(cleaned)
            elif isinstance(widget, QComboBox):
                for index in range(widget.count()):
                    value = widget.itemText(index)
                    cleaned = clean_settings_label(value)
                    if cleaned != value:
                        widget.setItemText(index, cleaned)

    def _restyle_forms(self):
        for panel in self._embedded:
            for widget in [panel, *panel.findChildren(QWidget)]:
                self._restyle_widget(widget)
        self._uniform_hud_labels()
        theme = resolved_settings_theme(self.theme_id)
        for switch in self.findChildren(ToggleSwitch):
            for name, color in (('switchAccent', theme.accent), ('switchBorder', theme.border),
                                ('switchTrack', theme.field), ('switchKnob', theme.text)):
                switch.setProperty(name, color)
            switch.update()

    def eventFilter(self, obj, event):
        if obj is getattr(self, '_header_host', None):
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_offset is not None:
                if event.buttons() & Qt.MouseButton.LeftButton:
                    self.move(event.globalPosition().toPoint() - self._drag_offset)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._drag_offset = None
                return True
        if not self._styling and isinstance(obj, QWidget) and self.isAncestorOf(obj):
            if event.type() in (QEvent.Type.StyleChange, QEvent.Type.Polish) and any(p is obj or p.isAncestorOf(obj) for p in self._embedded):
                if event.type() == QEvent.Type.StyleChange:
                    self._original_styles[obj] = obj.styleSheet()
                    self._source_palettes.pop(obj, None)
                self._restyle_widget(obj)
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        if hasattr(self, 'preview'):
            self.preview.player.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        if hasattr(self, 'preview'):
            self.preview.player.stop()
        super().closeEvent(event)
