import logging
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum, auto

from PySide6.QtCore import QObject, Signal

from core.config_loader import ConfigLoader
from services.input_automation_service import InputAutomationService
from services.text_processing_overlay import TextProcessingOverlay
from services.translation_service import TranslationService

class ProcessingState(Enum):
    """文本处理状态枚举"""
    IDLE = auto()        # 空闲状态
    PROCESSING = auto()  # 处理中
    FINISHED = auto()    # 处理完成
    ERROR = auto()       # 错误状态

@dataclass
class ProcessingResult:
    """文本处理结果数据类"""
    original_text: str
    processed_text: str
    success: bool
    translation_result: Optional[dict] = None
    error: Optional[str] = None

class TextProcessingService(QObject):
    """
    文本处理协调服务，负责管理整个文本处理流程：
    1. 从剪贴板获取文本
    2. 调用处理链处理文本
    3. 更新独立UI状态
    4. 将结果插入到目标应用
    """
    processing_started = Signal()
    processing_finished = Signal(ProcessingResult)
    error_occurred = Signal(str)

    def __init__(self,
                 config: ConfigLoader,
                 input_service: InputAutomationService):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self._config = config
        self._input_service = input_service
        self._state = ProcessingState.IDLE
        self._current_result: Optional[ProcessingResult] = None
        
        # 创建独立的文本处理UI
        self._ui_overlay = TextProcessingOverlay()

        # 初始化翻译服务
        try:
            config_data = self._config.load()
            translation_config = config_data['services']['translation']
            self._translation_service = TranslationService(translation_config)
            self._text_processing_config = config_data['services']['text_processing']
        except Exception as e:
            self.logger.error(f"Failed to initialize translation service: {e}")
            self._translation_service = None
            self._text_processing_config = {}

        # 连接信号
        self.processing_started.connect(self._on_processing_started)
        self.processing_finished.connect(self._on_processing_finished)
        self.error_occurred.connect(self._on_error)
        
        # 连接UI信号
        self._ui_overlay.style_selected.connect(self._on_style_selected)
        self._ui_overlay.close_requested.connect(self._on_ui_closed)
        self._ui_overlay.copy_to_clipboard.connect(self._on_copy_to_clipboard)

    @property
    def state(self) -> ProcessingState:
        """获取当前处理状态"""
        return self._state

    def start_processing(self):
        """启动文本处理流程"""
        if self._state != ProcessingState.IDLE:
            self.logger.warning(f"Cannot start processing in {self._state} state")
            return

        try:
            # 1. 从剪贴板获取文本，使用配置的延迟时间
            hotkey_release_delay = self._text_processing_config.get('hotkey_release_delay_seconds', 0.1)
            timeout = self._text_processing_config.get('clipboard_timeout_seconds', 5.0)
            retry_attempts = self._text_processing_config.get('retry_attempts', 5)
            
            text = self._input_service.copy_selected_text_to_clipboard(
                timeout=timeout,
                max_attempts=retry_attempts,
                hotkey_release_delay=hotkey_release_delay
            )
            if not text:
                raise ValueError("No text available in clipboard")

            # 2. 更新UI状态
            self.processing_started.emit()

            # 3. 处理文本 - 执行翻译
            translation_result = self._process_text(text)

            # 4. 完成处理
            result = ProcessingResult(
                original_text=text,
                processed_text=translation_result.get('translated_text', text),
                translation_result=translation_result,
                success=True
            )
            self.processing_finished.emit(result)

        except Exception as e:
            self.logger.error(f"Processing failed: {str(e)}")
            result = ProcessingResult(
                original_text="",
                processed_text="",
                success=False,
                error=str(e)
            )
            self.processing_finished.emit(result)

    def _process_text(self, text: str) -> dict:
        """实际文本处理方法 - 执行翻译"""
        if not self._translation_service:
            self.logger.error("Translation service not initialized")
            return {
                'original_text': text,
                'translated_text': text,
                'target_language': 'Unknown',
                'source_language': 'Unknown',
                'error': 'Translation service not available'
            }
        
        try:
            translation_logic = self._text_processing_config.get('translation_logic', {})
            result = self._translation_service.detect_language_and_translate(text, translation_logic)
            self.logger.info(f"Translation completed: {result['source_language']} -> {result['target_language']}")
            return result
        except Exception as e:
            self.logger.error(f"Translation failed: {e}")
            return {
                'original_text': text,
                'translated_text': text,
                'target_language': 'Unknown',
                'source_language': 'Unknown',
                'error': str(e)
            }

    def _on_processing_started(self):
        """处理开始时的回调"""
        self._state = ProcessingState.PROCESSING
        self._ui_overlay.show_processing_state()

    def _on_processing_finished(self, result: ProcessingResult):
        """处理完成时的回调"""
        self._current_result = result
        if result.success:
            self._state = ProcessingState.FINISHED
            # 显示翻译结果和风格选择
            self._show_translation_result(result)
        else:
            self._state = ProcessingState.ERROR
            self._ui_overlay.show_error(result.error or "处理失败")

    def _show_translation_result(self, result: ProcessingResult):
        """显示翻译结果和风格选择按钮"""
        if not result.translation_result:
            self._ui_overlay.show_error("翻译结果为空")
            return

        translation = result.translation_result
        
        # 将翻译结果插入到光标位置
        self._input_service.insert_text_at_caret(translation['translated_text'])
        
        # 获取风格选择选项
        style_options = self._text_processing_config.get('style_options', [])
        
        # 在独立UI中显示翻译结果
        self._ui_overlay.show_translation_result(translation, style_options)

    def _on_style_selected(self, style_name: str):
        """处理风格选择"""
        if not self._current_result or not self._current_result.translation_result:
            self.logger.warning("No translation result available for style application")
            self._ui_overlay.show_error("没有可用的翻译结果")
            return
            
        style_options = self._text_processing_config.get('style_options', [])
        selected_style = next((opt for opt in style_options if opt['name'] == style_name), None)
        
        if not selected_style:
            self.logger.error(f"Style '{style_name}' not found")
            self._ui_overlay.show_error(f"风格 '{style_name}' 未找到")
            return
            
        try:
            text_to_enhance = self._current_result.translation_result['translated_text']
            enhanced_text = self._translation_service.enhance_style(text_to_enhance, selected_style['prompt'])
            
            # 将风格化结果插入到光标位置
            self._input_service.insert_text_at_caret(enhanced_text)
            
            # 在UI中显示风格化结果
            self._ui_overlay.show_style_result(enhanced_text, style_name)
            
        except Exception as e:
            self.logger.error(f"Style application failed: {e}")
            self._ui_overlay.show_error(f"风格应用失败: {str(e)}")
            
    def _on_ui_closed(self):
        """处理UI关闭"""
        self.logger.info("Text processing UI closed")
        self._state = ProcessingState.IDLE
        self._current_result = None
        
    def _on_copy_to_clipboard(self, text: str):
        """处理复制到剪贴板请求"""
        try:
            import pyperclip
            pyperclip.copy(text)
            self.logger.info("Text copied to clipboard")
        except Exception as e:
            self.logger.error(f"Failed to copy to clipboard: {e}")

    def _on_error(self, error_msg: str):
        """错误处理回调"""
        self.logger.error(f"Text processing error: {error_msg}")
        self._ui_overlay.show_error(error_msg)
        # 重置处理状态，允许重新开始
        self._state = ProcessingState.IDLE
        
    @property
    def ui_overlay(self) -> TextProcessingOverlay:
        """获取UI界面引用"""
        return self._ui_overlay