"""
RTSP 服务器单元测试模块
"""
import os
import time
import pytest
import logging
from threading import Thread, Event
from pathlib import Path

from app.rtsp.server import RtspServer
from app.core.config import get_settings

# 配置测试日志
logger = logging.getLogger(__name__)


@pytest.fixture
def rtsp_server():
    """RTSP 服务器测试夹具"""
    server = RtspServer()
    yield server
    if server.is_running:
        server.stop()


def test_server_initialization(rtsp_server):
    """测试服务器初始化"""
    assert not rtsp_server.is_running
    assert rtsp_server.get_client_count() == 0
    assert os.path.exists(get_settings().OUTPUT_DIR)


def test_server_start_stop(rtsp_server):
    """测试服务器启动和停止"""
    # 在单独的线程中启动服务器
    server_thread = Thread(target=rtsp_server.start)
    server_thread.daemon = True
    server_thread.start()

    # 等待服务器启动
    time.sleep(1)
    assert rtsp_server.is_running

    # 停止服务器
    rtsp_server.stop()
    assert not rtsp_server.is_running


def test_context_manager():
    """测试上下文管理器"""
    server_ready = Event()
    server_stopped = Event()

    def server_thread():
        try:
            with RtspServer() as server:
                logger.info("服务器已启动")
                server_ready.set()

                # 验证服务器状态
                assert server.is_running, "服务器应该处于运行状态"

                # 等待停止信号
                server_stopped.wait(timeout=3)
                logger.info("开始停止服务器")
        except Exception as e:
            logger.error(f"服务器运行出错: {str(e)}")
            raise

    thread = Thread(target=server_thread)
    thread.daemon = True
    thread.start()

    # 等待服务器启动
    assert server_ready.wait(timeout=10), "服务器启动超时"

    # 验证服务器是否成功启动
    time.sleep(1)

    # 请求停止服务器
    server_stopped.set()
    # 等待线程结束
    thread.join(timeout=5)


def test_recording_path_format(rtsp_server):
    """测试录制文件路径格式"""
    path = rtsp_server._get_recording_path()
    assert path.suffix == '.mp4'
    assert path.stem.startswith('recording_')
    assert path.parent == get_settings().OUTPUT_DIR


def test_client_management(rtsp_server):
    """测试客户端管理"""
    assert rtsp_server.get_client_count() == 0
    # 由于需要实际的RTSP客户端连接才能完全测试
    # 这里只测试基本的计数功能
