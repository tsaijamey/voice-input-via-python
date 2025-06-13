import pyautogui
import pyperclip
import logging
import time
import platform
import pygetwindow

class InputAutomationService:
    """封装UI自动化操作的服务"""

    @staticmethod
    def get_focused_window():
        """获取当前拥有焦点的窗口信息"""
        try:
            active_window = pygetwindow.getActiveWindow()
            if active_window:
                logging.info(f"Focused window title: {active_window.title}")
                return active_window.title
            else:
                logging.warning("Could not get active window.")
                return None
        except Exception as e:
            logging.error(f"Error getting focused window: {e}")
            return None

    @staticmethod
    def get_window_under_cursor():
        """获取当前鼠标光标下的窗口信息"""
        try:
            x, y = pyautogui.position()
            windows = pygetwindow.getWindowsAt(x, y)
            if windows:
                window_title = windows[0].title
                logging.info(f"Window under cursor at ({x}, {y}): {window_title}")
                return window_title
            else:
                logging.warning(f"No window found under cursor at ({x}, {y}).")
                return None
        except Exception as e:
            logging.error(f"Error getting window under cursor: {e}")
            # 作为后备，尝试返回当前聚焦的窗口
            return InputAutomationService.get_focused_window()

    @staticmethod
    def paste_to_window(window_title: str, text: str):
        """尝试将文本粘贴到指定窗口"""
        if not window_title:
            logging.warning("No target window, falling back to clipboard.")
            pyperclip.copy(text)
            return

        try:
            pyperclip.copy(text)
            # 先尝试聚焦窗口
            windows = pygetwindow.getWindowsWithTitle(window_title)
            if windows:
                windows[0].activate()
                time.sleep(0.5)  # 等待窗口激活
            # Determine OS and use appropriate hotkey
            system = platform.system()
            
            if system == 'Darwin':  # macOS
                pyautogui.hotkey('command', 'v')
            elif system in ['Windows', 'Linux']:
                pyautogui.hotkey('ctrl', 'v')
            else:
                logging.warning(f"Unsupported OS: {system}, paste may not work correctly")
                pyautogui.hotkey('ctrl', 'v')  # Default fallback
            logging.info(f"Pasted text to window: {window_title}")
        except Exception as e:
            logging.error(f"Error pasting to window {window_title}: {e}")
            pyperclip.copy(text)  # 回退到剪贴板