"""
视频帧处理器实现模块

提供多种视频帧处理器的具体实现，包括MP4编码、JPEG提取和帧率控制等功能。
"""

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np
from app.core.logger import get_logger
from app.services.video_service import FrameProcessor

logger = get_logger(__name__)


class MP4EncodeProcessor(FrameProcessor):
    """MP4视频编码处理器"""

    def __init__(self, output_path: Path, fps: float = 30.0, codec: str = 'mp4v'):
        self.output_path = output_path
        self.fps = fps
        self.codec = codec
        self.writer: Optional[cv2.VideoWriter] = None
        self._frame_count = 0
        self._start_time = time.time()

    async def process(self, frame: np.ndarray) -> np.ndarray:
        """编码处理视频帧

        Args:
            frame: OpenCV格式的视频帧

        Returns:
            处理后的视频帧
        """
        if self.writer is None:
            fourcc = cv2.VideoWriter_fourcc(*self.codec)
            height, width = frame.shape[:2]
            self.writer = cv2.VideoWriter(
                str(self.output_path),
                fourcc,
                self.fps,
                (width, height)
            )

        self.writer.write(frame)
        self._frame_count += 1

        # 记录性能指标
        if self._frame_count % 100 == 0:
            elapsed = time.time() - self._start_time
            actual_fps = self._frame_count / elapsed
            logger.info(
                f"MP4编码性能指标 - 目标FPS: {self.fps:.2f}, 实际FPS: {actual_fps:.2f}")

        return frame

    async def cleanup(self):
        """清理资源"""
        if self.writer:
            self.writer.release()


class JPEGExtractProcessor(FrameProcessor):
    """JPEG帧提取处理器"""

    def __init__(self, output_dir: Path, quality: int = 95, interval: int = 30):
        """
        Args:
            output_dir: 输出目录
            quality: JPEG压缩质量(0-100)
            interval: 提取帧的间隔
        """
        self.output_dir = output_dir
        self.quality = quality
        self.interval = interval
        self._frame_count = 0

        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)

    async def process(self, frame: np.ndarray) -> np.ndarray:
        """提取并保存JPEG帧

        Args:
            frame: OpenCV格式的视频帧

        Returns:
            原始视频帧
        """
        self._frame_count += 1

        if self._frame_count % self.interval == 0:
            timestamp = int(time.time() * 1000)
            output_path = self.output_dir / f"frame_{timestamp}.jpg"

            # 保存JPEG
            success = cv2.imwrite(
                str(output_path),
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, self.quality]
            )

            if success:
                logger.debug(f"保存JPEG帧: {output_path}")
            else:
                logger.error(f"保存JPEG帧失败: {output_path}")

        return frame


class FPSControlProcessor(FrameProcessor):
    """帧率控制处理器"""

    def __init__(self, target_fps: float):
        """
        Args:
            target_fps: 目标帧率
        """
        self.target_fps = target_fps
        self._frame_interval = 1.0 / target_fps
        self._last_frame_time = 0.0
        self._processed_frames = 0
        self._start_time = time.time()

    async def process(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """控制帧率

        Args:
            frame: OpenCV格式的视频帧

        Returns:
            在目标帧率范围内返回视频帧，否则返回None
        """
        current_time = time.time()

        # 计算是否需要处理这一帧
        if (current_time - self._last_frame_time) >= self._frame_interval:
            self._last_frame_time = current_time
            self._processed_frames += 1

            # 每处理100帧记录一次性能指标
            if self._processed_frames % 100 == 0:
                elapsed = current_time - self._start_time
                actual_fps = self._processed_frames / elapsed
                logger.info(f"帧率控制指标 - 目标FPS: {self.target_fps:.2f}, "
                            f"实际FPS: {actual_fps:.2f}")

            return frame

        return None  # 丢弃超出目标帧率的帧
