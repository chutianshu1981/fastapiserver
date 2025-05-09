"""
日志配置模块

该模块负责配置应用程序的日志系统。
根据配置创建和管理日志记录器，提供不同模块使用的日志功能。
"""

import sys
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any

from .config import get_settings

# 日志级别映射
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def setup_logging(log_file: Optional[Path] = None) -> logging.Logger:
    """设置应用程序日志系统

    配置根日志记录器的格式、级别和处理程序。
    可以同时输出到控制台和文件（如果提供了文件路径）。

    Args:
        log_file: 可选的日志文件路径

    Returns:
        logging.Logger: 配置好的根日志记录器
    """
    settings = get_settings()

    # 获取日志级别
    log_level = LOG_LEVELS.get(settings.LOG_LEVEL.upper(), logging.INFO)

    # 配置根日志记录器
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # 清除任何现有的处理程序
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # 创建控制台处理程序
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(settings.LOG_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 如果提供了日志文件路径，则添加文件处理程序
    if log_file:
        # 确保日志目录存在
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 使用循环日志文件处理程序，每个文件最大 10MB，保留 5 个备份
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter(settings.LOG_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    # 设置第三方库的日志级别（通常可以使其更安静）
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logger.info(f"日志系统初始化完成，级别: {settings.LOG_LEVEL}")
    return logger


def get_logger(name: str) -> logging.Logger:
    """获取命名的日志记录器

    便于各个模块获取自己专用的日志记录器实例。

    Args:
        name: 模块名称

    Returns:
        logging.Logger: 命名的日志记录器
    """
    return logging.getLogger(name)