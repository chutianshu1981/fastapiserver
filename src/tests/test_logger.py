"""
日志模块测试
"""

import os
import shutil
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import pytest
from app.core.logger import setup_logging, get_logger
from app.core.config import get_settings


@pytest.fixture
def cleanup_test_logs():
    """清理测试日志的 fixture"""
    # 确保测试前目录不存在
    if Path("test_logs").exists():
        shutil.rmtree("test_logs")

    yield

    # 测试后清理
    if Path("test_logs").exists():
        shutil.rmtree("test_logs")


def test_logger_initialization():
    """测试日志初始化功能"""
    logger = setup_logging()
    assert isinstance(logger, logging.Logger)
    assert logger.level == logging.INFO  # 默认级别为 INFO

    # 验证是否至少有一个处理程序（控制台输出）
    assert len(logger.handlers) >= 1
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)


def test_logger_with_file(cleanup_test_logs):
    """测试文件日志功能"""
    test_log_path = Path("test_logs/test.log")
    logger = setup_logging(test_log_path)

    # 验证日志文件是否创建
    assert test_log_path.exists()
    assert test_log_path.is_file()

    # 验证是否有文件处理程序
    assert any(isinstance(h, RotatingFileHandler) for h in logger.handlers)


def test_log_levels(cleanup_test_logs):
    """测试不同日志级别"""
    test_log_path = Path("test_logs/level_test.log")
    logger = setup_logging(test_log_path)

    # 测试不同级别的日志记录
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")

    # 读取日志文件内容
    with open(test_log_path, "r", encoding="utf-8") as f:
        log_content = f.read()

    # INFO 级别下，debug 消息不应该出现
    assert "Debug message" not in log_content
    assert "Info message" in log_content
    assert "Warning message" in log_content
    assert "Error message" in log_content


def test_log_format(cleanup_test_logs):
    """测试日志格式"""
    test_log_path = Path("test_logs/format_test.log")
    settings = get_settings()
    logger = setup_logging(test_log_path)

    # 记录测试消息
    test_message = "Test format message"
    logger.info(test_message)

    # 读取日志文件内容
    with open(test_log_path, "r", encoding="utf-8") as f:
        log_content = f.read()

    # 验证日志格式
    assert test_message in log_content
    # 验证时间戳格式（格式：YYYY-MM-DD HH:MM:SS,mmm）
    log_lines = log_content.splitlines()
    test_log_line = [line for line in log_lines if test_message in line][0]

    # 提取并验证时间戳部分
    timestamp = test_log_line[:23]  # 包含毫秒的完整时间戳
    date_part = timestamp[:10]  # YYYY-MM-DD
    time_part = timestamp[11:19]  # HH:MM:SS

    assert len(date_part.split("-")) == 3  # 应该有年、月、日三部分
    assert len(time_part.split(":")) == 3  # 应该有时、分、秒三部分
    assert all(part.isdigit() for part in date_part.split("-"))  # 日期每部分都应该是数字
    assert all(part.isdigit() for part in time_part.split(":"))  # 时间每部分都应该是数字


def test_named_logger():
    """测试命名日志记录器"""
    logger_name = "test_module"
    named_logger = get_logger(logger_name)

    assert isinstance(named_logger, logging.Logger)
    assert named_logger.name == logger_name
