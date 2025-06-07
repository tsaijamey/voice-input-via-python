import os
import logging
import numpy as np
from groq import Groq
from typing import Optional, Union
import io

class ASRService:
    """语音识别服务，使用Groq官方Python客户端"""
    
    def __init__(self, config: dict):
        self.asr_config = config['asr_provider']
        self.llm_config = config.get('llm_provider', {})
        self.proxy_config = config.get('proxy')
        self.logger = logging.getLogger(__name__)
        self.client = self._init_client()

    def _init_client(self) -> Groq:
        """根据配置初始化Groq客户端，包括API密钥和代理"""
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable not set.")

        if self.proxy_config and self.proxy_config.get('http'):
            from httpx import Client
            proxies = {
                "http://": self.proxy_config['http'],
                "https://": self.proxy_config.get('https', self.proxy_config['http']),
            }
            http_client = Client(proxies=proxies)
            return Groq(api_key=api_key, http_client=http_client)
        else:
            return Groq(api_key=api_key)
        
    def transcribe(self, audio_source: Union[str, io.BytesIO], language: str = "zh") -> Optional[str]:
        """转录音频文件或内存数据为文本
        Args:
            audio_source: 音频文件路径或包含音频数据的io.BytesIO对象
            language: 语言代码(如zh/en)，默认为中文
        """
        try:
            if isinstance(audio_source, str):
                with open(audio_source, 'rb') as audio_file:
                    response = self.client.audio.transcriptions.create(
                        file=("audio.wav", audio_file.read()),
                        model=self.asr_config['model'],
                        language=language
                    )
            elif isinstance(audio_source, io.BytesIO):
                audio_source.seek(0) # 确保从头读取
                response = self.client.audio.transcriptions.create(
                    file=("audio.wav", audio_source.read()),
                    model=self.asr_config['model'],
                    language=language
                )
            else:
                self.logger.error(f"Unsupported audio source type: {type(audio_source)}")
                return None
                
            return response.text
        except Exception as e:
            self.logger.error(f"ASR transcription failed: {e}", exc_info=True)
            return None

    def transcribe_audio_data(self, audio_data: np.ndarray, sample_rate: int, language: str = "zh") -> Optional[str]:
        """
        直接从Numpy数组转录音频数据为文本。
        该方法通过在内存中创建WAV数据来实现，避免磁盘I/O。

        Args:
            audio_data: int16格式的音频Numpy数组。
            sample_rate: 音频采样率。
            language: 语言代码(如zh/en)，默认为中文。
        """
        import soundfile as sf
        
        try:
            # 检查输入是否为空
            if audio_data.size == 0:
                self.logger.warning("Received empty audio data, skipping transcription.")
                return None

            # 创建内存中的二进制数据流
            wav_buffer = io.BytesIO()
            
            # 将int16 NumPy数组直接写入内存中的WAV buffer
            # RecordingService 已经提供了 int16 数据，无需再做归一化
            sf.write(wav_buffer, audio_data, sample_rate, format='WAV', subtype='PCM_16')
            
            # 重置buffer的指针到开头
            wav_buffer.seek(0)
            
            # 调用核心的转录方法
            return self.transcribe(wav_buffer, language)
            
        except Exception as e:
            self.logger.error(f"ASR transcription from data failed: {e}", exc_info=True)
            return None

    def correct_text(self, text: str) -> str:
        """
        使用LLM修正和优化ASR识别出的文本。

        Args:
            text (str): ASR识别出的原始文本。

        Returns:
            str: 经过LLM修正后的文本。
        """
        if not self.llm_config:
            self.logger.warning("LLM provider not configured. Skipping text correction.")
            return text

        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一个专业的速记员和文本润色师。"
                            "你的任务是修正ASR（自动语音识别）的输出结果。"
                            "请遵循以下规则：\n"
                            "1.  修正明显的识别错误。\n"
                            "2.  添加正确的标点符号，使句子通顺流畅。\n"
                            "3.  保留原始文本的口语风格，不要过度书面化。\n"
                            "4.  如果内容包含代码或专业术语，请确保其格式正确。\n"
                            "5.  直接输出修正后的文本，不要包含任何解释或额外说明。"
                        )
                    },
                    {
                        "role": "user",
                        "content": f"请修正以下ASR识别结果：\n\n{text}",
                    }
                ],
                model=self.llm_config['model'],
                temperature=self.llm_config.get('temperature', 0.7),
            )
            corrected_text = chat_completion.choices[0].message.content
            return corrected_text.strip() if corrected_text else text
        except Exception as e:
            self.logger.error(f"LLM text correction failed: {e}", exc_info=True)
            return text # 如果修正失败，返回原始文本