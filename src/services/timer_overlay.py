import sys
import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, Property, QPoint, QRect, QSize
from PySide6.QtWidgets import QApplication, QLabel, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QAbstractButton, QSizePolicy
from PySide6.QtGui import QScreen, QMouseEvent, QPainter, QColor, QBrush, QPen

class Switch(QAbstractButton):
    """A custom switch control widget."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(False)
        self._track_color = QColor("#E9E9EA")
        self._thumb_color = QColor(Qt.GlobalColor.white)
        self._track_color_on = QColor("#34C759")
        self.setFixedSize(51, 31)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track_rect = self.rect().adjusted(1, 1, -1, -1)
        thumb_radius = (track_rect.height() / 2) - 1
        track_radius = track_rect.height() / 2

        if self.isChecked():
            painter.setBrush(self._track_color_on)
        else:
            painter.setBrush(self._track_color)
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(track_rect, track_radius, track_radius)

        thumb_x = thumb_radius + 2 if not self.isChecked() else self.width() - thumb_radius - 2

        painter.setPen(QPen(QColor(0, 0, 0, 50), 1))
        painter.setBrush(self._thumb_color)
        painter.drawEllipse(QPoint(thumb_x, self.height() // 2), thumb_radius, thumb_radius)

    def sizeHint(self):
        return QSize(51, 31)


class ControlWidget(QWidget):
    """
    一个迷你的GUI控制面板，包含开始/停止按钮和倒计时显示。
    被设计为在主GUI线程中创建和操作。
    """
    start_requested = Signal()
    stop_requested = Signal()
    exit_requested = Signal()
    enhancement_toggled = Signal(bool)
    
    # 新增信号用于更新转写文本
    transcription_updated = Signal(str)

    def __init__(self, bg_color: str = 'black', text_color: str = 'white', font_size: int = 48):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.remaining_seconds = 0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: rgba(0, 0, 0, 0.7);
                color: {text_color};
                border-radius: 15px;
            }}
            QPushButton {{
                background-color: #555;
                border: none;
                padding: 8px;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: #666;
            }}
            QLabel {{
                padding-left: 5px;
            }}
            #timerLabel {{
                background-color: rgba(20, 20, 20, 0.7);
                border-radius: 10px;
                padding: 5px;
            }}
        """)
        
        self.label_timer = QLabel("Ready", self)
        self.label_timer.setObjectName("timerLabel")
        self.label_timer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        font = self.label_timer.font()
        font.setPointSize(font_size)
        font.setBold(True)
        self.label_timer.setFont(font)
        self.label_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.transcription_label = QLabel("", self)
        font = self.transcription_label.font()
        font.setPointSize(14)
        self.transcription_label.setFont(font)
        self.transcription_label.setWordWrap(True)
        self.transcription_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.transcription_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.transcription_label.hide()
        
        self.start_button = QPushButton("Start Recording", self)
        self.stop_button = QPushButton("Stop Recording", self)
        self.exit_button = QPushButton("Exit", self)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(15, 15, 15, 15)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        
        enhancement_layout = QHBoxLayout()
        enhancement_label = QLabel("增强模式")
        self.enhancement_switch = Switch(self)
        enhancement_layout.addWidget(enhancement_label)
        enhancement_layout.addStretch()
        enhancement_layout.addWidget(self.enhancement_switch)

        main_layout.addWidget(self.label_timer)
        main_layout.addWidget(self.transcription_label)
        main_layout.addLayout(button_layout)
        main_layout.addLayout(enhancement_layout)
        main_layout.addWidget(self.exit_button)
        self.setMinimumWidth(280)

        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self._update_countdown)

        self.keep_on_top_timer = QTimer(self)
        self.keep_on_top_timer.timeout.connect(self._ensure_on_top)
        self.keep_on_top_timer.setInterval(500)

        self.start_button.clicked.connect(self.start_requested.emit)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.exit_button.clicked.connect(self.exit_requested.emit)
        self.enhancement_switch.toggled.connect(self.enhancement_toggled.emit)

        self.set_idle_state()
        self.drag_pos: Optional[QMouseEvent] = None
        self._center_on_screen()

    def set_enhancement_state(self, enabled: bool):
        self.enhancement_switch.setChecked(enabled)

    def _ensure_on_top(self):
        """主动将窗口提升到顶层，确保其可见性。"""
        if self.isVisible():
            self.raise_()
            self.activateWindow()


    def set_idle_state(self):
        self.logger.info("UI set to idle state.")
        self.countdown_timer.stop()
        self.keep_on_top_timer.stop()
        self.label_timer.setText("Ready")
        self.start_button.show()
        self.stop_button.hide()
        self.transcription_label.hide()
        self.transcription_label.clear()

    def _update_countdown(self):
        self.remaining_seconds -= 1
        self.label_timer.setText(str(self.remaining_seconds))
        if self.remaining_seconds <= 0:
            self.stop_requested.emit()

    def update_transcription(self, text: str, append: bool = False):
        """更新转写文本内容"""
        if append:
            current_text = self.transcription_label.text()
            new_text = f"{current_text} {text}".strip()
            self.transcription_label.setText(new_text)
        else:
            self.transcription_label.setText(text)
        
        if text and not self.transcription_label.isVisible():
            self.transcription_label.show()
        
        self.adjustSize()
    
    def set_recording_state(self, seconds: int):
        self.logger.info(f"UI set to recording state for {seconds} seconds.")
        self.remaining_seconds = seconds
        self.label_timer.setText(str(self.remaining_seconds))
        self.start_button.hide()
        self.stop_button.show()
        self.label_timer.show()
        self.transcription_label.clear()
        self.transcription_label.show()
        self.countdown_timer.start(1000)
        self.keep_on_top_timer.start()
    
    def set_finished_state(self, final_text: str):
        """设置录音完成状态，显示最终转写文本"""
        self.logger.info("UI set to finished state.")
        self.countdown_timer.stop()
        self.keep_on_top_timer.stop()
        self.start_button.show()
        self.stop_button.hide()
        self.update_transcription(final_text, append=False)
    
    def _center_on_screen(self):
        try:
            primary_screen = QApplication.primaryScreen()
            if primary_screen:
                screen_geometry = primary_screen.availableGeometry()
                self.move(screen_geometry.width() - self.width() - 20, 20)
        except Exception as e:
            self.logger.error(f"Could not center window on screen: {e}")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_pos:
            self.move(self.pos() + event.globalPosition().toPoint() - self.drag_pos)
            self.drag_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.drag_pos = None