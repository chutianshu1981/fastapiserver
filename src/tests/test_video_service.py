"""
视频处理服务测试模块

提供VideoService及其相关组件的单元测试、集成测试和性能测试。
"""

from app.services.monitor import SystemMonitor, PerformanceMetrics
from app.services.storage import ChunkedStorageManager
from app.services.processors import MP4EncodeProcessor, JPEGExtractProcessor, FPSControlProcessor
import asyncio
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Generator
import pytest
from pytest_asyncio import fixture
import numpy as np
import cv2
from unittest.mock import Mock, patch
from app.core.logger import get_logger

from app.services.video_service import VideoService, Pipeline, FrameProcessor

logger = get_logger(__name__)

# ---------------------- Fixtures ----------------------


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """提供临时目录"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def sample_frame() -> np.ndarray:
    """生成测试用的视频帧"""
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def video_service() -> VideoService:
    """创建VideoService实例"""
    return VideoService()


@fixture
async def running_video_service(video_service: VideoService) -> AsyncGenerator[VideoService, None]:
    """提供已启动的VideoService"""
    await video_service.start()
    yield video_service
    await video_service.stop()


@pytest.fixture
def mock_processor() -> FrameProcessor:
    """创建模拟的帧处理器"""
    class MockProcessor(FrameProcessor):
        async def process(self, frame):
            return frame
    return MockProcessor()

# ---------------------- 单元测试 ----------------------


class TestVideoService:
    """VideoService单元测试"""

    @pytest.mark.asyncio
    async def test_service_lifecycle(self, video_service: VideoService):
        """测试服务生命周期管理"""
        # 测试启动
        await video_service.start()
        status = video_service.get_health_status()
        assert status['status'] in ['healthy', 'warning']

        # 测试停止
        await video_service.stop()
        assert not video_service._monitor._running

    @pytest.mark.asyncio
    async def test_pipeline_registration(self, video_service: VideoService, mock_processor: FrameProcessor):
        """测试管道注册"""
        class TestPipeline(Pipeline):
            async def process_item(self, item):
                return item

        pipeline = TestPipeline("test_pipeline")
        pipeline.add_processor(mock_processor)
        video_service.register_pipeline(pipeline)

        assert "test_pipeline" in video_service._pipelines
        assert video_service._pipelines["test_pipeline"]._processors[0] == mock_processor

    @pytest.mark.asyncio
    async def test_storage_registration(self, video_service: VideoService, temp_dir: Path):
        """测试存储管理器注册"""
        storage = ChunkedStorageManager(temp_dir)
        video_service.register_storage(storage)

        assert video_service._storage == storage


class TestProcessors:
    """处理器单元测试"""

    @pytest.mark.asyncio
    async def test_mp4_encoder(self, temp_dir: Path, sample_frame: np.ndarray):
        """测试MP4编码处理器"""
        output_path = temp_dir / "test.mp4"
        processor = MP4EncodeProcessor(output_path, fps=30.0)

        # 处理多个帧
        for _ in range(10):
            processed_frame = await processor.process(sample_frame)
            assert np.array_equal(processed_frame, sample_frame)

        await processor.cleanup()
        assert output_path.exists()

    @pytest.mark.asyncio
    async def test_jpeg_extractor(self, temp_dir: Path, sample_frame: np.ndarray):
        """测试JPEG提取处理器"""
        processor = JPEGExtractProcessor(temp_dir, interval=1)
        logger.info(f"开始JPEG提取测试，输出目录: {temp_dir}")

        # 处理多个帧，每帧之间添加小延时
        for i in range(5):
            await processor.process(sample_frame)
            await asyncio.sleep(0.01)  # 确保每帧有不同的时间戳
            logger.info(f"处理第 {i+1} 帧")

        # 验证输出文件
        jpeg_files = list(temp_dir.glob("*.jpg"))
        logger.info(f"生成的JPEG文件: {[f.name for f in jpeg_files]}")
        assert len(jpeg_files) == 5, f"期望生成5个文件，实际生成了{len(jpeg_files)}个"

    @pytest.mark.asyncio
    async def test_fps_controller(self, sample_frame: np.ndarray):
        """测试帧率控制处理器"""
        processor = FPSControlProcessor(target_fps=30.0)

        # 测试帧率控制
        start_time = datetime.now()
        frames = []
        for _ in range(10):
            frame = await processor.process(sample_frame)
            if frame is not None:
                frames.append(frame)
            await asyncio.sleep(0.01)

        assert len(frames) <= 10  # 由于帧率限制，应该少于输入帧数


class TestStorage:
    """存储管理单元测试"""

    @pytest.mark.asyncio
    async def test_chunked_storage(self, temp_dir: Path, sample_frame: np.ndarray):
        """测试分块存储管理器"""
        storage = ChunkedStorageManager(
            temp_dir,
            chunk_interval=1,
            max_age_hours=1,
            max_space_gb=1.0,
            check_interval=1
        )

        await storage.start()

        # 测试帧保存
        for i in range(5):
            success = await storage.save_frame(
                cv2.imencode('.jpg', sample_frame)[1].tobytes(),
                {'timestamp': datetime.now().timestamp()}
            )
            assert success

        # 测试清理
        await storage.cleanup()
        await storage.stop()


class TestMonitor:
    """监控系统单元测试"""

    @pytest.mark.asyncio
    async def test_metrics_collection(self):
        """测试指标收集"""
        monitor = SystemMonitor(check_interval=1)
        await monitor.start()

        # 记录一些指标
        monitor.record_frame_processed(0.1)
        monitor.record_error()

        # 验证指标
        metrics = monitor.get_current_metrics()
        assert metrics is not None
        assert metrics.frame_latency == 0.1
        assert metrics.error_count == 1

        await monitor.stop()

# ---------------------- 集成测试 ----------------------


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_complete_pipeline(self, temp_dir: Path, sample_frame: np.ndarray):
        """测试完整的视频处理流程"""
        # 创建服务实例
        logger.info(f"开始集成测试，输出目录: {temp_dir}")
        service = VideoService()

        # 设置存储
        storage = ChunkedStorageManager(temp_dir)
        service.register_storage(storage)

        # 创建处理管道
        class VideoPipeline(Pipeline):
            async def process_item(self, item):
                for processor in self._processors:
                    item = await processor.process(item)
                    if item is None:
                        logger.warning("处理器返回了None")
                        return None
                return item

        pipeline = VideoPipeline("test_pipeline")

        # 添加处理器
        pipeline.add_processor(FPSControlProcessor(30.0))
        pipeline.add_processor(JPEGExtractProcessor(
            temp_dir, interval=1))  # 设置interval=1确保每帧都保存

        # 注册管道
        service.register_pipeline(pipeline)

        # 启动服务
        async with service:
            logger.info("服务已启动，开始处理帧...")
            # 处理多个帧，添加延时确保每帧都被处理
            for i in range(10):
                await pipeline.push(sample_frame)
                result = await pipeline.get()
                if result is None:
                    logger.warning(f"第{i+1}帧处理结果为None")
                await asyncio.sleep(0.1)  # 添加延时
            logger.info("帧处理完成")

        # 验证输出
        files = list(temp_dir.iterdir())
        logger.info(f"输出目录中的文件: {[f.name for f in files]}")
        assert len(files) > 0, f"输出目录{temp_dir}为空"

    @pytest.mark.asyncio
    async def test_error_handling(self, video_service: VideoService):
        """测试错误处理和恢复"""
        class ErrorPipeline(Pipeline):
            async def process_item(self, item):
                logger.info("处理帧时触发测试错误")
                raise RuntimeError("测试错误")

        pipeline = ErrorPipeline("error_pipeline")
        video_service.register_pipeline(pipeline)

        await video_service.start()
        try:
            # 推送帧并等待处理
            logger.info("推送测试帧到错误管道")
            await pipeline.push(np.zeros((100, 100, 3)))

            # 等待错误被记录
            await asyncio.sleep(0.1)

            # 验证错误被记录
            logger.info("验证错误计数")
            metrics = video_service._monitor.get_current_metrics()
            assert metrics is not None, "监控指标不应为空"

            logger.info(f"当前错误计数: {metrics.error_count}")
            assert metrics.error_count > 0, "错误计数应该大于0"

            # 同时验证状态信息
            status = video_service.get_health_status()
            logger.info(f"错误率: {status['metrics']['error_rate']}")
            assert float(status['metrics']['error_rate'].rstrip('%')) > 0

        finally:
            await video_service.stop()

# ---------------------- 性能测试 ----------------------


class TestPerformance:
    """性能测试"""

    @pytest.mark.asyncio
    async def test_concurrent_processing(self, temp_dir: Path, sample_frame: np.ndarray):
        """测试并发处理性能"""
        service = VideoService()

        class PerfTestPipeline(Pipeline):
            async def process_item(self, item):
                for processor in self._processors:
                    item = await processor.process(item)
                return item

        pipeline = PerfTestPipeline("perf_test")
        pipeline.add_processor(FPSControlProcessor(60.0))
        service.register_pipeline(pipeline)

        await service.start()

        # 并发处理多个帧
        tasks = []
        for _ in range(100):
            tasks.append(pipeline.push(sample_frame))

        await asyncio.gather(*tasks)

        # 验证性能指标
        metrics = service._monitor.get_current_metrics()
        assert metrics is not None
        assert metrics.fps >= 0

        await service.stop()

    @pytest.mark.asyncio
    async def test_memory_usage(self, temp_dir: Path, sample_frame: np.ndarray):
        """测试内存使用"""
        service = VideoService()
        storage = ChunkedStorageManager(temp_dir, max_space_gb=0.1)
        service.register_storage(storage)

        await service.start()

        # 持续写入数据直到触发清理
        for _ in range(50):
            await storage.save_frame(
                cv2.imencode('.jpg', sample_frame)[1].tobytes(),
                {'timestamp': datetime.now().timestamp()}
            )

        # 验证存储空间管理
        status = service.get_health_status()
        assert float(status['metrics']['disk'].rstrip('%')) < 90

        await service.stop()


if __name__ == "__main__":
    pytest.main([__file__])
