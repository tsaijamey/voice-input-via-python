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

    @staticmethod
    def copy_selected_text_to_clipboard(timeout: float = 2.0, max_attempts: int = 3, hotkey_release_delay: float = 0.1) -> str:
        """模拟复制选中文本到剪贴板并返回文本内容
        
        Args:
            timeout: 等待剪贴板内容变化的超时时间(秒)
            max_attempts: 最大重试次数
            hotkey_release_delay: 额外的安全延迟时间(秒)，确保系统稳定
            
        Returns:
            剪贴板中的文本内容
            
        Raises:
            RuntimeError: 当无法获取有效文本内容时
        """
        # 添加一个小的安全延迟，确保系统稳定
        # 注意：主要的快捷键释放等待已在HotkeyManager中处理
        time.sleep(hotkey_release_delay)
        logging.info(f"Starting copy operation with {hotkey_release_delay}s safety delay...")
        
        system = platform.system()
        copy_hotkey = 'command+c' if system == 'Darwin' else 'ctrl+c'
        
        original_content = pyperclip.paste()
        last_content = original_content
        
        for attempt in range(1, max_attempts + 1):
            try:
                # 模拟复制操作前先清空剪贴板
                pyperclip.copy('')
                time.sleep(0.2)
                
                # 模拟复制操作
                pyautogui.hotkey(*copy_hotkey.split('+'))
                time.sleep(0.5)  # 增加延迟确保复制完成
                
                # 等待剪贴板内容变化
                start_time = time.time()
                while time.time() - start_time < timeout:
                    current_content = pyperclip.paste()
                    if current_content and current_content != last_content:
                        # 验证内容是否为文本
                        try:
                            current_content.encode('utf-8')
                            if current_content.strip():  # 确保不是空字符串
                                return current_content.strip()
                        except UnicodeError:
                            raise RuntimeError("Clipboard contains non-text data")
                    
                    time.sleep(0.1)
                    last_content = current_content
                
                logging.warning(f"Attempt {attempt}: Clipboard content did not change within timeout")
                logging.info("Please ensure the application has accessibility permissions in System Settings")
            except Exception as e:
                logging.warning(f"Attempt {attempt} failed: {str(e)}")
                if system == 'Darwin' and "accessibility" in str(e).lower():
                    logging.error("MacOS accessibility permission required! Please enable in System Settings > Security & Privacy > Accessibility")
        
        raise RuntimeError(f"Failed to get selected text after {max_attempts} attempts. Please check: \n"
                         "1. Application has accessibility permissions (MacOS)\n"
                         "2. Text is actually selected\n"
                         "3. Try manually copying (Cmd+C) first")

    @staticmethod
    def insert_text_at_caret(text: str):
        """在当前光标位置插入文本"""
        try:
            # 将文本复制到剪贴板
            pyperclip.copy(text)
            time.sleep(0.1)  # 短暂延迟确保复制完成
            
            # 根据操作系统使用相应的粘贴快捷键
            system = platform.system()
            if system == 'Darwin':  # macOS
                pyautogui.hotkey('command', 'v')
            elif system in ['Windows', 'Linux']:
                pyautogui.hotkey('ctrl', 'v')
            else:
                logging.warning(f"Unsupported OS: {system}, paste may not work correctly")
                pyautogui.hotkey('ctrl', 'v')  # Default fallback
                
            logging.info(f"Inserted text at caret: {text[:50]}...")
        except Exception as e:
            logging.error(f"Error inserting text at caret: {e}")
            # 作为后备，至少将文本保留在剪贴板中
            pyperclip.copy(text)