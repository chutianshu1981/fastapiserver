"""
AI 处理模块，使用 Roboflow InferencePipeline 处理 RTSP 视频流
"""
from app.core.config import get_settings
from inference.core.interfaces.stream.sinks import render_boxes
from inference.core.interfaces.stream.inference_pipeline import InferencePipeline
from gi.repository import Gst, GLib, GstApp  # type: ignore
import os
import json
import asyncio
import numpy as np
from typing import Any, Callable, Coroutine, Dict, Optional, List, cast
from loguru import logger
import supervision as sv
import time
from datetime import datetime
from collections import defaultdict

# GStreamer imports
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')

# Initialize GStreamer
Gst.init(None)

settings = get_settings()

# FPS monitoring


class FPSCounter:
    def __init__(self, window_size: int = 30):
        self.window_size = window_size
        self.timestamps: List[float] = []

    def tick(self) -> None:
        current_time = time.time()
        self.timestamps.append(current_time)

        # Remove timestamps outside the window
        while self.timestamps and self.timestamps[0] < current_time - self.window_size:
            self.timestamps.pop(0)

    def get_fps(self) -> float:
        if len(self.timestamps) < 2:
            return 0.0

        time_diff = self.timestamps[-1] - self.timestamps[0]
        if time_diff == 0:
            return 0.0

        return (len(self.timestamps) - 1) / time_diff


# Create FPS counter instance
fps_counter = FPSCounter()


class AIProcessor:
    """
    封装 Roboflow InferencePipeline，用于处理视频帧并进行 AI 分析。
    """

    def __init__(
        self,
        model_id: str,
        rtsp_url: str,
        on_prediction_callback: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]],
        api_key: Optional[str] = None,
    ):
        """
        初始化 AIProcessor。

        Args:
            model_id: Roboflow 模型 ID
            rtsp_url: RTSP 视频流地址
            on_prediction_callback: 异步回调函数，用于处理每帧的推理结果
            api_key: Roboflow API 密钥
        """
        self.model_id = model_id
        self.rtsp_url = rtsp_url
        self.api_key = api_key or settings.ROBOFLOW_API_KEY
        self.on_prediction_callback = on_prediction_callback
        self.pipeline: Gst.Pipeline | None = None
        self.inference_pipeline = None
        self.is_running = False
        self.loop: asyncio.AbstractEventLoop | None = None
        self.frame_count = 0

        # 初始化 Roboflow
        try:
            # 初始化推理管道
            self.inference_pipeline = InferencePipeline.init(
                model_id=self.model_id,
                video_reference=self.rtsp_url,  # 设置视频源
                api_key=self.api_key,
                confidence=settings.ROBOFLOW_CONFIDENCE_THRESHOLD,
                on_prediction=self._on_prediction
            )
            logger.info(
                f"Successfully initialized Roboflow pipeline for model: {self.model_id}")
        except Exception as e:
            logger.error(
                f"Failed to initialize Roboflow pipeline: {e}", exc_info=True)
            raise

    def _on_prediction(self, predictions: Any, video_frame: Any) -> None:
        """
        处理 Roboflow 推理结果的回调函数

        Args:
            predictions: 模型推理结果
            video_frame: 视频帧数据
        """
        try:
            self.frame_count += 1

            # 处理检测结果
            detections = []
            if hasattr(predictions, "predictions"):
                raw_detections = predictions.predictions
            elif isinstance(predictions, list):
                raw_detections = predictions
            else:
                raw_detections = [predictions]

            # 处理每个检测结果
            for det in raw_detections:
                if not det:
                    continue

                detection_data = {
                    "class": det.get("class", "unknown"),
                    "confidence": float(det.get("confidence", 0.0)),
                    "x_center": float(det.get("x", 0.0)),
                    "y_center": float(det.get("y", 0.0)),
                    "width": float(det.get("width", 0.0)),
                    "height": float(det.get("height", 0.0))
                }
                detections.append(detection_data)

            # 更新FPS
            fps_counter.tick()
            current_fps = fps_counter.get_fps()

            # 构建输出数据
            processed_data = {
                "frame_id": self.frame_count,
                "timestamp": int(asyncio.get_event_loop().time() * 1000),
                "fps": round(current_fps, 2),
                "detections": detections
            }

            # 通过事件循环发送结果
            if self.loop:
                asyncio.run_coroutine_threadsafe(
                    self.on_prediction_callback(processed_data),
                    self.loop
                )

        except Exception as e:
            logger.error(f"Error processing predictions: {e}", exc_info=True)
            error_data = {
                "frame_id": self.frame_count,
                "error": str(e),
                "timestamp": int(asyncio.get_event_loop().time() * 1000)
            }
            if self.loop:
                asyncio.run_coroutine_threadsafe(
                    self.on_prediction_callback(error_data),
                    self.loop
                )

    async def start(self):
        """启动 AI 处理流程"""
        if self.is_running:
            logger.info("AIProcessor is already running")
            return

        if not self.inference_pipeline:
            logger.error("Roboflow pipeline not initialized")
            return

        self.loop = asyncio.get_running_loop()

        try:
            # 启动推理管道，已在初始化时设置了视频源
            self.inference_pipeline.start()
            self.is_running = True
            logger.info("AI processor started successfully")
        except Exception as e:
            logger.error(f"Failed to start AI processor: {e}", exc_info=True)
            self.is_running = False
            raise

    async def stop(self):
        """停止 AI 处理流程"""
        if not self.is_running:
            return

        try:
            if self.inference_pipeline:
                self.inference_pipeline.stop()
            self.inference_pipeline = None
            self.is_running = False
            logger.info("AI processor stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping AI processor: {e}", exc_info=True)
            raise

# 用于测试的回调函数


async def example_prediction_handler(prediction_data: Dict[str, Any]) -> None:
    """示例回调函数，用于处理来自 AIProcessor 的推理结果"""
    logger.info(
        f"Received prediction: {json.dumps(prediction_data, indent=2)}")

if __name__ == "__main__":
    async def main():
        # 测试用的RTSP流
        test_rtsp_url = "rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mov"

        processor = AIProcessor(
            model_id=settings.ROBOFLOW_MODEL_ID,
            rtsp_url=test_rtsp_url,
            on_prediction_callback=example_prediction_handler,
            api_key=settings.ROBOFLOW_API_KEY
        )

        try:
            await processor.start()
            # 运行60秒进行测试
            await asyncio.sleep(60)
        finally:
            await processor.stop()

    # asyncio.run(main())  # 注释掉以防止直接运行
