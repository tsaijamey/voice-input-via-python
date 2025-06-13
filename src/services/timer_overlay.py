import sys
import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QLabel, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QCheckBox
from PySide6.QtGui import QScreen, QMouseEvent

class ControlWidget(QWidget):
    """
    一个迷你的GUI控制面板，包含开始/停止按钮和倒计时显示。
    被设计为在主GUI线程中创建和操作。
    """
    start_requested = Signal()
    stop_requested = Signal()
    exit_requested = Signal()
    enhancement_toggled = Signal(bool)

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
                background-color: {bg_color};
                color: {text_color};
                border-radius: 10px;
            }}
            QPushButton {{
                background-color: #555;
                border: 1px solid #777;
                padding: 5px;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: #666;
            }}
        """)
        
        self.label_timer = QLabel("Ready", self)
        font = self.label_timer.font()
        font.setPointSize(font_size)
        font.setBold(True)
        self.label_timer.setFont(font)
        self.label_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.start_button = QPushButton("Start Recording", self)
        self.stop_button = QPushButton("Stop Recording", self)
        self.exit_button = QPushButton("Exit", self)
        self.enhancement_checkbox = QCheckBox("启用增强", self)

        main_layout = QVBoxLayout(self)
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.exit_button)
        
        main_layout.addWidget(self.label_timer)
        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.enhancement_checkbox) # 添加复选框到布局
        self.resize(250, 180)

        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self._update_countdown)

        # 新增：用于强制保持窗口在顶层的定时器
        self.keep_on_top_timer = QTimer(self)
        self.keep_on_top_timer.timeout.connect(self._ensure_on_top)
        self.keep_on_top_timer.setInterval(500) # 每500毫秒检查一次

        self.start_button.clicked.connect(self.start_requested.emit)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.exit_button.clicked.connect(self.exit_requested.emit)
        self.enhancement_checkbox.stateChanged.connect(self.enhancement_state_changed)

        self.set_idle_state()
        self.drag_pos: Optional[QMouseEvent] = None
        self._center_on_screen()

    def enhancement_state_changed(self, state):
        self.enhancement_toggled.emit(state == Qt.CheckState.Checked.value)

    def set_enhancement_state(self, enabled: bool):
        self.enhancement_checkbox.setChecked(enabled)

    def _ensure_on_top(self):
        """主动将窗口提升到顶层，确保其可见性。"""
        if self.isVisible():
            self.raise_()
            self.activateWindow()

    def set_recording_state(self, seconds: int):
        self.logger.info(f"UI set to recording state for {seconds} seconds.")
        self.remaining_seconds = seconds
        self.label_timer.setText(str(self.remaining_seconds))
        self.start_button.hide()
        self.stop_button.show()
        self.label_timer.show()
        self.countdown_timer.start(1000)
        self.keep_on_top_timer.start() # 录音时开始强制置顶

    def set_idle_state(self):
        self.logger.info("UI set to idle state.")
        self.countdown_timer.stop()
        self.keep_on_top_timer.stop() # 空闲时停止强制置顶
        self.label_timer.setText("Ready")
        self.start_button.show()
        self.stop_button.hide()

    def _update_countdown(self):
        self.remaining_seconds -= 1
        self.label_timer.setText(str(self.remaining_seconds))
        if self.remaining_seconds <= 0:
            self.stop_requested.emit()

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