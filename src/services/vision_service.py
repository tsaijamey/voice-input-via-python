import os
import io
import base64
import json
import logging
from PIL import Image
from google import genai
from google.genai import types

class VisionService:
    def __init__(self, config: dict):
        """
        初始化视觉服务。

        Args:
            config (dict): 解析后的 'vision' 服务配置。
        """
        api_key = config.get('api_key')
        if not api_key:
            raise ValueError(f"API key not found for provider {config.get('provider')}")
        
        # 目前只支持 Google GenAI
        if config.get('provider') == 'google':
            self.client = genai.Client(api_key=api_key)
        else:
            raise NotImplementedError(f"Provider '{config.get('provider')}' is not supported in VisionService.")
            
        self.model = config['model']
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
分析所附的屏幕截图，并提供一个结构化的 JSON 响应。你的目标是全面理解屏幕上发生的一切，以推断用户的意图和当前任务。不要仅仅局限于寻找文本输入区域。

考虑到截图文件会被自动保存，并且后续可能有自动化的处理流程，你需要提供尽可能丰富和准确的上下文信息。

JSON 输出必须包含以下键：
1.  `main_activity`: 对用户当前正在进行的主要活动或任务进行高层次的描述。例如：“在 VSCode 中调试 Python 代码”、“在浏览器中研究机器学习主题”、“设计一个 Figma 原型”。
2.  `key_elements`: 一个对象数组，识别并描述屏幕上所有重要的 UI 元素、窗口或内容区域。每个对象应包含：
    - `element_type`: 元素的类型（例如：“代码编辑器”、“终端”、“浏览器地址栏”、“聊天窗口”、“视频播放器”）。
    - `description`: 对该元素的简要描述，包括其内容或状态（例如：“显示一个名为 'vision_service.py' 的 Python 文件”、“正在运行 'npm start' 命令”、“地址为 'google.com'”、“与 'John Doe' 的对话”）。
    - `is_active`: 一个布尔值，指示该元素当前是否是用户的焦点（例如，窗口是否在前台，光标是否在其中）。
3.  `full_context_summary`: 基于以上分析，对整个屏幕的上下文进行一个全面的总结。这个总结应该整合来自不同元素的信息，形成一个连贯的叙述，描述用户可能正在做什么，以及他们的目标可能是什么。
        """
        
        try:
            self.logger.info("Sending screenshot to Vision API for analysis...")
            
            # 转换为base64编码
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode()
            
            contents = [
                genai.types.Content(
                    role="user",
                    parts=[
                        genai.types.Part.from_bytes(
                            mime_type="image/png",
                            data=base64.b64decode(img_base64),
                        ),
                        types.Part.from_text(text=prompt),
                    ],
                )
            ]
            
            generate_content_config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                response_mime_type="application/json",
            )
            
            response = ""
            for chunk in self.client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=generate_content_config,
            ):
                response += chunk.text
            
            self.logger.info(f"Vision API response received: {response}")
            return json.loads(response)

        except Exception as e:
            self.logger.error(f"Error analyzing screenshot: {e}", exc_info=True)
            return {
                "error": str(e),
                "overall_context": "Unknown",
                "focus_area": "Unknown",
                "contextual_information": "Failed to analyze screen."
            }