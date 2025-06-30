import sys
import logging
from typing import Optional, List
from enum import Enum, auto
from PySide6.QtCore import Qt, QTimer, Signal, QPoint, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (QApplication, QLabel, QWidget, QPushButton, QVBoxLayout, 
                               QHBoxLayout, QAbstractButton, QSizePolicy, QScrollArea, QFrame)
from PySide6.QtGui import QScreen, QMouseEvent, QPainter, QColor, QBrush, QPen, QFont

class TextProcessingState(Enum):
    """文本处理UI状态枚举"""
    HIDDEN = auto()          # 隐藏状态
    PROCESSING = auto()      # 处理中状态
    TRANSLATION_RESULT = auto()  # 显示翻译结果
    STYLE_SELECTION = auto() # 风格选择状态
    STYLE_RESULT = auto()    # 风格化结果
    ERROR = auto()           # 错误状态

class StyleButton(QPushButton):
    """风格选择按钮"""
    def __init__(self, style_name: str, parent=None):
        super().__init__(style_name, parent)
        self.style_name = style_name
        self.setFixedHeight(35)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                background-color: #4A90E2;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #357ABD;
            }
            QPushButton:pressed {
                background-color: #2E6DA4;
            }
        """)

class TextProcessingOverlay(QWidget):
    """
    文本处理专用的独立UI界面
    在屏幕中央显示，提供翻译和风格化处理的完整流程界面
    """
    # 信号定义
    style_selected = Signal(str)  # 风格选择信号
    close_requested = Signal()    # 关闭请求信号
    copy_to_clipboard = Signal(str)  # 复制到剪贴板信号
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self._state = TextProcessingState.HIDDEN
        self._current_translation_result = None
        self._style_options = []
        
        self._setup_ui()
        self._setup_animations()
        self._center_on_screen()
        
    def _setup_ui(self):
        """设置UI界面"""
        # 窗口设置
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 主容器
        self.main_container = QFrame(self)
        self.main_container.setObjectName("mainContainer")
        self.main_container.setStyleSheet("""
            QFrame#mainContainer {
                background-color: rgba(40, 40, 40, 0.95);
                border-radius: 15px;
                border: 2px solid rgba(255, 255, 255, 0.1);
            }
            QLabel {
                color: white;
                background-color: transparent;
            }
            QPushButton {
                background-color: #555;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #666;
            }
            QPushButton:pressed {
                background-color: #444;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollArea QWidget {
                background-color: transparent;
            }
        """)
        
        # 主布局
        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.main_container)
        
        main_layout = QVBoxLayout(self.main_container)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题栏
        title_layout = QHBoxLayout()
        self.title_label = QLabel("文本处理")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.close_button = QPushButton("×")
        self.close_button.setFixedSize(30, 30)
        self.close_button.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                border-radius: 15px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
        """)
        self.close_button.clicked.connect(self.hide_overlay)
        
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.close_button)
        
        # 状态标签
        self.status_label = QLabel("正在处理...")
        status_font = QFont()
        status_font.setPointSize(12)
        self.status_label.setFont(status_font)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #3498DB;")
        
        # 内容区域（可滚动）
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setMaximumHeight(300)
        
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(10)
        
        # 文本显示区域
        self.text_display = QLabel()
        self.text_display.setWordWrap(True)
        self.text_display.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.text_display.setStyleSheet("""
            QLabel {
                background-color: rgba(60, 60, 60, 0.8);
                border-radius: 8px;
                padding: 12px;
                color: white;
                line-height: 1.4;
            }
        """)
        text_font = QFont()
        text_font.setPointSize(11)
        self.text_display.setFont(text_font)
        
        # 风格选择区域
        self.style_container = QWidget()
        self.style_layout = QVBoxLayout(self.style_container)
        self.style_layout.setSpacing(8)
        
        self.style_title = QLabel("选择文本风格：")
        style_title_font = QFont()
        style_title_font.setPointSize(12)
        style_title_font.setBold(True)
        self.style_title.setFont(style_title_font)
        self.style_title.setStyleSheet("color: #F39C12;")
        
        self.style_buttons_layout = QVBoxLayout()
        self.style_buttons_layout.setSpacing(8)
        
        self.style_layout.addWidget(self.style_title)
        self.style_layout.addLayout(self.style_buttons_layout)
        
        # 操作按钮区域
        self.action_buttons_layout = QHBoxLayout()
        self.action_buttons_layout.setSpacing(10)
        
        self.copy_button = QPushButton("复制结果")
        self.copy_button.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                padding: 10px 20px;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        self.copy_button.clicked.connect(self._on_copy_clicked)
        
        self.new_process_button = QPushButton("处理新文本")
        self.new_process_button.clicked.connect(self.hide_overlay)
        
        self.action_buttons_layout.addWidget(self.copy_button)
        self.action_buttons_layout.addWidget(self.new_process_button)
        
        # 添加到内容布局
        self.content_layout.addWidget(self.text_display)
        self.content_layout.addWidget(self.style_container)
        self.content_layout.addLayout(self.action_buttons_layout)
        
        self.scroll_area.setWidget(self.content_widget)
        
        # 添加到主布局
        main_layout.addLayout(title_layout)
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.scroll_area)
        
        # 设置初始大小
        self.setFixedSize(500, 400)
        
        # 初始隐藏所有组件
        self._hide_all_content()
        
    def _setup_animations(self):
        """设置动画效果"""
        self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_animation.setDuration(300)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
    def _center_on_screen(self):
        """将窗口居中显示"""
        try:
            primary_screen = QApplication.primaryScreen()
            if primary_screen:
                screen_geometry = primary_screen.availableGeometry()
                x = (screen_geometry.width() - self.width()) // 2
                y = (screen_geometry.height() - self.height()) // 2
                self.move(x, y)
        except Exception as e:
            self.logger.error(f"Could not center window on screen: {e}")
            
    def _hide_all_content(self):
        """隐藏所有内容组件"""
        self.status_label.hide()
        self.scroll_area.hide()
        self.text_display.hide()
        self.style_container.hide()
        self.copy_button.hide()
        self.new_process_button.hide()
        
    def show_processing_state(self):
        """显示处理中状态"""
        self._state = TextProcessingState.PROCESSING
        self.logger.info("Text processing overlay: showing processing state")
        
        self._hide_all_content()
        self.status_label.setText("正在处理选中的文本...")
        self.status_label.show()
        
        self.show()
        self.raise_()
        self.activateWindow()
        
    def show_translation_result(self, translation_result: dict, style_options: List[dict] = None):
        """显示翻译结果"""
        self._state = TextProcessingState.TRANSLATION_RESULT
        self._current_translation_result = translation_result
        self._style_options = style_options or []
        
        self.logger.info("Text processing overlay: showing translation result")
        
        # 构建显示文本
        original_text = translation_result.get('original_text', '')
        translated_text = translation_result.get('translated_text', '')
        source_lang = translation_result.get('source_language', 'Unknown')
        target_lang = translation_result.get('target_language', 'Unknown')
        
        display_text = f"<b>原文 ({source_lang}):</b><br/>{original_text}<br/><br/>"
        display_text += f"<b>翻译 ({target_lang}):</b><br/>{translated_text}"
        
        if 'error' in translation_result:
            display_text += f"<br/><br/><span style='color: #E74C3C;'><b>错误:</b> {translation_result['error']}</span>"
        
        self.text_display.setText(display_text)
        
        # 更新UI显示
        self.status_label.hide()
        self.text_display.show()
        self.scroll_area.show()
        
        # 显示风格选择（如果有）
        if self._style_options:
            self._setup_style_buttons()
            self.style_container.show()
        else:
            self.style_container.hide()
            
        # 显示操作按钮
        self.copy_button.show()
        self.new_process_button.show()
        
        # 调整窗口大小
        self.adjustSize()
        
    def show_style_result(self, styled_text: str, style_name: str):
        """显示风格化结果"""
        self._state = TextProcessingState.STYLE_RESULT
        self.logger.info(f"Text processing overlay: showing style result for {style_name}")
        
        display_text = f"<b>风格化结果 ({style_name}):</b><br/>{styled_text}"
        self.text_display.setText(display_text)
        
        # 隐藏风格选择，显示操作按钮
        self.style_container.hide()
        self.copy_button.show()
        self.new_process_button.show()
        
        self.adjustSize()
        
    def show_error(self, error_message: str):
        """显示错误信息"""
        self._state = TextProcessingState.ERROR
        self.logger.error(f"Text processing overlay: showing error - {error_message}")
        
        self._hide_all_content()
        self.status_label.setText(f"处理失败: {error_message}")
        self.status_label.setStyleSheet("color: #E74C3C;")
        self.status_label.show()
        self.new_process_button.show()
        
        self.show()
        self.raise_()
        self.activateWindow()
        
    def _setup_style_buttons(self):
        """设置风格选择按钮"""
        # 清除现有按钮
        for i in reversed(range(self.style_buttons_layout.count())):
            child = self.style_buttons_layout.itemAt(i).widget()
            if child:
                child.setParent(None)
                
        # 添加新按钮
        for style_option in self._style_options:
            button = StyleButton(style_option['name'])
            button.clicked.connect(lambda checked, name=style_option['name']: self._on_style_selected(name))
            self.style_buttons_layout.addWidget(button)
            
    def _on_style_selected(self, style_name: str):
        """处理风格选择"""
        self.logger.info(f"Style selected: {style_name}")
        self.style_selected.emit(style_name)
        
        # 显示处理状态
        self.status_label.setText(f"正在应用 {style_name} 风格...")
        self.status_label.setStyleSheet("color: #3498DB;")
        self.status_label.show()
        self.style_container.hide()
        self.copy_button.hide()
        self.new_process_button.hide()
        
    def _on_copy_clicked(self):
        """处理复制按钮点击"""
        if self._state == TextProcessingState.TRANSLATION_RESULT and self._current_translation_result:
            text_to_copy = self._current_translation_result.get('translated_text', '')
        elif self._state == TextProcessingState.STYLE_RESULT:
            # 从显示的文本中提取实际内容
            display_text = self.text_display.text()
            # 简单的文本提取，实际应用中可能需要更复杂的解析
            if "风格化结果" in display_text:
                text_to_copy = display_text.split(":</b><br/>", 1)[-1].replace("<br/>", "\n")
            else:
                text_to_copy = display_text
        else:
            text_to_copy = ""
            
        if text_to_copy:
            self.copy_to_clipboard.emit(text_to_copy)
            self.status_label.setText("已复制到剪贴板")
            self.status_label.setStyleSheet("color: #27AE60;")
            self.status_label.show()
            
            # 2秒后隐藏状态
            QTimer.singleShot(2000, lambda: self.status_label.hide())
            
    def hide_overlay(self):
        """隐藏界面"""
        self._state = TextProcessingState.HIDDEN
        self.logger.info("Text processing overlay: hiding")
        self.hide()
        self.close_requested.emit()
        
    def mousePressEvent(self, event: QMouseEvent):
        """处理鼠标按下事件（用于拖拽）"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()
            
    def mouseMoveEvent(self, event: QMouseEvent):
        """处理鼠标移动事件（用于拖拽）"""
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, 'drag_pos'):
            self.move(self.pos() + event.globalPosition().toPoint() - self.drag_pos)
            self.drag_pos = event.globalPosition().toPoint()
            event.accept()
            
    def mouseReleaseEvent(self, event: QMouseEvent):
        """处理鼠标释放事件"""
        if hasattr(self, 'drag_pos'):
            delattr(self, 'drag_pos')
            
    @property
    def state(self) -> TextProcessingState:
        """获取当前状态"""
        return self._state