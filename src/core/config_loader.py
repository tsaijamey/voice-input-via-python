import json
import os
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

class ConfigLoader:
    """
    配置文件加载器，处理JSON配置文件的读取、解析和验证。
    支持将服务配置与提供商配置分离，通过索引进行关联。
    """
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        load_dotenv()  # 加载 .env 文件中的环境变量

    def load(self) -> Dict[str, Any]:
        """加载、解析并验证配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
            
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self._config = json.load(f)
            
        self._validate_base_structure()
        self._resolve_services()
        self._validate_resolved_services()
        
        return self._config

    def _validate_base_structure(self) -> None:
        """验证配置文件顶层结构"""
        required_sections = ['hotkeys', 'recording', 'providers', 'services']
        for section in required_sections:
            if section not in self._config:
                raise ValueError(f"Missing required config section: '{section}'")

    def _resolve_services(self) -> None:
        """解析服务配置，将提供商信息合并到服务中"""
        providers = self._config.get('providers', [])
        services_to_resolve = self._config.get('services', {})
        resolved_services = {}

        for service_name, service_config in services_to_resolve.items():
            provider_index = service_config.get('provider_index')
            model_index = service_config.get('model_index')

            if provider_index is None or model_index is None:
                raise ValueError(f"Service '{service_name}' is missing 'provider_index' or 'model_index'.")

            if not (0 <= provider_index < len(providers)):
                raise ValueError(f"Invalid 'provider_index' {provider_index} for service '{service_name}'.")
            
            provider = providers[provider_index]
            
            if not (0 <= model_index < len(provider.get('models', []))):
                raise ValueError(f"Invalid 'model_index' {model_index} for service '{service_name}' in provider '{provider.get('name')}'.")

            model = provider['models'][model_index]
            api_key_env = provider.get('api_key_env')
            api_key = os.getenv(api_key_env) if api_key_env else None

            if api_key_env and not api_key:
                raise ValueError(f"Environment variable '{api_key_env}' for provider '{provider.get('name')}' is not set.")

            # 合并配置
            resolved_config = {
                'provider': provider.get('name'),
                'model': model.get('name'),
                'api_key': api_key,
                **service_config,  # 包含 temperature, max_width 等
                **model  # 包含 type 等
            }
            resolved_services[service_name] = resolved_config
        
        self._config['services'] = resolved_services

    def _validate_resolved_services(self) -> None:
        """验证解析后的服务配置是否齐全"""
        required_services = ['asr', 'text_correction', 'vision', 'content_enhancement']
        for service in required_services:
            if service not in self._config.get('services', {}):
                raise ValueError(f"Missing configuration for required service: '{service}'")