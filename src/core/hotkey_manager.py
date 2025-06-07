from pynput import keyboard
from typing import Callable, Optional
import logging

class HotkeyManager:
    """简化版热键管理器，使用单个修饰键切换录音状态"""
    
    def __init__(self):
        self.listener: Optional[keyboard.Listener] = None
        self.toggle_callback: Optional[Callable] = None
        self.is_pressed = False
        self.logger = logging.getLogger(__name__)
        
    def register_toggle(self, key: str, callback: Callable) -> None:
        """注册切换键和回调函数"""
        self.toggle_key = key.lower()
        self.toggle_callback = callback
        self.logger.info(f"Registered toggle key: {self.toggle_key}")
        
    def start(self) -> None:
        """启动热键监听"""
        if self.listener is not None:
            self.logger.warning("Listener already running")
            return
            
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.listener.start()
        self.logger.info("Hotkey listener started")
        
    def stop(self) -> None:
        """停止热键监听"""
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
            self.logger.info("Hotkey listener stopped")
            
    def _on_press(self, key) -> None:
        """处理按键按下事件"""
        try:
            key_str = self._get_key_str(key)
            if key_str == self.toggle_key and not self.is_pressed:
                self.is_pressed = True
                self.toggle_callback(True)  # 开始录音
        except Exception as e:
            self.logger.error(f"Key press error: {e}")
            
    def _on_release(self, key) -> None:
        """处理按键释放事件"""
        try:
            key_str = self._get_key_str(key)
            if key_str == self.toggle_key and self.is_pressed:
                self.is_pressed = False
                self.toggle_callback(False)  # 停止录音
        except Exception as e:
            self.logger.error(f"Key release error: {e}")
            
    def _get_key_str(self, key) -> str:
        """将键对象转换为字符串"""
        if hasattr(key, 'char') and key.char:
            return key.char.lower()
        elif hasattr(key, 'name'):
            return key.name.lower()
        return str(key).lower().replace('key.', '')