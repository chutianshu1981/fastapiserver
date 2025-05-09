"""
视频处理服务模块

该模块提供基于管道的模块化视频处理框架，支持异步处理、上下文隔离和可扩展的帧处理能力。
"""

import asyncio
import contextvars
import logging
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Generic, List, Optional, Protocol, TypeVar

import cv2
from app.core.config import get_settings
from app.core.logger import get_logger
from app.services.monitor import SystemMonitor

logger = get_logger(__name__)

# 上下文变量定义
pipeline_context = contextvars.ContextVar[str](
    "pipeline_context", default="default")
frame_context = contextvars.ContextVar[Dict[str, Any]](
    "frame_context", default={})


class FrameProcessor(Protocol):
    """帧处理器接口"""

    async def process(self, frame: Any) -> Any:
        """处理单个视频帧

        Args:
            frame: 输入视频帧

        Returns:
            Any: 处理后的视频帧
        """
        ...


class StorageManager(Protocol):
    """存储管理器接口"""

    async def save_frame(self, frame: Any, metadata: Dict[str, Any]) -> bool:
        """保存处理后的视频帧

        Args:
            frame: 处理后的视频帧
            metadata: 帧元数据

        Returns:
            bool: 保存是否成功
        """
        ...

    async def cleanup(self) -> None:
        """清理过期数据"""
        ...

    async def start(self) -> None:
        """启动存储管理器"""
        ...

    async def stop(self) -> None:
        """停止存储管理器"""
        ...


DataT = TypeVar('DataT')


class Pipeline(Generic[DataT], ABC):
    """视频处理管道抽象基类

    TypeVars:
        DataT: 处理数据的类型
    """

    def __init__(self, name: str, monitor: Optional[SystemMonitor] = None) -> None:
        """初始化处理管道

        Args:
            name: 管道名称
            monitor: 系统监控器(可选)
        """
        self.name = name
        self._processors: List[FrameProcessor] = []
        self._input_queue: asyncio.Queue[DataT] = asyncio.Queue()
        self._output_queue: asyncio.Queue[DataT] = asyncio.Queue()
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._monitor = monitor

    def add_processor(self, processor: FrameProcessor) -> None:
        """添加帧处理器

        Args:
            processor: 实现了 FrameProcessor 接口的处理器实例
        """
        self._processors.append(processor)

    async def push(self, data: DataT) -> None:
        """推送数据到管道输入队列

        Args:
            data: 输入数据
        """
        await self._input_queue.put(data)

    async def get(self) -> DataT:
        """从管道输出队列获取处理后的数据

        Returns:
            DataT: 处理后的数据
        """
        return await self._output_queue.get()

    @abstractmethod
    async def process_item(self, item: DataT) -> DataT:
        """处理单个数据项

        Args:
            item: 输入数据项

        Returns:
            DataT: 处理后的数据项
        """
        ...

    async def _worker(self) -> None:
        """管道工作器协程"""
        while self._running:
            try:
                # 设置管道上下文
                pipeline_context.set(self.name)

                # 获取输入数据
                start_time = time.time()
                item = await self._input_queue.get()

                # 处理数据
                result = await self.process_item(item)

                # 计算处理延迟
                latency = time.time() - start_time

                # 记录性能指标
                if self._monitor:
                    self._monitor.record_frame_processed(latency)

                # 将结果放入输出队列
                await self._output_queue.put(result)

            except Exception as e:
                logger.error(f"管道 {self.name} 处理异常: {e}")
                if self._monitor:
                    self._monitor.record_error()
                continue

    async def start(self) -> None:
        """启动管道处理"""
        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info(f"管道 {self.name} 已启动")

    async def stop(self) -> None:
        """停止管道处理"""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info(f"管道 {self.name} 已停止")


class VideoService:
    """视频处理服务

    管理视频处理管道、帧处理器和存储管理器的核心服务类。
    """

    def __init__(self) -> None:
        """初始化视频服务"""
        self._settings = get_settings()
        self._lock = threading.Lock()
        self._pipelines: Dict[str, Pipeline[Any]] = {}
        self._storage: Optional[StorageManager] = None

        # 初始化系统监控器
        self._monitor = SystemMonitor(
            check_interval=5,        # 5秒检查一次
            metrics_history_size=1000,  # 保留最近1000条指标
            alert_cpu_threshold=80.0,   # CPU使用率超过80%告警
            alert_memory_threshold=80.0,  # 内存使用率超过80%告警
            alert_disk_threshold=90.0    # 磁盘使用率超过90%告警
        )

    def register_pipeline(self, pipeline: Pipeline[Any]) -> None:
        """注册视频处理管道

        Args:
            pipeline: Pipeline 实例
        """
        # 为管道注入监控器
        if not pipeline._monitor:
            pipeline._monitor = self._monitor
        self._pipelines[pipeline.name] = pipeline

    def register_storage(self, storage: StorageManager) -> None:
        """注册存储管理器

        Args:
            storage: StorageManager 实例
        """
        self._storage = storage

    async def start(self) -> None:
        """启动视频服务"""
        # 启动监控器
        await self._monitor.start()

        # 启动存储管理器
        if self._storage:
            await self._storage.start()

        # 启动所有管道
        for pipeline in self._pipelines.values():
            await pipeline.start()

        logger.info("视频服务已启动")

    async def stop(self) -> None:
        """停止视频服务"""
        # 停止所有管道
        for pipeline in self._pipelines.values():
            await pipeline.stop()

        # 停止存储管理器
        if self._storage:
            await self._storage.stop()

        # 停止监控器
        await self._monitor.stop()

        logger.info("视频服务已停止")

    async def __aenter__(self) -> "VideoService":
        """异步上下文管理器入口"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器退出"""
        await self.stop()

    def get_health_status(self) -> Dict[str, Any]:
        """获取服务健康状态

        Returns:
            Dict[str, Any]: 包含服务状态信息的字典
        """
        status = self._monitor.get_health_status()

        # 添加管道状态
        status['pipelines'] = {
            name: "running" if p._running else "stopped"
            for name, p in self._pipelines.items()
        }

        # 添加存储状态
        status['storage'] = "active" if self._storage else "not_configured"

        return status
