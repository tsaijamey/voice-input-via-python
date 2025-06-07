import json
import os
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

class ConfigLoader:
    """配置文件加载器，处理JSON配置文件的读取和验证"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        load_dotenv()  # 加载环境变量
        
    def load(self) -> Dict[str, Any]:
        """加载并验证配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
            
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self._config = json.load(f)
            
        self._inject_env_vars()
        self._validate()
        return self._config
    
    def _validate(self) -> None:
        """验证配置结构"""
        required_sections = ['hotkeys', 'recording', 'asr_provider', 'llm_provider']
        for section in required_sections:
            if section not in self._config:
                raise ValueError(f"Missing required config section: {section}")
                
        # 验证热键配置
        if 'toggle_recording' not in self._config['hotkeys']:
            raise ValueError("Missing required hotkey: toggle_recording")
            
    def _inject_env_vars(self) -> None:
        """将环境变量注入到配置中"""
        # 确保API服务配置存在
        for service in ['asr_provider', 'llm_provider']:
            if service in self._config:
                self._config[service]['api_key'] = os.getenv('GROQ_API_KEY', '')