"""Single Qt settings window: searchable navigation and existing runtime forms.

Forms are created on demand on the Qt thread. Each form retains its existing
save/reconnect contract; theme changes only write the settings_theme key.
"""
import re
import unicodedata
from weakref import WeakKeyDictionary

from PyQt6.QtCore import QEvent, Qt, QTimer, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPalette, QLinearGradient, QRadialGradient, QBrush
from PyQt6.QtWidgets import (QApplication, QBoxLayout, QComboBox, QDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from gui.style import hud_font, DISPLAY_FAMILIES, DISPLAY_CSS
from gui.settings_visuals import settings_stylesheet
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
    ('general', 'Geral', 'Identidade e personalização', 'nome usuario assistente voz cor'),
    ('appearance', 'Aparência', 'Escolha o seu ambiente', 'tema cyber minimal nature titanium neon hud visual'),
    ('audio', 'Voz e áudio', 'Voz, microfone e saída de som', 'volume dispositivos teste entrada saida gemini previa'),
    ('ai', 'Inteligência artificial', 'Mecanismo e provedores', 'modelo stt llm tts api chave token ollama pipeline'),
    ('memory', 'Memória', 'Informações que a JINX lembra', 'esquecer excluir dados lembrancas'),
    ('learned_rules', 'Regras aprendidas', 'Preferências de comportamento que você aprova',
     'learned rules regras preferencias comportamento estilo fluxo aprovar exportar importar backup'),
    ('automation', 'Automação', 'Agenda e controles do dia a dia', 'eventos calendario resumo gestos camera palavra de ativacao wake push to talk pressionar falar'),
    ('integrations', 'Integrações', 'Configure um plugin por vez', 'plugins spotify discord google trello contas'),
    ('security', 'Segurança', 'Acesso remoto', 'celular chave acesso token remoto'),
    ('system', 'Sistema', 'Inicialização e manutenção', 'atalho windows iniciar carregados plugins'),
)


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


class SettingsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setObjectName('SettingsCentral')
        self.setWindowTitle('JINX — Configurações')
        self.setFont(hud_font(9))
        self.resize(1080, 740)
        self.setMinimumSize(760, 540)
        self.theme_id = settings_theme_id(config.load_api_keys().get('settings_theme'))
        self._pages = {}
        self._embedded = []
        self._original_styles = WeakKeyDictionary()
        self._source_palettes = WeakKeyDictionary()
        self._styling = False
        self._current = 'general'
        self._theme_buttons = {}
        self._theme_previews = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        header_host = QWidget()
        header_host.setObjectName('SettingsHeader')
        header_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header = QHBoxLayout(header_host)
        header.setContentsMargins(20, 13, 20, 13)
        header.setSpacing(16)
        identity = QVBoxLayout()
        identity.setSpacing(1)
        brand = QLabel('JINX IA')
        brand.setObjectName('SettingsBrand')
        brand.setFont(hud_font(17, QFont.Weight.Bold))
        identity.addWidget(brand)
        kicker = QLabel('CENTRAL DE CONFIGURAÇÕES')
        kicker.setObjectName('SettingsKicker')
        kicker.setFont(hud_font(8))
        identity.addWidget(kicker)
        header.addLayout(identity)
        header.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Buscar configurações…')
        self.search.setAccessibleName('Buscar configurações')
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(290)
        header.addWidget(self.search)
        root.addWidget(header_host)
        body = QHBoxLayout()
        body.setSpacing(14)
        self.navigation = QListWidget()
        self.navigation.setObjectName('SettingsNavigation')
        self.navigation.setFixedWidth(190)
        self.navigation.setAccessibleName('Categorias de configuração')
        for key, title, description, terms in CATEGORIES:
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setToolTip(description)
            self.navigation.addItem(item)
        body.addWidget(self.navigation)
        right = QVBoxLayout()
        self.heading = QLabel()
        self.heading.setObjectName('SettingsHeading')
        self.heading.setFont(hud_font(17, QFont.Weight.Bold))
        self.subtitle = QLabel()
        self.subtitle.setObjectName('SettingsSubtitle')
        self.subtitle.setWordWrap(True)
        right.addWidget(self.heading)
        right.addWidget(self.subtitle)
        right.addSpacing(12)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        self.empty = QLabel('Nenhuma configuração encontrada. Tente outro termo.')
        self.empty.setWordWrap(True)
        self.stack.addWidget(self.empty)
        body.addLayout(right, 1)
        root.addLayout(body, 1)
        footer_host = QWidget()
        footer_host.setObjectName('SettingsFooter')
        footer_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        footer = QHBoxLayout(footer_host)
        footer.setContentsMargins(15, 8, 15, 8)
        self.status = QLabel('As alterações são salvas em cada seção.')
        self.status.setObjectName('SettingsHint')
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        close = QPushButton('Concluir')
        close.setObjectName('SettingsPrimary')
        close.setMinimumWidth(96)
        close.clicked.connect(self.close)
        footer.addWidget(close)
        root.addWidget(footer_host)
        self.navigation.currentItemChanged.connect(self._selected)
        self.search.textChanged.connect(self._search)
        self.navigation.setCurrentRow(0)
        self._apply_theme()
        QApplication.instance().installEventFilter(self)

    def _card(self, layout, title, description=''):
        """Real responsive Qt panel; all controls keep their callbacks."""
        card = QWidget()
        card.setObjectName('SettingsCard')
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setMinimumWidth(0)
        card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        body = QVBoxLayout(card)
        body.setContentsMargins(17, 14, 17, 16)
        body.setSpacing(10)
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

    def _selected(self, item, previous=None):
        if item:
            self.show_category(item.data(Qt.ItemDataRole.UserRole))

    def show_category(self, key):
        if key != 'audio' and hasattr(self, 'preview'):
            self.preview.player.stop()
        self._current = key
        for index, category in enumerate(CATEGORIES):
            if category[0] == key and self.navigation.currentRow() != index:
                self.navigation.blockSignals(True)
                self.navigation.setCurrentRow(index)
                self.navigation.blockSignals(False)
                break
        _, title, description, _ = next(c for c in CATEGORIES if c[0] == key)
        self.heading.setText(title)
        self.subtitle.setText(description)
        if key not in self._pages:
            page = QWidget()
            page.setObjectName('SettingsPage')
            layout = QVBoxLayout(page)
            layout.setContentsMargins(1, 0, 8, 4)
            layout.setSpacing(12)
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
            scroll.setWidget(page)
            self._pages[key] = scroll
            self.stack.addWidget(scroll)
        self.stack.setCurrentWidget(self._pages[key])
        self._restyle_forms()

    def _search(self, text):
        query = normalized(text.strip())
        sections = self.window.get_plugin_settings() if self.window.get_plugin_settings else []
        plugin_terms = ' '.join(str(s.get('title', '')) + ' ' + str(s.get('namespace', ''))
                               + ' ' + ' '.join(str(f.get('label', '')) for f in s.get('fields', []))
                               for s in sections)
        matches = []
        for index, (key, title, description, terms) in enumerate(CATEGORIES):
            haystack = f'{title} {description} {terms}' + (plugin_terms if key == 'integrations' else '')
            match = all(word in normalized(haystack) for word in query.split())
            self.navigation.item(index).setHidden(not match)
            if match:
                matches.append(index)
        if matches:
            row = self.navigation.currentRow()
            if row not in matches:
                self.navigation.setCurrentRow(matches[0])
            else:
                self.show_category(CATEGORIES[row][0])
            if query and self._current == 'integrations' and hasattr(self, 'plugin_picker'):
                for index, section in enumerate(sections):
                    title = str(section.get('title', '')) + ' ' + str(section.get('namespace', ''))
                    fields = ' '.join(str(f.get('label', '')) for f in section.get('fields', []))
                    if all(word in normalized(title + ' ' + fields) for word in query.split()):
                        self.plugin_picker.setCurrentIndex(index)
                        break
        else:
            self.heading.setText('Busca')
            self.subtitle.setText('Nenhum resultado')
            self.stack.setCurrentWidget(self.empty)

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
        from gui.app_icon_picker import AppIconPicker
        icon_body = self._card(layout, 'Ícone da JINX')
        icon_body.addWidget(AppIconPicker(self.window))
        themes_body = self._card(layout, 'Escolha seu ambiente',
                                 'Cinco designs próprios. Clique em um cartão para aplicar imediatamente.')
        grid = QGridLayout()
        grid.setSpacing(12)
        for index, (key, theme) in enumerate(SETTINGS_THEMES.items()):
            card = QPushButton()
            card.setObjectName('SettingsThemeCard')
            card.setCheckable(True)
            # QPushButton's sizeHint does not account for nested preview widgets.
            # A fixed card height prevents the thumbnail from spilling over labels.
            card.setFixedHeight(158)
            card.setAccessibleName(theme.name)
            card.setToolTip(theme.description)
            inner = QVBoxLayout(card)
            inner.setContentsMargins(12, 10, 12, 10)
            preview = ThemePreview(resolved_settings_theme(key), key)
            self._theme_previews[key] = preview
            inner.addWidget(preview)
            label = QLabel(theme.name)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            inner.addWidget(label)
            card.clicked.connect(lambda checked=False, k=key: self.select_theme(k))
            self._theme_buttons[key] = card
            grid.addWidget(card, index // 2, index % 2)
            grid.setRowMinimumHeight(index // 2, 158)
        themes_body.addLayout(grid)
        self._button(themes_body, 'Restaurar Cyber HUD', lambda: self.select_theme(DEFAULT_SETTINGS_THEME))
        # The scroll page must grow to the gallery's real minimum height.
        # Otherwise Qt compresses all three preview rows into thin strips.
        themes_body.parentWidget().setMinimumHeight(660)
        layout = self._card(layout, 'Visual do HUD',
                            'As esferas e a cor do HUD são independentes dos outros quatro temas.')
        layout.addWidget(QLabel('Visual do assistente no HUD'))
        hud = QComboBox()
        names = {'face': 'Rosto animado', 'core': 'Núcleo reator', 'brahma_evo': 'EVO', 'brahma_echo': 'ECHO'}
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
        if columns is None:
            return
        direction = (QBoxLayout.Direction.LeftToRight if self.width() >= 1160
                     else QBoxLayout.Direction.TopToBottom)
        if columns.direction() != direction:
            columns.setDirection(direction)

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
        for name in config.AVAILABLE_VOICES:
            self.voice.addItem(f'{name} — {config.VOICE_STYLES[name]}', name)
        self.voice.setCurrentIndex(max(0, self.voice.findData(config.get_voice())))
        voice_body.addWidget(self.voice)
        self.voice_status = QLabel('Escolha uma voz e ouça antes de aplicar.')
        self.voice_status.setWordWrap(True)
        self.preview = VoicePreviewController(self, lambda active: (
            self.window.on_voice_preview_state(active) if self.window.on_voice_preview_state else None))
        self.voice.preview_theme = resolved_settings_theme(self.theme_id)
        self.preview.status.connect(lambda voice, msg: self.voice_status.setText(f'{voice}: {msg}'))
        self.voice.preview_requested.connect(self.preview.player.request)
        actions = QHBoxLayout()
        self._button(actions, 'Ouvir prévia', lambda: self.preview.player.request(self.voice.currentData()))
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
        voice_body.parentWidget().setMinimumWidth(300)
        devices_body.parentWidget().setMinimumWidth(365)
        columns.setStretch(0, 1)
        columns.setStretch(1, 1)

    def _save_voice(self):
        try:
            voice = self.voice.currentData()
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
        panel = self._embed(self._card(layout, 'Modelos e provedores'),
                            ProvidersOverlay())
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
                            'Configure um serviço por vez. Credenciais permanecem ocultas.')
        sections = self.window.get_plugin_settings() if self.window.get_plugin_settings else []
        if not sections:
            layout.addWidget(QLabel('Nenhum plugin com configurações está carregado.'))
            return
        from gui.overlays import PluginSettingsOverlay
        picker = QComboBox()
        self.plugin_picker = picker
        picker.setAccessibleName('Selecionar integração')
        for section in sections:
            title = section.get('title') or section.get('namespace') or 'Plugin'
            picker.addItem(title.split(' / ')[0].split(' — ')[0])
        layout.addWidget(picker)
        stack = QStackedWidget()
        layout.addWidget(stack)
        panels = {}
        def select(index):
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
        picker.currentIndexChanged.connect(select)
        select(0)

    def _build_security(self, layout):
        layout = self._card(layout, 'Acesso e privacidade')
        self._security_layout = layout
        self._button(layout, 'Gerenciar acesso remoto', self._remote,
                     'Abra o endereço, QR code e gerenciamento da chave de acesso pelo celular.')

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
