from pynput import keyboard
from typing import Callable, Optional
import logging
from services.input_automation_service import InputAutomationService

class HotkeyManager:
    """支持多热键注册的热键管理器，可处理组合键"""
    
    def __init__(self):
        self.listener: Optional[keyboard.Listener] = None
        self.hotkey_callbacks: dict = {}  # {hotkey_str: callback}
        self.active_keys = set()  # 当前按下的键
        self.triggered_hotkeys = set()  # 已触发但尚未完全释放的热键
        self.logger = logging.getLogger(__name__)
        
    def register_hotkey(self, key: str, callback: Callable) -> None:
        """注册热键和回调函数
        
        Args:
            key: 热键字符串，如 'alt' 或 'ctrl+alt'
            callback: 回调函数，接受一个布尔参数表示按下/释放
        """
        key = key.lower()
        if key in self.hotkey_callbacks:
            self.logger.warning(f"Hotkey {key} already registered, overwriting")
        self.hotkey_callbacks[key] = callback
        self.logger.info(f"Registered hotkey: {key}")
        
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
            self.active_keys.add(key_str)
            
            # 检查所有已注册的热键是否匹配当前按下的键组合
            current_combo = '+'.join(sorted(self.active_keys))
            for hotkey, callback in self.hotkey_callbacks.items():
                if current_combo == hotkey and hotkey not in self.triggered_hotkeys:
                    # 标记热键已触发，但不立即执行回调
                    self.triggered_hotkeys.add(hotkey)
                    self.logger.info(f"Hotkey {hotkey} triggered, waiting for release...")
        except Exception as e:
            self.logger.error(f"Key press error: {e}")
            
    def _on_release(self, key) -> None:
        """处理按键释放事件"""
        try:
            key_str = self._get_key_str(key)
            if key_str in self.active_keys:
                self.active_keys.remove(key_str)
                
                # 检查已触发的热键是否完全释放
                for hotkey in list(self.triggered_hotkeys):
                    hotkey_keys = set(hotkey.split('+'))
                    # 如果热键的所有按键都已释放
                    if not hotkey_keys.intersection(self.active_keys):
                        self.triggered_hotkeys.remove(hotkey)
                        self.logger.info(f"Hotkey {hotkey} fully released, executing callback...")
                        
                        # 获取窗口信息并执行回调
                        window = InputAutomationService.get_window_under_cursor()
                        callback = self.hotkey_callbacks.get(hotkey)
                        if callback:
                            callback(True, window)  # 执行按下回调
        except Exception as e:
            self.logger.error(f"Key release error: {e}")
            
    def _get_key_str(self, key) -> str:
        """将键对象转换为字符串"""
        if hasattr(key, 'char') and key.char:
            return key.char.lower()
        elif hasattr(key, 'name'):
            return key.name.lower()
        return str(key).lower().replace('key.', '')
        
    def get_registered_hotkeys(self) -> list:
        """获取所有已注册的热键"""
        return list(self.hotkey_callbacks.keys())