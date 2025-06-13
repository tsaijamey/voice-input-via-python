import mss
import mss.tools
import pyautogui
from PIL import Image
import os
from datetime import datetime

# 定义存放截图的目录
RECORDING_DIR = "recordings"


def save_screenshot(image: Image.Image) -> str:
    """
    将截图保存到指定目录，并以时间戳命名。

    Args:
        image (Image.Image): 要保存的图像。

    Returns:
        str: 保存的文件路径。
    """
    # 确保目录存在
    if not os.path.exists(RECORDING_DIR):
        os.makedirs(RECORDING_DIR)

    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"screenshot_{timestamp}.png"
    filepath = os.path.join(RECORDING_DIR, filename)

    # 保存文件
    image.save(filepath, "PNG")
    print(f"截图已保存至: {filepath}")
    return filepath


def take_screenshot() -> Image.Image:
    """
    捕获当前鼠标所在显示器的屏幕截图。
    如果无法确定鼠标位置，则回退到主显示器。

    Returns:
        PIL.Image.Image: 捕获到的屏幕截图图像对象。
    """
    with mss.mss() as sct:
        try:
            # 获取当前鼠标位置
            mouse_x, mouse_y = pyautogui.position()
            
            # 遍历所有显示器，找到包含鼠标的那个
            target_monitor = None
            for monitor in sct.monitors[1:]: # sct.monitors[0] 是所有显示器的合集
                if monitor["left"] <= mouse_x < monitor["left"] + monitor["width"] and \
                   monitor["top"] <= mouse_y < monitor["top"] + monitor["height"]:
                    target_monitor = monitor
                    break
            
            # 如果没找到（例如鼠标在显示器之间），则默认使用主显示器
            if not target_monitor:
                target_monitor = sct.monitors[1]

        except Exception:
            # 如果pyautogui失败，也回退到主显示器
            target_monitor = sct.monitors[1]

        # 捕获目标显示器
        sct_img = sct.grab(target_monitor)
        
        # 将mss的BGRA格式转换为PIL的RGB格式
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        return img

def resize_image(image: Image.Image, max_width: int) -> Image.Image:
    """
    根据最大宽度按比例缩放图像。

    Args:
        image (Image.Image): 原始图像。
        max_width (int): 允许的最大宽度。

    Returns:
        PIL.Image.Image: 缩放后的图像。
    """
    if image.width <= max_width:
        return image
    
    original_width, original_height = image.size
    aspect_ratio = original_height / original_width
    new_width = max_width
    new_height = int(new_width * aspect_ratio)
    
    return image.resize((new_width, new_height), Image.LANCZOS)