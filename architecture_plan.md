# 开发实现指南：集成视觉分析与内容增强功能 (V4 - 施工版)

## 1. 概述与目标

本指南提供了一个完整的、可直接用于编码的详细设计方案。目标是在现有语音输入应用中，集成一个结合了屏幕视觉分析与语音识别的智能内容增强功能。后续开发者可完全依据此文档进行实现，无需参考额外上下文。

**核心流程**: 用户按下录音键时，程序并行执行两个任务：(1) 录制并转录用户的语音；(2) 捕获屏幕并调用多模态AI分析用户意图和上下文。录音结束后，程序结合两者的结果，生成优化后的文本。

---

## 2. 文件结构变更

将在 `src` 目录下创建和修改以下文件：

```
src/
├── core/
│   └── ...
├── services/
│   ├── asr_service.py
│   ├── recording_service.py
│   ├── timer_overlay.py
│   ├── vision_service.py             # <-- 新增
│   └── content_enhancement_service.py  # <-- 新增
├── utils/
│   ├── __init__.py
│   └── screenshot_util.py            # <-- 新增
├── main.py                           # <-- 修改
└── output_handler.py
```

---

## 3. 配置文件 `config.json`

需要添加新的配置节，用于管理AI服务。

**`config.json` 示例:**
```json
{
  "hotkeys": {
    "toggle_recording": "ctrl+shift+space"
  },
  "recording": {
    "realtime_chunk_seconds": 10,
    "countdown_seconds": 60
  },
  "asr_service": {
    "provider": "openai",
    "model": "whisper-1"
  },
  "vision_service": {
    "provider": "google",
    "model": "gemini-2.5-flash",
    "api_key_env": "GOOGLE_API_KEY",
    "max_width": 1200
  },
  "enhancement_service": {
    "provider": "google",
    "model": "gemini-2.5-flash",
    "api_key_env": "GOOGLE_API_KEY"
  },
  "output": {
    "save_to_file": true,
    "filepath": "output.txt"
  }
}
```

---

## 4. 模块详细设计与实现代码

### 4.1. `src/utils/screenshot_util.py`

**职责**: 提供跨平台的屏幕截图和图像缩放功能。

**实现代码**:
```python
# src/utils/screenshot_util.py
import mss
import mss.tools
from PIL import Image

def take_screenshot() -> Image.Image:
    """
    捕获主显示器的屏幕截图。

    Returns:
        PIL.Image.Image: 捕获到的屏幕截图图像对象。
    """
    with mss.mss() as sct:
        # 获取主显示器的信息
        monitor = sct.monitors[1]
        
        # 捕获屏幕
        sct_img = sct.grab(monitor)
        
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

```

### 4.2. `src/services/vision_service.py`

**职责**: 调用Google Gemini模型分析截图，提取上下文信息。

**实现代码**:
```python
# src/services/vision_service.py
import os
import google.generativeai as genai
from PIL import Image
import json
import logging

class VisionService:
    def __init__(self, config: dict):
        """
        初始化视觉服务。

        Args:
            config (dict): 'vision_service' 部分的配置。
        """
        api_key = os.getenv(config['api_key_env'])
        if not api_key:
            raise ValueError(f"API key environment variable '{config['api_key_env']}' not set.")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(config['model'])
        self.logger = logging.getLogger(__name__)

    def analyze_screenshot(self, image: Image.Image) -> dict:
        """
        分析截图并返回结构化的上下文信息。

        Args:
            image (Image.Image): 待分析的截图。

        Returns:
            dict: 包含分析结果的字典，如果失败则返回错误信息。
        """
        prompt = """
        Analyze the attached screenshot and provide a structured JSON response. Your goal is to understand the user's current context and identify where they likely intend to input text.

        The JSON output must contain these keys:
        1.  `overall_context`: Briefly describe the main activity shown on the screen (e.g., "coding in VSCode", "replying to an email in Gmail", "searching on Google").
        2.  `focus_area`: Describe the specific UI element that is the most likely target for text input. Identify it by its characteristics (e.g., "the active search bar", "the blinking cursor in the code editor", "the message composition box").
        3.  `contextual_information`: Extract any relevant text or information immediately surrounding the focus area that would be crucial for generating a relevant response. For example, if it's a code editor, provide the surrounding function/class. If it's a reply, provide the previous message's content.
        """
        
        try:
            self.logger.info("Sending screenshot to Vision API for analysis...")
            response = self.model.generate_content([prompt, image])
            
            # 清理和解析返回的JSON
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            
            self.logger.info(f"Vision API response received: {raw_text}")
            return json.loads(raw_text)

        except Exception as e:
            self.logger.error(f"Error analyzing screenshot: {e}", exc_info=True)
            return {
                "error": str(e),
                "overall_context": "Unknown",
                "focus_area": "Unknown",
                "contextual_information": "Failed to analyze screen."
            }
```

### 4.3. `src/services/content_enhancement_service.py`

**职责**: 结合语音文本和视觉上下文，生成最终的优化文本。

**实现代码**:
```python
# src/services/content_enhancement_service.py
import os
import google.generativeai as genai
import logging

class ContentEnhancementService:
    def __init__(self, config: dict):
        api_key = os.getenv(config['api_key_env'])
        if not api_key:
            raise ValueError(f"API key environment variable '{config['api_key_env']}' not set.")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(config['model'])
        self.logger = logging.getLogger(__name__)

    def enhance_text(self, transcript: str, screen_context: dict) -> str:
        """
        根据语音和视觉上下文增强文本。

        Args:
            transcript (str): ASR服务转录的原始文本。
            screen_context (dict): VisionService返回的屏幕上下文。

        Returns:
            str: 增强后的文本。
        """
        prompt = f"""
        You are an intelligent assistant. Your task is to refine and complete a user's dictated text based on the context of their screen.

        **Screen Context:**
        - **Main Activity:** {screen_context.get('overall_context', 'N/A')}
        - **Input Focus Area:** {screen_context.get('focus_area', 'N/A')}
        - **Surrounding Information:** {screen_context.get('contextual_information', 'N/A')}

        **User's Dictated Text (raw):**
        "{transcript}"

        **Your Task:**
        Based on all the context provided, rewrite and enhance the user's dictated text to be more complete, coherent, and contextually appropriate. 
        - If the user is coding, complete the code snippet.
        - If the user is writing an email, formulate a full sentence or paragraph.
        - If the user is searching, create a precise search query.
        - Only return the final, enhanced text. Do not add any extra commentary.
        """
        
        try:
            self.logger.info("Sending data for content enhancement...")
            response = self.model.generate_content(prompt)
            enhanced_text = response.text.strip()
            self.logger.info(f"Enhanced text received: {enhanced_text}")
            return enhanced_text
        except Exception as e:
            self.logger.error(f"Error enhancing text: {e}", exc_info=True)
            # 在增强失败时，优雅地回退到原始文本
            return transcript
```

### 4.4. `src/main.py` 修改指南

**职责**: 集成新服务，并实现并行处理逻辑。

**修改步骤**:

1.  **导入新模块**:
    ```python
    # 在文件顶部添加
    from services.vision_service import VisionService
    from services.content_enhancement_service import ContentEnhancementService
    from utils.screenshot_util import take_screenshot, resize_image
    ```

2.  **修改 `main` 函数**:
    *   在 `try` 块内，初始化新服务：
      ```python
      # --- 初始化服务和状态 ---
      # ... (保留原有服务初始化)
      vision_service = VisionService(config['vision_service'])
      enhancement_service = ContentEnhancementService(config['enhancement_service'])
      max_screenshot_width = config['vision_service'].get('max_width', 1200)
      ```
    *   在 `main` 函数作用域内，增加用于线程通信的变量：
      ```python
      vision_worker_thread = None
      screen_context_result = None
      ```

3.  **修改 `handle_toggle_recording` 函数**: 这是核心修改。

    *   **处理 `start=True` (开始录音)**:
      ```python
      # 在 handle_toggle_recording 函数内
      if start and not is_recording:
          is_recording = True
          logger.info("Recording started...")

          # --- 并行任务启动 ---
          # 1. 启动视觉分析线程
          def vision_worker():
              nonlocal screen_context_result
              logger.info("Capturing and analyzing screen...")
              screenshot = take_screenshot()
              resized_screenshot = resize_image(screenshot, max_screenshot_width)
              screen_context_result = vision_service.analyze_screenshot(resized_screenshot)
              logger.info("Screen analysis complete.")

          vision_worker_thread = threading.Thread(target=vision_worker, daemon=True)
          vision_worker_thread.start()

          # 2. 启动录音和ASR转录线程 (保留原有逻辑)
          full_transcript = []
          while not audio_queue.empty():
              audio_queue.get_nowait()

          transcription_worker_thread = threading.Thread(target=transcription_worker, daemon=True)
          transcription_worker_thread.start()
          
          countdown = config['recording'].get('countdown_seconds', 60)
          control_widget.set_recording_state(countdown)
          
          recording_service.start_recording(audio_queue, chunk_size)
      ```

    *   **处理 `start=False` (停止录音)**:
      ```python
      elif not start and is_recording:
          is_recording = False
          logger.info("Recording stopped...")
          
          # 停止录音
          recording_service.stop_recording()
          
          # 发送结束信号给ASR转录工作线程
          audio_queue.put(None)
          
          # --- 等待并行任务完成 ---
          logger.info("Waiting for transcription and vision analysis to complete...")
          if transcription_worker_thread:
              transcription_worker_thread.join(timeout=10.0) # 增加超时
          if vision_worker_thread:
              vision_worker_thread.join(timeout=20.0) # 视觉分析可能更耗时

          final_text = ' '.join(full_transcript)
          logger.info(f"最终识别文本: {final_text}")
          logger.info(f"最终屏幕上下文: {screen_context_result}")

          if final_text and screen_context_result:
              # --- 内容增强 ---
              enhanced_text = enhancement_service.enhance_text(final_text, screen_context_result)
              logger.info(f"增强后文本: {enhanced_text}")
              copy_to_clipboard(enhanced_text)
              save_to_file(enhanced_text)
          elif final_text:
              # 如果视觉分析失败，则回退到只输出原始文本
              logger.warning("Vision analysis failed or returned no result. Falling back to original transcript.")
              copy_to_clipboard(final_text)
              save_to_file(final_text)
          else:
              logger.warning("没有识别到任何文本，跳过输出。")

          control_widget.set_idle_state()
      ```

---

## 5. 总结

本指南提供了从配置文件到具体模块代码的完整实现细节。按照此文档，开发者可以：
1.  更新 `config.json`。
2.  创建 `screenshot_util.py`, `vision_service.py`, `content_enhancement_service.py` 三个新文件并填入代码。
3.  修改 `main.py`，集成新的服务和并行处理逻辑。

完成以上步骤后，应用将具备完整的“语音+视觉”内容增强能力。