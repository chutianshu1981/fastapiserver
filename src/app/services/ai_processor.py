"""
AI 处理模块，使用 Roboflow InferencePipeline 处理视频帧数据

该模块实现了两种集成方式:
1. 直接通过RTSP URL连接 - 不再推荐，因为RTSP服务器配置为推流模式
2. 通过GStreamer appsink和VideoFrameProducer接口处理推送到服务器的帧 - 推荐方式
"""
from app.core.config import get_settings
from inference.core.interfaces.stream.sinks import render_boxes
from inference.core.interfaces.stream.inference_pipeline import InferencePipeline
from app.services.gstreamer_frame_producer import GStreamerFrameProducer
from app.utils.fps_counter import FPSCounter
from app.utils.gstreamer_utils import create_and_setup_gstreamer_frame_producer
from gi.repository import Gst  # type: ignore
import os
import json
import asyncio
import time
from typing import Any, Callable, Coroutine, Dict, Optional, List, Tuple, cast
from loguru import logger
from inference.core.interfaces.camera.entities import VideoFrameProducer, VideoFrame
import queue
import numpy as np
import copy
from datetime import datetime
from inference import InferencePipeline # type: ignore
from inference.core.interfaces.stream.watchdog import BaseStreamWatchdog # type: ignore
from inference.core.interfaces.stream.sinks import VideoFrame # For type hinting if needed
import concurrent.futures # 为了 concurrent.futures.Future 类型提示

# Initialize settings
settings = get_settings()

# Create FPS counter instance
fps_counter = FPSCounter()


class AIProcessor:
    """
    封装 Roboflow InferencePipeline，用于处理视频帧并进行 AI 分析。
    支持两种模式：
    1. 直接连接RTSP流（不推荐，因为服务器配置为推流模式）
    2. 通过GStreamerFrameProducer处理来自appsink的帧（推荐）
    """

    def __init__(
        self,
        model_id: str,
        rtsp_url: Optional[str] = None,
        on_prediction_callback: Optional[Callable[[
            Dict[str, Any], Dict[str, Any]], Coroutine[Any, Any, None]]] = None,
        api_key: Optional[str] = None,
        frame_producer: Optional[Any] = None,
    ):
        """
        初始化 AIProcessor。

        Args:
            model_id: Roboflow 模型 ID
            rtsp_url: RTSP 视频流地址（使用模式1时必需）
            on_prediction_callback: 异步回调函数，用于处理每帧的推理结果
            api_key: Roboflow API 密钥
            frame_producer: GStreamerFrameProducer实例（使用模式2时必需）
        """
        self.settings = get_settings()
        self.model_id = model_id
        self.rtsp_url = rtsp_url
        self.api_key = api_key or self.settings.ROBOFLOW_API_KEY
        self.on_prediction_callback = on_prediction_callback
        self.inference_pipeline: Optional[InferencePipeline] = None
        self.is_running = False
        self.frame_producer = frame_producer
        self.main_event_loop: Optional[asyncio.AbstractEventLoop] = None
        self.frame_counter = 0
        self.last_prediction_time = time.time()

        if not self.api_key:
            logger.error("Roboflow API key is not set.")
            raise ValueError("Roboflow API key is required.")

        if not self.model_id:
            logger.error("Roboflow Model ID is not set.")
            raise ValueError("Roboflow Model ID is required.")

        logger.info(
            f"AIProcessor initialized. Model ID: {self.model_id}. Using {'RTSP URL' if self.rtsp_url else 'Frame Producer' if self.frame_producer else 'Unknown Source'}.")

        # 初始化 Roboflow
        try:
            # 根据提供的参数选择初始化模式
            if self.frame_producer:
                # 模式2：使用GStreamerFrameProducer
                logger.info(
                    f"Initializing Roboflow pipeline with GStreamerFrameProducer")
                self.inference_pipeline = InferencePipeline.init(
                    model_id=self.model_id,
                    video_reference=lambda: self.frame_producer,  # 必须是lambda
                    api_key=self.api_key,
                    confidence=settings.ROBOFLOW_CONFIDENCE_THRESHOLD,
                    on_prediction=self._on_prediction
                )
            elif self.rtsp_url:
                # 模式1：直接使用RTSP URL
                logger.info(
                    f"Initializing Roboflow pipeline with RTSP URL: {self.rtsp_url}")
                self.inference_pipeline = InferencePipeline.init(
                    model_id=self.model_id,
                    video_reference=self.rtsp_url,
                    api_key=self.api_key,
                    confidence=settings.ROBOFLOW_CONFIDENCE_THRESHOLD,
                    on_prediction=self._on_prediction
                )
            else:
                raise ValueError(
                    "Either rtsp_url or frame_producer must be provided")

            logger.info(
                f"Successfully initialized Roboflow pipeline for model: {self.model_id}")
        except Exception as e:
            logger.error(
                f"Failed to initialize Roboflow pipeline: {e}", exc_info=True)
            raise

    def _predictions_to_dict(self, predictions_input: Any) -> Dict[str, Any]:
        """
        Converts raw prediction output (if necessary) to a dictionary.
        This method is being added to diagnose/resolve an AttributeError
        from the inference library's sinks.py.
        """
        logger.info(f"AIProcessor._predictions_to_dict CALLED. Input type: {type(predictions_input)}")
        
        if isinstance(predictions_input, dict):
            logger.info("AIProcessor._predictions_to_dict: Input is already a dict.")
            return copy.deepcopy(predictions_input) 
        elif hasattr(predictions_input, 'json') and callable(predictions_input.json):
            try:
                logger.info("AIProcessor._predictions_to_dict: Input has .json() method. Calling it.")
                return copy.deepcopy(predictions_input.json())
            except Exception as e:
                logger.error(f"AIProcessor._predictions_to_dict: Error calling .json() on input: {e}")
                return {"error": "Failed to call .json()", "raw_input_type": str(type(predictions_input))}
        elif isinstance(predictions_input, list):
             logger.info("AIProcessor._predictions_to_dict: Input is a list. Assuming list of serializable items or predictions.")
             # Ensure items in list are serializable, or convert them
             processed_list = []
             for item in predictions_input:
                 if isinstance(item, dict):
                     processed_list.append(copy.deepcopy(item))
                 elif hasattr(item, 'dict') and callable(item.dict): # For pydantic-like models
                     processed_list.append(item.dict())
                 elif hasattr(item, 'json') and callable(item.json): # For objects with json method
                     try:
                         processed_list.append(item.json())
                     except:
                         processed_list.append(str(item)) # Fallback
                 else:
                     processed_list.append(str(item)) # Fallback for other types
             return {"predictions": processed_list}
        
        logger.warning(f"AIProcessor._predictions_to_dict: Don't know how to convert type {type(predictions_input)} to dict. Returning as is under 'raw_predictions'.")
        return {"raw_predictions": predictions_input, "conversion_warning": "Unknown type"}

    def _on_prediction(self, predictions: Any, image_np: np.ndarray) -> None:
        """
        当推理管线产生新的预测结果时调用。
        这个方法在 Roboflow pipeline 的内部线程中执行。
        注意: `image_np` 参数是帧的 numpy 数组，而不是 VideoFrame 对象。
        """
        current_time_iso = datetime.now().isoformat()

        # 从 frame_producer 获取帧ID和时间戳
        frame_id_val = "Unknown_FID"
        frame_timestamp_obj: Optional[datetime] = None
        frame_timestamp_iso_val = "Unknown_TS"

        if self.frame_producer:
            if hasattr(self.frame_producer, 'get_frame_id') and callable(self.frame_producer.get_frame_id):
                frame_id_val = self.frame_producer.get_frame_id() or "Producer_No_FID"
            else:
                logger.warning("AIProcessor._on_prediction: frame_producer does not have get_frame_id method.")
            
            if hasattr(self.frame_producer, 'get_frame_timestamp') and callable(self.frame_producer.get_frame_timestamp):
                frame_timestamp_obj = self.frame_producer.get_frame_timestamp()
                if frame_timestamp_obj:
                    frame_timestamp_iso_val = frame_timestamp_obj.isoformat()
                else:
                    frame_timestamp_iso_val = "Producer_No_TS_Obj"
            else:
                logger.warning("AIProcessor._on_prediction: frame_producer does not have get_frame_timestamp method.")

        logger.info(
            f"AIProcessor._on_prediction: Received predictions. Type: {type(predictions)}. Frame ID: {frame_id_val}, Timestamp: {frame_timestamp_iso_val}. "
            f"Predictions data (sample): {'Non-empty dict' if predictions and isinstance(predictions, dict) else str(predictions)[:200]}..."
        )

        if self.on_prediction_callback and self.main_event_loop:
            logger.info(f"AIProcessor._on_prediction: Scheduling callback for Frame ID {frame_id_val} on loop {self.main_event_loop}")

            async def guarded_callback_executor():
                # Force a print to see if this coroutine is entered AT ALL
                print(f"DEBUG: GUARDED_CALLBACK_EXECUTOR ENTERED for Frame ID {frame_id_val}")
                logger.info(f"Guarded executor: ENTERED for Frame ID {frame_id_val}. Callback: {self.on_prediction_callback}")
                try:
                    frame_info_for_callback = {
                        "frame_id": frame_id_val,
                        "timestamp": frame_timestamp_obj, # datetime object or None
                        "image_shape": image_np.shape if image_np is not None else None,
                        "raw_image_np_type": str(type(image_np)) # for debugging
                    }
                    
                    logger.info(f"Guarded executor: About to await on_prediction_callback for Frame ID {frame_id_val} with predictions type {type(predictions)} and frame_info type {type(frame_info_for_callback)}")
                    await self.on_prediction_callback(predictions, frame_info_for_callback)
                    logger.info(f"Guarded executor: Successfully awaited on_prediction_callback for Frame ID {frame_id_val}.")
                except Exception as e_callback:
                    logger.error(f"Guarded executor: Error during on_prediction_callback execution for Frame ID {frame_id_val}: {e_callback}", exc_info=True)
                finally:
                    logger.info(f"Guarded executor: EXITED for Frame ID {frame_id_val}")

            if not self.main_event_loop.is_closed():
                future: concurrent.futures.Future = asyncio.run_coroutine_threadsafe(guarded_callback_executor(), self.main_event_loop)
                logger.info(f"AIProcessor._on_prediction: Callback for Frame ID {frame_id_val} scheduled via run_coroutine_threadsafe.")

                def future_done_callback(f: concurrent.futures.Future):
                    try:
                        f.result()  # This will raise an exception if the coroutine raised one
                        logger.info(f"AIProcessor._on_prediction (future_done_callback): Guarded executor for Frame ID {frame_id_val} completed without error (result awaited).")
                    except asyncio.CancelledError:
                        logger.warning(f"AIProcessor._on_prediction (future_done_callback): Guarded executor for Frame ID {frame_id_val} was cancelled.")
                    except Exception as e_future:
                        logger.error(f"AIProcessor._on_prediction (future_done_callback): Guarded executor for Frame ID {frame_id_val} raised an exception: {e_future}", exc_info=True)
                
                future.add_done_callback(future_done_callback)
                logger.info(f"AIProcessor._on_prediction: Done callback added to future for Frame ID {frame_id_val}.")
            else:
                logger.error(f"AIProcessor._on_prediction: Main event loop is closed. Cannot schedule callback for Frame ID {frame_id_val}.")
        
        elif not self.on_prediction_callback:
            logger.warning("AIProcessor._on_prediction: on_prediction_callback is None. Cannot schedule callback.")
        elif not self.main_event_loop:
            logger.warning("AIProcessor._on_prediction: main_event_loop is None. Cannot schedule callback.")

    async def start(self):
        """启动AI处理器，初始化并开始推理管线"""
        print("AIProcessor.start(): Entered method.") # DEBUG PRINT
        logger.info("AIProcessor.start(): Entered method.")

        if self.is_running:
            print("AIProcessor.start(): Already running, returning.") # DEBUG PRINT
            logger.warning("AIProcessor 已在运行")
            return

        # Capture the current (main) event loop
        try:
            self.main_event_loop = asyncio.get_running_loop()
            print(f"AIProcessor.start(): Captured main event loop: {self.main_event_loop}") # DEBUG PRINT
            logger.info(f"AIProcessor.start(): 已捕获主事件循环: {self.main_event_loop}")
        except RuntimeError as e:
            print(f"AIProcessor.start(): Error getting running loop: {e}") # DEBUG PRINT
            logger.error(f"AIProcessor.start(): 无法在非异步上下文中获取正在运行的事件循环。确保 start() 是被 await 的。错误: {e}", exc_info=True)
            return # Exit if loop cannot be obtained


        print(f"AIProcessor.start(): Starting with model: {self.model_id}") # DEBUG PRINT
        logger.info(f"AIProcessor 开始使用模型: {self.model_id}")
        self.is_running = True

        if not self.inference_pipeline:
            print("AIProcessor.start(): Roboflow pipeline not initialized, returning.") # DEBUG PRINT
            logger.error("Roboflow pipeline not initialized")
            self.is_running = False # Reset status
            return

        try:
            # 如果使用GStreamerFrameProducer，确保它已启动
            if self.frame_producer:
                print("AIProcessor.start(): Frame producer found. Calling self.frame_producer.start()") # DEBUG PRINT
                logger.info("AIProcessor.start(): Frame producer found. Calling self.frame_producer.start()")
                self.frame_producer.start() # This should call the start method in gstreamer_frame_producer.py
                print(f"AIProcessor.start(): self.frame_producer.start() called. Producer running state: {self.frame_producer.running}") # DEBUG PRINT
                logger.info(f"AIProcessor.start(): self.frame_producer.start() called. Producer running state: {self.frame_producer.running}")
            else:
                print("AIProcessor.start(): No frame producer found.") # DEBUG PRINT
                logger.warning("AIProcessor.start(): No frame producer found.")

            # 启动推理管道
            print("AIProcessor.start(): Calling self.inference_pipeline.start()") # DEBUG PRINT
            logger.info("AIProcessor.start(): Calling self.inference_pipeline.start()")
            self.inference_pipeline.start()
            print("AIProcessor.start(): self.inference_pipeline.start() called.") # DEBUG PRINT
            logger.info("AI processor started successfully")

            print("AIProcessor.start(): Creating task for _run_inference_loop.") # DEBUG PRINT
            asyncio.create_task(self._run_inference_loop())
            print("AIProcessor.start(): Task for _run_inference_loop created.") # DEBUG PRINT
        except Exception as e:
            print(f"AIProcessor.start(): Failed to start AI processor: {e}") # DEBUG PRINT
            logger.error(f"Failed to start AI processor: {e}", exc_info=True)
            self.is_running = False
            raise

    async def _run_inference_loop(self):
        logger.info("AIProcessor 推理主循环启动")
        # InferencePipeline 在启动后应自行处理来自 frame_producer 的帧消耗
        # 和 _on_prediction 回调的触发。
        # 如果 pipeline 配置正确，此循环可能不需要进行主动的帧处理。
        # 我们保持它运行以维持处理器的活动状态，并可能用于未来的定期检查。
        while self.is_running:
            # logger.debug("AIProcessor 推理主循环保持活动状态...") # 可以取消注释以进行调试
            await asyncio.sleep(1) # 保持任务存活并检查运行状态
        logger.info("AIProcessor 推理主循环已退出。")

    async def stop(self):
        """停止 AI 处理流程"""
        if not self.is_running:
            return

        try:
            if self.inference_pipeline:
                # 停止推理管道
                self.inference_pipeline.stop()

            # 如果使用GStreamerFrameProducer，停止它
            if self.frame_producer:
                self.frame_producer.release()

            self.inference_pipeline = None
            self.is_running = False
            logger.info("AI processor stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping AI processor: {e}", exc_info=True)
            raise

# 用于测试的回调函数


async def example_prediction_handler(predictions_data: Dict[str, Any], frame_info: Dict[str, Any]) -> None:
    """示例回调函数，用于处理预测结果。"""
    frame_id = frame_info.get('frame_id', 'N/A')
    timestamp = frame_info.get('timestamp', 'N/A')
    logger.info(
        f"[示例回调] 收到预测! Frame ID: {frame_id}, Timestamp: {timestamp}, "
        f"Predictions: {json.dumps(predictions_data, indent=2)}"
    )
    # 在这里，你可以添加将结果发送到 WebSocket 或其他地方的逻辑
    await asyncio.sleep(0.01) # 模拟异步IO操作


if __name__ == "__main__":
    import sys
    import gi
    from app.utils.gstreamer_utils import create_and_setup_gstreamer_frame_producer
    import numpy as np
    import queue

    # 确保GStreamer已初始化
    gi.require_version('Gst', '1.0')
    gi.require_version('GstApp', '1.0')
    Gst.init(None)

    async def main():
        # 设置测试GStreamer管道
        Gst.init(None)
        pipeline_str = (
            "videotestsrc is-live=true ! video/x-raw,format=BGR,width=640,height=480,framerate=30/1 ! " +
            "appsink name=test_sink emit-signals=true max-buffers=1 drop=true sync=false"
        )
        pipeline = Gst.parse_launch(pipeline_str)
        appsink = pipeline.get_by_name("test_sink")

        # 创建GStreamerFrameProducer
        frame_producer, frame_queue = create_and_setup_gstreamer_frame_producer(
            rtsp_server_appsink=appsink,
            fps=30.0,
            width=640,
            height=480
        )

        # 创建AIProcessor
        processor = AIProcessor(
            model_id=settings.ROBOFLOW_MODEL_ID,
            on_prediction_callback=example_prediction_handler,
            api_key=settings.ROBOFLOW_API_KEY,
            frame_producer=frame_producer
        )

        # 启动GStreamer管道
        pipeline.set_state(Gst.State.PLAYING)

        try:
            await processor.start()
            # 运行60秒进行测试
            await asyncio.sleep(60)
        finally:
            await processor.stop()
            # 停止GStreamer管道
            pipeline.set_state(Gst.State.NULL)

    # asyncio.run(main())  # 注释掉以防止直接运行

class GStreamerFrameProducer(VideoFrameProducer):
    def __init__(self, frame_queue: queue.Queue, fps: float, width: int, height: int, source_id: int = 0):
        self.frame_queue = frame_queue
        self.running = False
        self._fps = fps
        self._width = width
        self._height = height
        self._source_id = source_id
        self.frame_id_counter = 0
        self._last_frame = None  # 用于 retrieve
        self._last_timestamp = None

    def start(self):
        self.running = True

    def grab(self) -> bool:
        # 从队列取一帧，缓存到 self._last_frame
        if not self.running:
            return False
        try:
            self._last_frame, self._last_timestamp = self.frame_queue.get(timeout=1.0)
            return True
        except queue.Empty:
            self._last_frame = None
            self._last_timestamp = None
            return False

    def retrieve(self) -> tuple[bool, np.ndarray]:
        # 返回上一次 grab 的帧
        if self._last_frame is not None:
            return True, self._last_frame
        else:
            return False, None

    def release(self):
        self.running = False

    def isOpened(self) -> bool:
        return self.running

    def discover_source_properties(self):
        # 返回 Roboflow 需要的 SourceProperties
        from inference.core.interfaces.camera.entities import SourceProperties
        return SourceProperties(
            width=self._width,
            height=self._height,
            total_frames=0,
            is_file=False,
            fps=self._fps
        )
