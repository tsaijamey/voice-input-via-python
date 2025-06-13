import os
import logging
from google import genai
from google.genai import types

class ContentEnhancementService:
    def __init__(self, config: dict):
        """
        初始化内容增强服务。

        Args:
            config (dict): 解析后的 'content_enhancement' 服务配置。
        """
        api_key = config.get('api_key')
        if not api_key:
            raise ValueError(f"API key not found for provider {config.get('provider')}")

        provider = config.get('provider')
        if provider == 'google':
            from google import genai
            self.client = genai.Client(api_key=api_key)
        elif provider == 'groq':
            from groq import Groq
            self.client = Groq(api_key=api_key)
        else:
            raise NotImplementedError(f"Provider '{provider}' is not supported in ContentEnhancementService.")
            
        self.model = config['model']
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
        
        # 格式化关键元素以获得更好的可读性
        key_elements_str = "\n".join(
            [
                f"  - 类型: {el.get('element_type', 'N/A')}, "
                f"描述: {el.get('description', 'N/A')}, "
                f"是否激活: {'是' if el.get('is_active') else '否'}"
                for el in screen_context.get('key_elements', [])
            ]
        )

        prompt = f"""
任务目标：根据视觉识别理解的当前用户屏幕上下文，和用户语音输入转义的文本，理解用户当前面临的场景以及用户表达的意图，为用户生成用于输入的内容。内容应该是完整连贯的，符合用户当前的操作场景，符合用户意图。

规范与行动指南：
- 如果用户的表达带有情绪，那么审视这种情绪通过文字传递到场景时是否恰当。
    - 恰当的标准：
        - 人际交流中，不应该有过度的情绪表达。
        - 人机交互中，无需体现过度情绪，应该从用户情绪中理解用户真正想要陈述的内容重点。
        - 特例：当上下文中充斥着情绪表达时，那么服从用户的情绪表达，甚至你应该让用户的情绪表达通过文字传递更精彩，例如贴吧嘴臭哥那种高潮的情绪表达。
- 如果用户正在编写代码，那么帮助用户用更详细且符合上下文信息的方式增强他的描述。
- 如果用户正在撰写文章，则将其转化为完整的句子或段落。
- 如果用户正在搜索，则创建一个精确的搜索查询。
- 如果……

**屏幕上下文:**
- **主要活动:** {screen_context.get('main_activity', 'N/A')}
- **关键元素:**
{key_elements_str if key_elements_str else '  - 未识别到关键元素'}
- **上下文总结:** {screen_context.get('full_context_summary', 'N/A')}

**用户原始语音文本:**
"{transcript}"

**输出格式要求:**
仅允许输出可以直接用于输入在input区域的文本内容，**不允许**包含其他无关的解释、自白、思考信息或总结。
        """
        
        try:
            self.logger.info("Sending data for content enhancement...")
            # 根据客户端类型调用不同的方法
            if isinstance(self.client, genai.Client):
                contents = [
                    genai.types.Content(
                        role="user",
                        parts=[genai.types.Part.from_text(text=prompt)]
                    )
                ]
                generate_content_config = types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                    response_mime_type="text/plain",
                )
                stream = self.client.models.generate_content_stream(
                    model=self.model,
                    contents=contents,
                    config=generate_content_config,
                )
            else: # 假设是 Groq 或其他 OpenAI 兼容的客户端
                messages = [{"role": "user", "content": prompt}]
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    stream=True
                )

            response = ""
            for chunk in stream:
                # 处理不同客户端返回的 chunk 结构
                if hasattr(chunk, 'text'): # Google GenAI
                    response += chunk.text
                elif hasattr(chunk, 'choices') and chunk.choices: # OpenAI-like
                    content = chunk.choices[0].delta.content
                    if content:
                        response += content
            
            self.logger.info(f"Enhanced text received: {response}")
            return response.strip()
        except Exception as e:
            self.logger.error(f"Error enhancing text: {e}", exc_info=True)
            # 在增强失败时，优雅地回退到原始文本
            return transcript
