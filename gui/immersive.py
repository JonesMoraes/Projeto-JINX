"""Qt-thread-only orb mode, compact notices and expandable result panels."""
from collections import OrderedDict
import threading
import unicodedata

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QTextBrowser, QVBoxLayout, QWidget

from gui.style import btn_css, px_font, scroll_css
from gui.theme import C


class PopupToast(QFrame):
    opened = pyqtSignal(str)
    dismissed = pyqtSignal(str)

    def __init__(self, key, parent):
        super().__init__(parent)
        self.key = key
        self.setObjectName('OrbToast')
        self.setFixedSize(268, 76)
        self.setStyleSheet(f'QFrame#OrbToast {{background:{C.PANEL}; border:1px solid {C.BORDER_B}; border-radius:8px;}}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 8, 9, 7)
        layout.setSpacing(3)
        row = QHBoxLayout()
        self.title = QLabel()
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setFont(px_font(12, QFont.Weight.DemiBold))
        self.title.setStyleSheet(f'color:{C.WHITE}; border:0; background:transparent;')
        row.addWidget(self.title, 1)
        self.open_button = QPushButton('Abrir')
        self.open_button.setFont(px_font(11))
        self.open_button.setStyleSheet(btn_css('dim'))
        self.open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_button.clicked.connect(lambda: self.opened.emit(key))
        row.addWidget(self.open_button)
        close = QPushButton('×')
        close.setFixedSize(20, 20)
        close.setFont(px_font(14))
        close.setStyleSheet(f'color:{C.TEXT_MED}; border:0; background:transparent;')
        close.setToolTip('Dispensar aviso; o resultado continua no histórico')
        close.clicked.connect(lambda: self.dismissed.emit(key))
        row.addWidget(close)
        layout.addLayout(row)
        self.preview = QLabel()
        self.preview.setTextFormat(Qt.TextFormat.PlainText)
        self.preview.setFont(px_font(11))
        self.preview.setStyleSheet(f'color:{C.TEXT_MED}; border:0; background:transparent;')
        layout.addWidget(self.preview)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def update_notice(self, title, preview, persistent=False):
        self.title.setText(self.title.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, 155))
        self.title.setToolTip(title)
        self.open_button.setToolTip(f'Abrir pop-up {self.key}: {title}')
        self.preview.setText(self.preview.fontMetrics().elidedText(' '.join(preview.split()), Qt.TextElideMode.ElideRight, 244))
        self.timer.stop()
        if not persistent:
            self.timer.start(7000)


class ResultPopup(QFrame):
    collapsed = pyqtSignal()
    enlarged = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('OrbResult')
        self.setStyleSheet(f'QFrame#OrbResult {{background:{C.PANEL}; border:1px solid {C.BORDER_B}; border-radius:10px;}}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        header = QHBoxLayout()
        self.title = QLabel()
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setFont(px_font(13, QFont.Weight.DemiBold))
        self.title.setMinimumWidth(0)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.title.setStyleSheet(f'color:{C.WHITE}; background:transparent;')
        header.addWidget(self.title, 1)
        for text, tip, signal in (('⛶', 'Ampliar ou reduzir', self.enlarged),
                                   ('—', 'Recolher para o orb', self.collapsed),
                                   ('×', 'Fechar pop-up', self.collapsed)):
            button = QPushButton(text)
            button.setFixedSize(28, 26)
            button.setFont(px_font(13))
            button.setToolTip(tip)
            button.setStyleSheet(btn_css('dim'))
            button.clicked.connect(lambda _checked=False, event=signal: event.emit())
            header.addWidget(button)
        layout.addLayout(header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet('QScrollArea {background:transparent; border:0;}' + scroll_css())
        container = QWidget()
        self.body = QVBoxLayout(container)
        self.body.setContentsMargins(0, 3, 0, 0)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        self.text.setOpenExternalLinks(False)
        self.text.setFont(px_font(13))
        self.text.setMinimumHeight(180)
        self.text.setStyleSheet(f'QTextBrowser {{background:transparent; color:{C.TEXT}; border:0;}}' + scroll_css())
        self.body.addWidget(self.text)
        self.hide()


class OrbMode(QObject):
    LIMIT = 24

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.active = False
        self.entries = OrderedDict()
        self.toasts = OrderedDict()
        self.serial = 0
        self.current = None
        self.borrowed = None
        self.large = False
        self.saved = {}
        self.popup = ResultPopup(window.centralWidget())
        self.popup.collapsed.connect(self.close_popup)
        self.popup.enlarged.connect(self.toggle_size)
        self.command = QLineEdit(window.centralWidget())
        self.command.setPlaceholderText('Peça uma função ou diga: abra o último pop-up…')
        self.command.setFont(px_font(13))
        self.command.setStyleSheet(f'background:{C.PANEL}; color:{C.WHITE}; border:1px solid {C.BORDER_B}; border-radius:8px; padding:8px;')
        self.command.returnPressed.connect(self.submit_command)
        self.command.hide()
        self._snapshot()

    def _snapshot(self):
        # Replace as a whole; workers read only a deep copy of this plain data.
        self.window._display_snapshot = {
            'fullscreen': self.active, 'open_popup': self.current,
            'popups': [{'id': key, 'title': row['title'], 'kind': row['kind']}
                       for key, row in self.entries.items()]}

    def publish(self, kind, title, preview='', payload=None, persistent=False):
        # Interactive surfaces have one live instance; never reopen an old quiz,
        # expired confirmation or a replaced video under a stale title.
        match = next((key for key, row in self.entries.items()
                      if row['kind'] == kind and (kind != 'content' or row['title'] == title)), None)
        if match is None:
            self.serial += 1
            match = str(self.serial)
        elif self.current == match and kind in ('quiz', 'capture'):
            self.close_popup()
        self.entries[match] = {'kind': kind, 'title': str(title)[:160],
                               'preview': str(preview)[:240], 'payload': payload}
        self.entries.move_to_end(match)
        while len(self.entries) > self.LIMIT:
            victim = next(key for key, row in self.entries.items()
                          if row['kind'] not in ('camera', 'confirm') and key != self.current)
            self.remove(victim)
        if self.active:
            toast = self.toasts.get(match)
            if toast is None:
                toast = PopupToast(match, self.window.centralWidget())
                toast.opened.connect(self.open_popup)
                toast.dismissed.connect(self.dismiss)
                self.toasts[match] = toast
            toast.update_notice(str(title), str(preview), persistent)
            toast.show()
            toast.raise_()
            self.toasts.move_to_end(match)
            # At most three tiny cards, with bounded widget/payload history.
            while len(self.toasts) > 3:
                key = next(key for key in self.toasts if self.entries[key]['kind'] not in ('camera', 'confirm'))
                old = self.toasts.pop(key)
                old.hide(); old.deleteLater()
            self.reposition()
        self._snapshot()
        return match

    def capture_panel(self, panel):
        w = self.window
        if panel is w._quiz_panel:
            return self.publish('quiz', w._quiz_title_lbl.text(), 'Questionário pronto · abrir para responder', persistent=True)
        return self.publish('content', w._content_title_lbl.text(), w._content_display.toPlainText(),
                            {'html': w._content_display.toHtml()[:160000]})

    def remove(self, key):
        if self.current == key:
            self.close_popup()
        self.entries.pop(key, None)
        toast = self.toasts.pop(key, None)
        if toast:
            toast.hide(); toast.deleteLater()
        self._snapshot()

    def remove_kind(self, kind):
        for key, row in list(self.entries.items()):
            if row['kind'] == kind:
                self.remove(key)

    def dismiss(self, key):
        row = self.entries.get(key)
        if row and row['kind'] == 'camera':
            self.window.stop_camera_stream()
            self.window._on_cam_stream(False)
        toast = self.toasts.get(key)
        if toast:
            toast.hide()

    def set_active(self, active):
        active = bool(active)
        if active == self.active:
            return
        w = self.window
        if active:
            widgets = (w._header, w._left_panel, w._right_panel, w._status_strip,
                       w._content_panel, w._quiz_panel)
            margins = w._body_layout.contentsMargins()
            self.saved = {'widgets': [(item, not item.isHidden()) for item in widgets],
                          'style': w.hud.hud_style, 'sizes': w._center_split.sizes(),
                          'handle': w._center_split.handleWidth(),
                          'margins': (margins.left(), margins.top(), margins.right(), margins.bottom()),
                          'spacing': w._body_layout.spacing()}
            self.active = True
            for item, _ in self.saved['widgets']:
                item.hide()
            for name in ('_quick_drawer', '_ctrl_drawer', '_clipboard_panel', '_cam_preview'):
                widget = getattr(w, name, None)
                if widget is not None: widget.hide()
            w._body_layout.setContentsMargins(0, 0, 0, 0)
            w._body_layout.setSpacing(0)
            w._center_split.setHandleWidth(0)
            w.hud.immersive = True
            # Preserve the selected sphere; only the face becomes a native orb.
            if w.hud.hud_style == 'face':
                w.hud.hud_style = 'core'
            w.hud._sync_hud_style()
            w._hud_cam_stack.setCurrentIndex(0)
            for item, visible in self.saved['widgets']:
                if visible and item in (w._content_panel, w._quiz_panel):
                    self.capture_panel(item)
            if w._video_on:
                self.publish('media', w._video_title.text(), 'Mídia disponível · abrir para visualizar')
            if getattr(w, '_cam_stream_active', False):
                self.publish('camera', 'Câmera ativa', 'Abrir câmera · × encerra captura', persistent=True)
            if w._confirm_overlay is not None:
                w._confirm_overlay.hide()
                self.publish('confirm', 'Confirmação necessária', 'Abrir para revisar e decidir no HUD', persistent=True)
        else:
            self.command.hide()
            self.close_popup()
            self.active = False
            for toast in self.toasts.values(): toast.hide()
            for item, visible in self.saved.get('widgets', []):
                if item is w._quiz_panel and w._quiz is None: visible = False
                item.setVisible(visible)
            w.hud.immersive = False
            w.hud.hud_style = self.saved.get('style', 'face')
            w.hud._sync_hud_style()
            w._body_layout.setContentsMargins(*self.saved.get('margins', (10, 10, 10, 10)))
            w._body_layout.setSpacing(self.saved.get('spacing', 10))
            w._center_split.setHandleWidth(self.saved.get('handle', 10))
            w._center_split.setSizes(self.saved.get('sizes', []))
            w._hud_cam_stack.setCurrentIndex(2 if w._video_on else 1 if getattr(w, '_cam_stream_active', False) else 0)
            if w._confirm_overlay is not None: w._centre_overlay(w._confirm_overlay)
            w._refresh_hud_btn()
        w.hud.update()
        self._snapshot()
        self.reposition()

    def resolve(self, target=''):
        def folded(text):
            return ''.join(c for c in unicodedata.normalize('NFKD', str(text).casefold()) if not unicodedata.combining(c))
        value = folded(str(target or '').strip())
        if not value or value in ('último', 'ultimo', 'last', 'latest'):
            if not self.entries: raise ValueError('Nenhum pop-up disponível / No popup available')
            return next(reversed(self.entries))
        if value in self.entries: return value
        exact = [key for key, row in self.entries.items() if folded(row['title']) == value]
        matches = exact or [key for key, row in self.entries.items() if value in folded(row['title'])]
        if len(matches) != 1:
            raise ValueError('Pop-up não encontrado ou nome ambíguo; use o ID / Use an exact popup ID')
        return matches[0]

    def open_popup(self, target=''):
        key = self.resolve(target)
        row = self.entries[key]
        self.close_popup()
        w = self.window
        kind = row['kind']
        widget = None
        restore = None
        if kind == 'quiz':
            if w._quiz is None: raise ValueError('Questionário encerrado / Quiz ended')
            widget = w._quiz_panel
            restore = lambda: w._center_split.insertWidget(2, widget)
        elif kind == 'media':
            if not w._video_on: raise ValueError('Mídia encerrada / Media closed')
            widget = w._video_cont
            restore = lambda: w._hud_cam_stack.insertWidget(2, widget)
        elif kind == 'camera':
            if not w._cam_stream_active: raise ValueError('Câmera encerrada / Camera stopped')
            widget = w._cam_cont
            restore = lambda: w._hud_cam_stack.insertWidget(1, widget)
        elif kind == 'confirm':
            widget = w._confirm_overlay
            if widget is None: raise ValueError('Confirmação encerrada / Confirmation ended')
            restore = lambda: widget.setParent(w.centralWidget())
        elif kind == 'capture':
            widget = w._cam_preview
            restore = lambda: widget.setParent(w.centralWidget())
        self.popup.title.setText(row['title'])
        self.popup.title.setToolTip(row['title'])
        self.popup.text.setVisible(widget is None)
        if widget is not None:
            visible = not widget.isHidden()
            self.popup.body.addWidget(widget)
            widget.show()
            self.borrowed = (widget, restore, visible)
        else:
            self.popup.text.setHtml((row['payload'] or {}).get('html', ''))
        self.current = key
        self.large = False
        self.popup.show()
        self.popup.raise_()
        self.reposition()
        if kind == 'media': w._fit_video()
        self._snapshot()
        return key

    def close_popup(self):
        if self.borrowed is not None:
            widget, restore, visible = self.borrowed
            self.borrowed = None
            self.popup.body.removeWidget(widget)
            widget.hide()
            restore()
            widget.setVisible(visible and not self.active)
        self.popup.hide()
        self.current = None
        self._snapshot()

    def toggle_size(self):
        self.large = not self.large
        self.reposition()
        if self.current and self.entries[self.current]['kind'] == 'media': self.window._fit_video()

    def reposition(self):
        area = self.window.centralWidget().rect()
        width, height = area.width(), area.height()
        self.command.setGeometry(max(8, (width - min(480, width - 32)) // 2), max(8, height - 78), min(480, width - 32), 44)
        if self.popup.isVisible():
            pw = min(width - 32, 880 if self.large else 580)
            ph = min(height - 48, 680 if self.large else 440)
            self.popup.setGeometry(max(8, (width - pw) // 2), max(8, (height - ph) // 2), max(180, pw), max(100, ph))
            if self.current and self.entries[self.current]['kind'] == 'media':
                QTimer.singleShot(0, self.window._fit_video)
        for index, toast in enumerate(reversed(list(self.toasts.values()))):
            toast.move(max(8, width - toast.width() - 18), max(8, height - 18 - (index + 1) * 84))

    def show_command(self):
        if not self.active:
            self.window._input.setFocus()
            return
        self.command.setVisible(not self.command.isVisible())
        if self.command.isVisible():
            self.reposition()
            self.command.raise_()
            self.command.setFocus()

    def submit_command(self):
        text = self.command.text().strip()
        self.command.clear()
        self.command.hide()
        if not text: return
        from core.display_commands import parse
        command = parse(text)
        if command:
            self.control(*command)
        elif self.window.on_text_command:
            self.window._log.append_log('Você: ' + text)
            threading.Thread(target=self.window.on_text_command, args=(text,), daemon=True).start()

    def control(self, action, target='', receipt=None):
        result = {'ok': False, 'reason': 'Display update interrupted'}
        try:
            if action == 'fullscreen': self.window.showFullScreen(); self.set_active(True)
            elif action == 'windowed': self.window._leave_fullscreen(); self.set_active(False)
            elif action == 'open_popup': self.open_popup(target)
            elif action == 'close_popup': self.close_popup()
            elif action == 'expand_popup':
                if self.current is None: self.open_popup(target)
                self.large = True; self.reposition()
            else: raise ValueError('Ação de tela inválida / Invalid display action')
            result = {'ok': True, 'popup': self.current}
        except ValueError as exc:
            result = {'ok': False, 'reason': str(exc)}
        except Exception:
            result = {'ok': False, 'reason': 'Não foi possível atualizar a tela / Could not update display'}
        finally:
            if receipt is not None:
                receipt['result'] = result
                receipt['ready'].set()
        return result
