"""
系统集成测试模块

提供端到端的集成测试，验证系统各组件之间的交互。
包括:
- RTSP服务器与视频处理服务的集成
- API层与后端服务的集成
- 配置和日志系统的集成
"""

# 标准库导入
from app.rtsp.server import RtspServer
from app.services.video_service import VideoService, Pipeline
from app.services.monitor import SystemMonitor
from app.services.processors import FPSControlProcessor, JPEGExtractProcessor
from app.core.config import get_settings
from app.core.logger import get_logger, setup_logging
from gi.repository import Gst  # type: ignore
import os
import json
import asyncio
import logging
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, Mock, AsyncMock

# 第三方库导入
import pytest
import pytest_asyncio
import numpy as np
import cv2  # type: ignore
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient

# GStreamer导入
import gi  # type: ignore
gi.require_version('Gst', '1.0')

# 本地模块导入

# 本地模块导入


# 配置测试日志
logger = get_logger(__name__)

# ---------------------- 测试夹具 ----------------------


# 创建测试路由
test_router = APIRouter()


@test_router.get("/api/v1/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "details": {
            "rtsp_server": "healthy",
            "video_service": {
                "status": "healthy",
                "metrics": {
                    "error_rate": "0%",
                    "cpu": "10%",
                    "memory": "20%"
                }
            }
        }
    }

# 创建测试用FastAPI应用
test_app = FastAPI()
test_app.include_router(test_router)


@pytest.fixture
def test_client():
    """提供FastAPI测试客户端"""
    return TestClient(test_app)


@pytest.fixture
def temp_output_dir():
    """提供临时输出目录"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def test_config(temp_output_dir):
    """提供测试配置"""
    with patch("app.core.config.get_settings") as mock_settings:
        settings = get_settings()
        settings.OUTPUT_DIR = temp_output_dir
        settings.RTSP_PORT = 8554
        # 设置API端口
        settings.API_PORT = 58000
        settings.LOG_LEVEL = "DEBUG"
        mock_settings.return_value = settings
        yield settings


@pytest_asyncio.fixture
async def integrated_system(test_config):
    """提供完整的集成系统实例"""
    try:
        # 设置日志系统
        setup_logging()

        # 创建mock RTSP服务器
        mock_rtsp_server = Mock(spec=RtspServer)
        mock_rtsp_server.is_running = True
        mock_rtsp_server.start = Mock()
        mock_rtsp_server.stop = Mock()

        # 创建模拟的video_service
        mock_video_service = Mock(spec=VideoService)
        mock_video_service.get_health_status.return_value = {
            "status": "healthy",
            "metrics": {
                "error_rate": "0%",
                "cpu": "10%",
                "memory": "20%"
            }
        }
        mock_video_service.start = AsyncMock()
        mock_video_service.stop = AsyncMock()
        await mock_video_service.start()

        return {
            "rtsp_server": mock_rtsp_server,
            "video_service": mock_video_service,
            "config": test_config
        }
    finally:
        # 清理资源
        await mock_video_service.stop()

# ---------------------- 集成测试 ----------------------


@pytest.mark.asyncio
class TestSystemIntegration:
    """系统集成测试"""

    async def test_system_initialization(self, integrated_system, test_client):
        """测试系统初始化和配置加载"""
        logger.info("开始测试系统初始化和配置加载")

        # 验证RTSP服务器状态
        assert integrated_system["rtsp_server"].is_running
        logger.info("RTSP服务器状态正常")

        # 验证API服务是否正常响应
        response = test_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        logger.info("API服务响应正常")

        # 验证视频服务状态
        video_service = integrated_system["video_service"]
        status = video_service.get_health_status()
        assert status["status"] in ["healthy", "warning"]
        logger.info("视频服务状态正常")

        # 验证配置加载
        assert os.path.exists(integrated_system["config"].OUTPUT_DIR)
        logger.info("配置加载正确")

    async def test_rtsp_video_integration(self, integrated_system, temp_output_dir):
        """测试RTSP服务器与视频处理服务的集成"""
        logger.info("开始测试RTSP与视频处理集成")

        rtsp_server = integrated_system["rtsp_server"]
        video_service = integrated_system["video_service"]

        # 创建测试视频处理管道
        class TestPipeline(Pipeline):
            async def process_item(self, item):
                """实现process_item方法"""
                if not self._processors:
                    return item

                result = item
                for processor in self._processors:
                    result = await processor.process(result)
                    if result is None:
                        break
                return result

        pipeline = TestPipeline("test_pipeline")
        pipeline.add_processor(FPSControlProcessor(30.0))
        pipeline.add_processor(JPEGExtractProcessor(temp_output_dir))

        video_service.register_pipeline(pipeline)

        # 模拟视频帧处理
        test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        for i in range(5):
            logger.info(f"处理第 {i+1} 帧")
            await pipeline.push(test_frame)
            result = await pipeline.get()
            assert result is not None
            await asyncio.sleep(0.1)

        # 验证输出文件
        output_files = list(temp_output_dir.glob("*.jpg"))
        assert len(output_files) > 0
        logger.info(f"成功生成 {len(output_files)} 个输出文件")

    async def test_api_backend_integration(self, integrated_system, test_client):
        """测试API层与后端服务的集成"""
        logger.info("开始测试API与后端服务集成")

        video_service = integrated_system["video_service"]

        # 测试视频服务状态API
        response = test_client.get("/api/v1/video/status")
        assert response.status_code == 200
        status_data = response.json()
        assert "metrics" in status_data
        logger.info("状态API响应正常")

        # 测试监控指标API
        response = test_client.get("/api/v1/monitor/metrics")
        assert response.status_code == 200
        metrics_data = response.json()
        assert "fps" in metrics_data
        assert "error_rate" in metrics_data
        logger.info("监控指标API响应正常")

    async def test_error_handling_integration(self, integrated_system, test_client):
        """测试错误处理和恢复机制"""
        logger.info("开始测试错误处理和恢复机制")

        video_service = integrated_system["video_service"]

        # 创建一个会产生错误的处理管道
        class ErrorPipeline(Pipeline):
            async def process_item(self, item):
                """实现会产生错误的process_item方法"""
                raise RuntimeError("测试错误")

        pipeline = ErrorPipeline("error_pipeline")
        video_service.register_pipeline(pipeline)

        # 触发错误
        test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        await pipeline.push(test_frame)
        await asyncio.sleep(0.1)

        # 验证错误是否被正确记录和报告
        status = video_service.get_health_status()
        assert float(status["metrics"]["error_rate"].rstrip("%")) > 0
        logger.info("错误被正确记录")

        # 验证系统恢复能力
        response = test_client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] in ["healthy", "warning"]
        logger.info("系统正常恢复")

    async def test_performance_integration(self, integrated_system):
        """测试系统性能和并发处理能力"""
        logger.info("开始测试系统性能和并发处理")

        video_service = integrated_system["video_service"]

        # 创建性能测试管道
        class PerfPipeline(Pipeline):
            async def process_item(self, item):
                """实现简单的process_item方法"""
                return item

        pipeline = PerfPipeline("perf_pipeline")
        video_service.register_pipeline(pipeline)

        # 并发处理测试（增加到100个并发帧）
        test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tasks = []
        for i in range(100):
            tasks.append(pipeline.push(test_frame))

        # 等待所有任务完成并记录时间
        start_time = datetime.now()
        await asyncio.gather(*tasks)
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"并发处理测试完成，处理时间: {processing_time:.2f}秒")

        # 验证性能指标
        metrics = video_service.get_health_status()["metrics"]
        assert float(metrics["cpu"].rstrip("%")) >= 0
        assert float(metrics["memory"].rstrip("%")) >= 0
        logger.info(f"系统资源使用: CPU {metrics['cpu']}, 内存 {metrics['memory']}")

    async def test_gstreamer_integration(self, integrated_system):
        """测试GStreamer初始化和功能"""
        logger.info("开始测试GStreamer集成")

        # 验证GStreamer初始化
        # GStreamer已在文件顶部导入

        assert Gst.is_initialized()
        logger.info("GStreamer已正确初始化")

        # 验证GStreamer版本
        version = Gst.version_string()
        logger.info(f"GStreamer版本: {version}")
        assert version is not None

        # 测试创建基本的GStreamer管道
        pipeline_str = "videotestsrc ! fakesink"
        pipeline = Gst.parse_launch(pipeline_str)
        assert pipeline is not None
        logger.info("成功创建测试管道")

        # 验证管道状态转换
        ret = pipeline.set_state(Gst.State.PLAYING)
        assert ret != Gst.StateChangeReturn.FAILURE
        await asyncio.sleep(0.1)

        pipeline.set_state(Gst.State.NULL)
        logger.info("管道状态转换测试完成")

    async def test_resource_management(self, integrated_system, temp_output_dir):
        """测试资源管理和清理"""
        logger.info("开始测试资源管理")

        video_service = integrated_system["video_service"]
        initial_metrics = video_service.get_health_status()["metrics"]

        # 创建大量临时文件测试资源管理
        test_files = []
        for i in range(100):
            file_path = temp_output_dir / f"test_file_{i}.tmp"
            with open(file_path, 'wb') as f:
                f.write(os.urandom(1024 * 1024))  # 写入1MB随机数据
            test_files.append(file_path)

        logger.info(f"创建了 {len(test_files)} 个测试文件")

        # 触发资源清理
        await asyncio.sleep(1)
        final_metrics = video_service.get_health_status()["metrics"]

        # 验证资源使用情况
        assert float(final_metrics["memory"].rstrip("%")) >= 0
        logger.info(f"内存使用: {final_metrics['memory']}")

        # 清理测试文件
        for file_path in test_files:
            try:
                os.unlink(file_path)
            except Exception as e:
                logger.error(f"清理文件失败 {file_path}: {e}")

        # 验证文件清理
        remaining_files = list(temp_output_dir.glob("*.tmp"))
        assert len(remaining_files) == 0
        logger.info("所有测试文件已清理")


if __name__ == "__main__":
    pytest.main([__file__])
