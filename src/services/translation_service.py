import os
import logging
import re
from google import genai
from google.genai import types
from groq import Groq

class TranslationService:
    def __init__(self, config: dict):
        """
        初始化翻译服务。

        Args:
            config (dict): 解析后的 'translation_service' 服务配置。
        """
        api_key = config.get('api_key')
        if not api_key:
            raise ValueError(f"API key not found for provider {config.get('provider')}")

        provider = config.get('provider')
        if provider == 'google':
            self.client = genai.Client(api_key=api_key)
        elif provider == 'groq':
            self.client = Groq(api_key=api_key)
        else:
            raise NotImplementedError(f"Provider '{provider}' is not supported in TranslationService.")
            
        self.model = config['model']
        self.temperature = config.get('temperature', 0.3)
        self.logger = logging.getLogger(__name__)

    def detect_language_and_translate(self, text: str, translation_logic: dict) -> dict:
        """
        检测文本语言并进行翻译。

        Args:
            text (str): 要翻译的文本。
            translation_logic (dict): 翻译逻辑配置。

        Returns:
            dict: 包含原文、目标语言、翻译结果的字典。
        """
        # 简单的语言检测
        is_chinese = self._contains_chinese(text)
        
        if is_chinese:
            target_language = translation_logic.get('zh_to', 'English')
        else:
            target_language = translation_logic.get('en_to', 'Chinese')

        prompt = f"""
请将以下文本翻译为{target_language}。要求：
1. 保持原文的语气和风格
2. 确保翻译准确、自然
3. 只输出翻译结果，不要包含其他解释

原文：
{text}
"""

        try:
            self.logger.info(f"Translating text to {target_language}...")
            
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
            else:  # 假设是 Groq 或其他 OpenAI 兼容的客户端
                messages = [{"role": "user", "content": prompt}]
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    stream=True
                )

            response = ""
            for chunk in stream:
                # 处理不同客户端返回的 chunk 结构
                if hasattr(chunk, 'text'):  # Google GenAI
                    response += chunk.text
                elif hasattr(chunk, 'choices') and chunk.choices:  # OpenAI-like
                    content = chunk.choices[0].delta.content
                    if content:
                        response += content
            
            if isinstance(self.client, Groq):
                self.logger.info(f"Original response from groq: {response}")
                response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)

            translation = response.strip()
            self.logger.info(f"Translation completed: {translation}")
            
            return {
                'original_text': text,
                'target_language': target_language,
                'translated_text': translation,
                'source_language': 'Chinese' if is_chinese else 'English'
            }
            
        except Exception as e:
            self.logger.error(f"Error translating text: {e}", exc_info=True)
            return {
                'original_text': text,
                'target_language': target_language,
                'translated_text': text,  # 翻译失败时返回原文
                'source_language': 'Chinese' if is_chinese else 'English',
                'error': str(e)
            }

    def enhance_style(self, text: str, style_prompt: str) -> str:
        """
        根据风格提示增强文本。

        Args:
            text (str): 要增强的文本。
            style_prompt (str): 风格提示。

        Returns:
            str: 增强后的文本。
        """
        prompt = f"""
{style_prompt}

原文：
{text}

请按照上述要求改写文本，只输出改写结果，不要包含其他解释。
"""

        try:
            self.logger.info("Enhancing text style...")
            
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
            else:  # 假设是 Groq 或其他 OpenAI 兼容的客户端
                messages = [{"role": "user", "content": prompt}]
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,  # 风格增强使用更高的温度
                    stream=True
                )

            response = ""
            for chunk in stream:
                # 处理不同客户端返回的 chunk 结构
                if hasattr(chunk, 'text'):  # Google GenAI
                    response += chunk.text
                elif hasattr(chunk, 'choices') and chunk.choices:  # OpenAI-like
                    content = chunk.choices[0].delta.content
                    if content:
                        response += content
            
            if isinstance(self.client, Groq):
                response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)

            enhanced_text = response.strip()
            self.logger.info(f"Style enhancement completed: {enhanced_text}")
            return enhanced_text
            
        except Exception as e:
            self.logger.error(f"Error enhancing style: {e}", exc_info=True)
            return text  # 增强失败时返回原文

    def _contains_chinese(self, text: str) -> bool:
        """
        检测文本是否包含中文字符。

        Args:
            text (str): 要检测的文本。

        Returns:
            bool: 如果包含中文字符返回True，否则返回False。
        """
        chinese_pattern = re.compile(r'[\u4e00-\u9fff]+')
        return bool(chinese_pattern.search(text))