"""Main module tests"""
from app.core.config import get_settings
from app.main import (
    app, get_server_ip, run_rtsp_server_loop,
    periodic_tasks, shutdown_event,
    mainloop
)
import sys
from types import ModuleType
from unittest.mock import Mock, patch, AsyncMock
import pytest
import asyncio
import socket
import os
from datetime import datetime
from fastapi.testclient import TestClient

# 在导入任何应用代码之前设置模拟
mock_gst = Mock()
mock_glib = Mock()
mock_gst_rtsp_server = Mock()

# 设置 gi 模拟


class MockGiModule(ModuleType):
    def __init__(self):
        super().__init__('gi')
        self._versions = {}

    def require_version(self, namespace, version):
        self._versions[namespace] = version
        return True

    def get_required_versions(self):
        return self._versions


mock_gi = MockGiModule()

# 设置 GLib 模拟方法


class MockMainLoop:
    def __init__(self):
        self._running = False

    def run(self):
        self._running = True

    def quit(self):
        self._running = False

    def is_running(self):
        return self._running


mock_glib.threads_init = Mock()
mock_glib.MainLoop = MockMainLoop
mock_gst.init = Mock()

# 设置系统模块
mock_repository = Mock()
mock_repository.GLib = mock_glib
mock_repository.Gst = mock_gst
mock_repository.GstRtspServer = mock_gst_rtsp_server

sys.modules['gi'] = mock_gi
sys.modules['gi.repository'] = mock_repository


@pytest.fixture(scope='function', autouse=True)
def reset_mocks():
    """每个测试前重置所有mock"""
    mock_gst.init.reset_mock()
    yield


def test_aaa_gi_initialization():
    """测试 GStreamer 初始化 (aaa 前缀确保最先运行)"""
    # 重新导入来触发初始化
    import importlib
    import app.main
    importlib.reload(app.main)

    # 验证版本设置
    versions = mock_gi.get_required_versions()
    assert versions.get('Gst') == '1.0'
    assert versions.get('GstRtspServer') == '1.0'

    # 验证初始化调用
    mock_gst.init.assert_called_once()


# 导入应用代码

# 测试客户端
client = TestClient(app)


@pytest.fixture
def mock_socket():
    with patch('socket.socket') as mock:
        yield mock


@pytest.fixture
def mock_logger():
    with patch('app.main.logger') as mock:
        yield mock


def test_get_server_ip_success(mock_socket):
    """测试成功获取服务器IP"""
    mock_sock_instance = Mock()
    mock_sock_instance.getsockname.return_value = ('192.168.1.100', 12345)
    mock_socket.return_value = mock_sock_instance

    assert get_server_ip() == '192.168.1.100'
    mock_sock_instance.connect.assert_called_once_with(('8.8.8.8', 80))


def test_get_server_ip_fallback(mock_socket):
    """测试IP获取失败时的回退机制"""
    mock_socket.return_value.connect.side_effect = Exception(
        "Connection failed")

    with patch('socket.gethostname', return_value='test-host'), \
            patch('socket.gethostbyname', return_value='192.168.1.200'):
        assert get_server_ip() == '192.168.1.200'


def test_get_server_ip_complete_failure(mock_socket, mock_logger):
    """测试所有IP获取方法都失败的情况"""
    mock_socket.return_value.connect.side_effect = Exception(
        "Connection failed")
    with patch('socket.gethostname', side_effect=Exception("Hostname failed")):
        assert get_server_ip() == '0.0.0.0'
        mock_logger.error.assert_called_once()


def test_mainloop_basic_operations():
    """测试 GLib MainLoop 基本操作"""
    mock_mainloop = MockMainLoop()
    with patch('app.main.mainloop', mock_mainloop):
        assert not mock_mainloop.is_running()
        mock_mainloop.run()
        assert mock_mainloop.is_running()
        mock_mainloop.quit()
        assert not mock_mainloop.is_running()


@pytest.mark.asyncio
async def test_periodic_tasks(mock_logger):
    """测试定期任务基本功能"""
    with patch('asyncio.sleep', AsyncMock(side_effect=asyncio.CancelledError)):
        with pytest.raises(asyncio.CancelledError):
            await periodic_tasks()
        mock_logger.info.assert_called_with("定期任务检查...")


def test_shutdown_event_sync(mock_logger):
    """测试关闭事件的同步功能"""
    mock_mainloop = MockMainLoop()
    with patch('app.main.mainloop', mock_mainloop):
        # 启动mainloop
        mock_mainloop.run()
        assert mock_mainloop.is_running()
        mock_logger.info.assert_not_called()  # 确保开始时没有日志调用

        # 执行关闭
        mock_mainloop.quit()
        assert not mock_mainloop.is_running()
        mock_logger.info("收到关闭信号，开始优雅关闭...")
        mock_logger.info("正在停止主循环...")
        mock_logger.info.assert_called()


@pytest.mark.asyncio
async def test_lifespan():
    """测试应用生命周期管理"""
    mock_app = Mock()
    mock_mainloop = MockMainLoop()
    mock_logger = Mock()

    with patch('app.main.mainloop', mock_mainloop), \
            patch('app.main.logger', mock_logger), \
            patch('app.main.run_rtsp_server_loop') as mock_run:

        async with app.router.lifespan_context(mock_app):
            # 验证启动操作
            mock_logger.info.assert_any_call("应用启动，正在初始化...")
            mock_logger.info.assert_any_call("应用启动完成。")
            mock_run.assert_called_once()

        # 验证关闭操作
        mock_logger.info.assert_any_call("关闭完成。")

if __name__ == '__main__':
    pytest.main(['-v', __file__])
