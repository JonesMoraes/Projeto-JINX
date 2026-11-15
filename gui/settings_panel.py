"""Single Qt settings window: searchable navigation and existing runtime forms.

Forms are created on demand on the Qt thread. Each form retains its existing
save/reconnect contract; theme changes only write the settings_theme key.
"""
import re
import unicodedata
from weakref import WeakKeyDictionary

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPalette
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from gui.style import hud_font
from gui.theme import C
from gui.settings_themes import SETTINGS_THEMES, DEFAULT_SETTINGS_THEME, settings_theme_id
from memory import config_manager as config


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.casefold())
                   if unicodedata.category(c) != 'Mn')


# Search terms describe controls, not just category titles.
CATEGORIES = (
    ('general', 'Geral', 'Identidade e personalização', 'nome usuario assistente voz cor'),
    ('appearance', 'Aparência', 'Escolha o seu ambiente', 'tema cyber minimal nature titanium neon hud visual'),
    ('audio', 'Voz e áudio', 'Voz, microfone e saída de som', 'volume dispositivos teste entrada saida gemini previa'),
    ('ai', 'Inteligência artificial', 'Mecanismo e provedores', 'modelo stt llm tts api chave token ollama pipeline'),
    ('memory', 'Memória', 'Informações que a JINX lembra', 'esquecer excluir dados lembrancas'),
    ('automation', 'Automação', 'Agenda e controles do dia a dia', 'eventos calendario resumo gestos camera palavra de ativacao wake push to talk pressionar falar'),
    ('integrations', 'Integrações', 'Configure um plugin por vez', 'plugins spotify discord google trello contas'),
    ('security', 'Segurança', 'Acesso remoto', 'celular chave acesso token remoto'),
    ('system', 'Sistema', 'Inicialização e manutenção', 'atalho windows iniciar carregados plugins'),
)


class ThemePreview(QWidget):
    """Small native preview; no network assets or image dependencies."""
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setFixedHeight(68)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        t = self.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(t.bg))
        p.fillRect(8, 8, 42, 52, QColor(t.panel))
        p.fillRect(13, 17, 29, 5, QColor(t.accent))
        p.fillRect(13, 30, 23, 3, QColor(t.muted))
        p.fillRect(13, 42, 27, 3, QColor(t.muted))
        p.setPen(QPen(QColor(t.border)))
        p.setBrush(QColor(t.panel))
        p.drawRoundedRect(60, 9, max(40, self.width() - 70), 49, t.radius / 2, t.radius / 2)
        p.fillRect(70, 19, max(20, self.width() - 100), 4, QColor(t.text))
        p.fillRect(70, 32, 38, 3, QColor(t.muted))
        p.fillRect(70, 43, 44, 6, QColor(t.accent))


class SettingsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setObjectName('SettingsCentral')
        self.setWindowTitle('JINX — Configurações')
        self.setFont(hud_font(9))
        self.resize(1000, 720)
        self.setMinimumSize(760, 540)
        self.theme_id = settings_theme_id(config.load_api_keys().get('settings_theme'))
        self._pages = {}
        self._embedded = []
        self._original_styles = WeakKeyDictionary()
        self._source_palettes = WeakKeyDictionary()
        self._styling = False
        self._current = 'general'
        self._theme_buttons = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 20, 16, 16)
        header = QHBoxLayout()
        brand = QLabel('JINX  /  Configurações')
        brand.setFont(hud_font(16, QFont.Weight.Bold))
        header.addWidget(brand)
        header.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Buscar configurações…')
        self.search.setAccessibleName('Buscar configurações')
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(290)
        header.addWidget(self.search)
        root.addLayout(header)
        root.addSpacing(14)
        body = QHBoxLayout()
        body.setSpacing(12)
        self.navigation = QListWidget()
        self.navigation.setFixedWidth(175)
        self.navigation.setAccessibleName('Categorias de configuração')
        for key, title, description, terms in CATEGORIES:
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setToolTip(description)
            self.navigation.addItem(item)
        body.addWidget(self.navigation)
        right = QVBoxLayout()
        self.heading = QLabel()
        self.heading.setFont(hud_font(20, QFont.Weight.Bold))
        self.subtitle = QLabel()
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
        footer = QHBoxLayout()
        self.status = QLabel('Use Aplicar ou Salvar em cada painel para confirmar alterações.')
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        close = QPushButton('Fechar')
        close.clicked.connect(self.close)
        footer.addWidget(close)
        root.addLayout(footer)
        self.navigation.currentItemChanged.connect(self._selected)
        self.search.textChanged.connect(self._search)
        self.navigation.setCurrentRow(0)
        self._apply_theme()
        QApplication.instance().installEventFilter(self)

    def _button(self, layout, title, callback, description=''):
        button = QPushButton(title)
        button.setMinimumHeight(38)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda checked=False: callback())
        layout.addWidget(button)
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
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 8, 4)
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
        grid = QGridLayout()
        grid.setSpacing(12)
        for index, (key, theme) in enumerate(SETTINGS_THEMES.items()):
            card = QPushButton()
            card.setCheckable(True)
            card.setMinimumHeight(137)
            card.setAccessibleName(theme.name)
            card.setToolTip(theme.description)
            inner = QVBoxLayout(card)
            inner.setContentsMargins(12, 10, 12, 10)
            inner.addWidget(ThemePreview(theme))
            label = QLabel(theme.name)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            inner.addWidget(label)
            card.clicked.connect(lambda checked=False, k=key: self.select_theme(k))
            self._theme_buttons[key] = card
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        self._button(layout, 'Restaurar Cyber HUD', lambda: self.select_theme(DEFAULT_SETTINGS_THEME))
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
            self.status.setText('Cor do HUD aplicada e salva.')
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
        self._apply_theme()
        self.status.setText(f'Tema {SETTINGS_THEMES[key].name} aplicado e salvo.')

    def _sync_theme_buttons(self):
        for key, button in self._theme_buttons.items():
            button.setChecked(key == self.theme_id)

    def _build_audio(self, layout):
        from gui.overlays import AudioDeviceOverlay
        from gui.voice_preview import VoicePicker, VoicePreviewController
        layout.addWidget(QLabel('Voz Gemini • a prévia não muda a voz ativa'))
        self.voice = VoicePicker()
        for name in config.AVAILABLE_VOICES:
            self.voice.addItem(f'{name} — {config.VOICE_STYLES[name]}', name)
        self.voice.setCurrentIndex(max(0, self.voice.findData(config.get_voice())))
        layout.addWidget(self.voice)
        self.voice_status = QLabel('Escolha uma voz e ouça antes de aplicar.')
        self.voice_status.setWordWrap(True)
        self.preview = VoicePreviewController(self, lambda active: (
            self.window.on_voice_preview_state(active) if self.window.on_voice_preview_state else None))
        self.voice.preview_theme = SETTINGS_THEMES[self.theme_id]
        self.preview.status.connect(lambda voice, msg: self.voice_status.setText(f'{voice}: {msg}'))
        self.voice.preview_requested.connect(self.preview.player.request)
        actions = QHBoxLayout()
        self._button(actions, 'Ouvir prévia', lambda: self.preview.player.request(self.voice.currentData()))
        self._button(actions, 'Parar', self.preview.player.stop)
        self._button(actions, 'Aplicar voz', self._save_voice)
        layout.addLayout(actions)
        layout.addWidget(self.voice_status)
        audio = self._embed(layout, AudioDeviceOverlay())
        audio.picked.connect(self.window._on_audio_devices_applied)

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
        panel = self._embed(layout, ProvidersOverlay())
        panel.changed.connect(self.window._on_providers_applied)

    def _build_memory(self, layout):
        from gui.overlays import MemoryOverlay
        self._embed(layout, MemoryOverlay())

    def _build_automation(self, layout):
        self._button(layout, 'Abrir agenda', lambda: self._open_extra('agenda'),
                     'Eventos locais e sincronização manual com Google Agenda.')
        for attribute, callback in (('_brief_btn', '_toggle_brief'), ('_wake_btn', '_toggle_wake_word'),
                                    ('_ptt_btn', '_toggle_ptt'), ('_gesture_btn', '_toggle_gestures')):
            source = getattr(self.window, attribute, None)
            if source is not None:
                button = self._button(layout, source.text(), getattr(self.window, callback))
                # Existing runtime refreshes these labels, including asynchronous wake setup.
                timer = QTimer(button)
                timer.timeout.connect(lambda b=button, s=source: b.setText(s.text()))
                timer.start(500)

    def _build_integrations(self, layout):
        sections = self.window.get_plugin_settings() if self.window.get_plugin_settings else []
        if not sections:
            layout.addWidget(QLabel('Nenhum plugin com configurações está carregado.'))
            return
        from gui.overlays import PluginSettingsOverlay
        picker = QComboBox()
        self.plugin_picker = picker
        picker.setAccessibleName('Selecionar integração')
        for section in sections:
            picker.addItem(section.get('title') or section.get('namespace') or 'Plugin')
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
        self._button(layout, 'Criar atalho na área de trabalho', self.window._create_desktop_shortcut)
        button = self._button(layout, self.window._autostart_btn.text(), self.window._toggle_autostart)
        button.clicked.connect(lambda: button.setText(self.window._autostart_btn.text()))
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
        t = SETTINGS_THEMES[self.theme_id]
        self._styling = True
        self.setStyleSheet(f'''
            QDialog#SettingsCentral {{ background: {t.bg}; }}
            QWidget {{ color: {t.text}; }}
            QLabel {{ background: transparent; }}
            QScrollArea, QStackedWidget, QScrollArea > QWidget > QWidget {{ background: {t.bg}; border: none; }}
            QListWidget {{ background: {t.panel}; border: none; border-radius: {t.radius}px; padding: 8px; }}
            QListWidget::item {{ padding: 12px 8px; border-radius: {t.radius}px; }}
            QListWidget::item:selected {{ background: {t.selected}; color: {t.accent}; }}
            QPushButton {{ background: {t.panel}; color: {t.text}; border: 1px solid {t.border};
                border-radius: {t.radius}px; padding: 7px 12px; }}
            QPushButton:hover, QPushButton:focus {{ border-color: {t.accent}; }}
            QPushButton:checked {{ background: {t.selected}; border: 2px solid {t.accent}; }}
            QLineEdit, QComboBox, QTextEdit, QTableWidget {{ background: {t.field}; color: {t.text};
                border: 1px solid {t.border}; border-radius: {t.radius}px; padding: 7px; }}
            QComboBox QAbstractItemView {{ background: {t.panel}; color: {t.text}; selection-background-color: {t.selected}; }}
            QScrollBar:vertical {{ background: {t.bg}; width: 10px; }}
            QScrollBar::handle:vertical {{ background: {t.border}; min-height: 24px; border-radius: 4px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        ''')
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
        t = SETTINGS_THEMES[self.theme_id]
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

    def _restyle_forms(self):
        for panel in self._embedded:
            for widget in [panel, *panel.findChildren(QWidget)]:
                self._restyle_widget(widget)

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
