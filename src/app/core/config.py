"""
配置管理模块

该模块负责加载、验证和提供应用程序配置。
使用 Pydantic v2 的 Settings 类处理配置验证和环境变量加载。
"""

import os
from typing import Dict, Any, Optional
from pathlib import Path
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 获取项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """应用程序设置类，使用 Pydantic V2 进行验证

    所有配置项应在这里定义，并指定类型、默认值和描述
    """
    # API 配置
    API_PREFIX: str = "/api"
    API_PORT: int = Field(default=58000, description="API 服务器监听端口")
    DEBUG: bool = Field(default=False, description="调试模式")
    PROJECT_NAME: str = "RTSP 视频流接收服务器"
    VERSION: str = "0.1.0"

    # RTSP 服务器配置
    RTSP_PORT: int = Field(default=8554, description="RTSP 服务器监听端口")  # 改为非特权端口
    RTSP_PATH: str = Field(default="/live", description="RTSP 媒体路径")
    OUTPUT_DIR: Path = Field(default=BASE_DIR / "videos", description="视频输出目录")
    MAX_VIDEO_STORAGE_DAYS: int = Field(default=1, description="视频文件最大存储天数")

    # 日志配置
    LOG_LEVEL: str = Field(default="INFO", description="日志级别")
    LOG_FORMAT: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="日志格式"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    def __init__(self, **data: Any):
        super().__init__(**data)
        # 确保输出目录存在
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    """获取应用程序设置的单例实例

    使用 lru_cache 装饰器确保只创建一个 Settings 实例

    Returns:
        Settings: 应用程序设置实例
    """
    return Settings()
