"""
存储管理模块

提供视频帧的分块存储、自动清理和存储空间监控功能。
"""

import asyncio
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.logger import get_logger
from app.services.video_service import StorageManager

logger = get_logger(__name__)


class ChunkedStorageManager(StorageManager):
    """分块存储管理器

    实现基于时间分块的存储策略，自动清理过期数据，并监控存储空间使用情况。
    """

    def __init__(
        self,
        base_dir: Path,
        chunk_interval: int = 3600,  # 默认1小时一个块
        max_age_hours: int = 24,     # 默认保存24小时
        max_space_gb: float = 10.0,  # 默认最大使用10GB空间
        check_interval: int = 300    # 默认5分钟检查一次
    ):
        """
        Args:
            base_dir: 基础存储目录
            chunk_interval: 分块时间间隔(秒)
            max_age_hours: 数据最大保存时间(小时)
            max_space_gb: 最大存储空间(GB)
            check_interval: 清理检查间隔(秒)
        """
        self.base_dir = base_dir
        self.chunk_interval = chunk_interval
        self.max_age = timedelta(hours=max_age_hours)
        self.max_space = max_space_gb * 1024 * 1024 * 1024  # 转换为字节
        self.check_interval = check_interval

        # 创建基础目录
        os.makedirs(base_dir, exist_ok=True)

        # 存储监控指标
        self._total_frames = 0
        self._total_bytes = 0
        self._current_chunk_dir: Optional[Path] = None
        self._current_chunk_time = 0

        # 启动自动清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    def _ensure_chunk_dir(self) -> Path:
        """确保当前块目录存在并返回

        Returns:
            Path: 当前块目录的路径

        Raises:
            RuntimeError: 如果无法创建或访问存储目录
        """
        current_time = int(time.time())
        chunk_time = current_time - (current_time % self.chunk_interval)

        # 如果时间块改变或目录未初始化，创建新目录
        if chunk_time != self._current_chunk_time or self._current_chunk_dir is None:
            chunk_dir = self.base_dir / \
                datetime.fromtimestamp(chunk_time).strftime("%Y%m%d_%H%M%S")
            try:
                os.makedirs(chunk_dir, exist_ok=True)
            except OSError as e:
                raise RuntimeError(f"无法创建存储目录: {e}")

            self._current_chunk_dir = chunk_dir
            self._current_chunk_time = chunk_time

        if self._current_chunk_dir is None:
            raise RuntimeError("存储目录未初始化")

        return self._current_chunk_dir

    async def save_frame(self, frame: Any, metadata: Dict[str, Any]) -> bool:
        """保存处理后的视频帧

        Args:
            frame: 处理后的视频帧
            metadata: 帧元数据

        Returns:
            bool: 保存是否成功
        """
        try:
            # 获取当前块目录
            chunk_dir = self._ensure_chunk_dir()

            # 生成文件名
            timestamp = metadata.get('timestamp', int(time.time() * 1000))
            frame_path = chunk_dir / f"frame_{timestamp}.jpg"

            # 保存帧
            with open(frame_path, 'wb') as f:
                f.write(frame)

            # 更新指标
            self._total_frames += 1
            self._total_bytes += frame_path.stat().st_size

            # 每保存100帧记录一次指标
            if self._total_frames % 100 == 0:
                self._log_metrics()

            return True

        except Exception as e:
            logger.error(f"保存帧失败: {e}")
            return False

    async def cleanup(self) -> None:
        """清理过期数据"""
        try:
            current_time = datetime.now()
            total_cleaned = 0

            # 遍历所有时间块目录
            for chunk_dir in self.base_dir.iterdir():
                if not chunk_dir.is_dir():
                    continue

                # 检查目录年龄
                try:
                    dir_time = datetime.strptime(
                        chunk_dir.name, "%Y%m%d_%H%M%S")
                    if current_time - dir_time > self.max_age:
                        shutil.rmtree(chunk_dir)
                        total_cleaned += 1
                except ValueError:
                    continue

            if total_cleaned > 0:
                logger.info(f"已清理 {total_cleaned} 个过期数据块")

        except Exception as e:
            logger.error(f"清理过期数据失败: {e}")

    async def _monitor_storage(self) -> None:
        """监控存储空间使用情况"""
        while self._running:
            try:
                # 检查总存储空间使用
                total_size = sum(
                    f.stat().st_size
                    for f in self.base_dir.rglob('*')
                    if f.is_file()
                )

                # 如果超过限制，强制清理最旧的数据
                if total_size > self.max_space:
                    logger.warning(
                        f"存储空间超出限制: {total_size/1024/1024/1024:.2f}GB "
                        f"> {self.max_space/1024/1024/1024:.2f}GB"
                    )
                    # 获取并排序所有块目录
                    chunk_dirs = sorted(
                        [d for d in self.base_dir.iterdir() if d.is_dir()],
                        key=lambda x: x.name
                    )

                    # 删除最旧的块，直到空间足够
                    while total_size > self.max_space and chunk_dirs:
                        oldest_dir = chunk_dirs.pop(0)
                        dir_size = sum(
                            f.stat().st_size for f in oldest_dir.rglob('*'))
                        shutil.rmtree(oldest_dir)
                        total_size -= dir_size
                        logger.info(f"已删除最旧数据块: {oldest_dir.name}")

                # 执行常规清理
                await self.cleanup()

            except Exception as e:
                logger.error(f"存储监控失败: {e}")

            # 等待下次检查
            await asyncio.sleep(self.check_interval)

    def _log_metrics(self) -> None:
        """记录存储指标"""
        try:
            total_size_gb = self._total_bytes / 1024 / 1024 / 1024
            logger.info(
                f"存储指标 - 总帧数: {self._total_frames}, "
                f"总大小: {total_size_gb:.2f}GB, "
                f"平均帧大小: {self._total_bytes/self._total_frames/1024:.2f}KB"
            )
        except Exception as e:
            logger.error(f"记录存储指标失败: {e}")

    async def start(self) -> None:
        """启动存储管理器"""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._monitor_storage())
        logger.info("存储管理器已启动")

    async def stop(self) -> None:
        """停止存储管理器"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("存储管理器已停止")
