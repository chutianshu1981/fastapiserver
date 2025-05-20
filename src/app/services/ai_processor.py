"""
AI 处理模块，使用 Roboflow InferencePipeline 处理视频帧数据
通过GStreamer appsink和VideoFrameProducer接口处理推送到服务器的帧
"""
from app.core.config import get_settings
from inference.core.interfaces.stream.sinks import render_boxes
from inference.core.interfaces.stream.inference_pipeline import InferencePipeline
from app.services.gstreamer_frame_producer import GStreamerFrameProducer
from app.utils.fps_counter import FPSCounter
from app.utils.gstreamer_utils import create_and_setup_gstreamer_frame_producer
from gi.repository import Gst  # type: ignore
import json
import asyncio
import time
from typing import Any, Callable, Coroutine, Dict, Optional, List, Tuple, cast
from loguru import logger
from inference.core.interfaces.camera.entities import VideoFrameProducer, VideoFrame
import numpy as np
from datetime import datetime
from inference.core.interfaces.stream.sinks import VideoFrame # For type hinting if needed
from inference.core.entities.responses.inference import InferenceResponse, ObjectDetectionPrediction

# Initialize settings
settings = get_settings()

# Create FPS counter instance
fps_counter = FPSCounter()


class AIProcessor:
    """
    封装 Roboflow InferencePipeline，用于处理视频帧并进行 AI 分析。
    支持两种模式：
    通过GStreamerFrameProducer处理来自appsink的帧
    """

    def __init__(
        self,
        model_id: str,
        rtsp_url: Optional[str] = None,
        on_prediction_callback: Optional[Callable[[
            Dict[str, Any], Dict[str, Any]], Coroutine[Any, Any, None]]] = None,
        api_key: Optional[str] = None,
        frame_producer: Optional[Any] = None, # Should be GStreamerFrameProducer
    ):
        logger.info(f"AIProcessor.__init__: Initializing with model_id: {model_id}, rtsp_url: {rtsp_url is not None}, on_prediction_callback: {on_prediction_callback is not None}, frame_producer: {frame_producer is not None}")
        self.model_id = model_id
        self.api_key = api_key if api_key else settings.ROBOFLOW_API_KEY
        self.rtsp_url = rtsp_url
        self.on_prediction_callback = on_prediction_callback
        self.frame_producer = frame_producer # Instance of GStreamerFrameProducer
        self.video_source_id = frame_producer.get_source_id() if frame_producer and hasattr(frame_producer, 'get_source_id') else 0


        if not self.api_key:
            logger.error("AIProcessor.__init__: Roboflow API key is not set. Please set ROBOFLOW_API_KEY environment variable.")
            raise ValueError("Roboflow API key is not set.")

        self.inference_pipeline: Optional[InferencePipeline] = None
        self.is_running = False
        self.fps_counter = FPSCounter()
        # self.thread_pool_executor = concurrent.futures.ThreadPoolExecutor(max_workers=settings.THREAD_POOL_MAX_WORKERS)
        self.main_event_loop = None # Will be captured in start()
        logger.info("AIProcessor.__init__: Initialization complete.")

    def _predictions_to_dict(self, predictions_input: Any) -> Dict[str, Any]:
        """
        Converts predictions from various Roboflow types to a serializable dictionary.
        Handles InferenceResponse and potentially other formats if predictions_input is already a dict.
        """
        if isinstance(predictions_input, InferenceResponse):
            # This is a common case for object detection, classification, etc.
            # Convert the Pydantic model to a dict.
            # We need to be careful about custom objects like 'image' or 'parent_id' if they exist
            # and are not directly serializable.
            
            # Create a base dictionary
            response_dict = {
                "time": predictions_input.time,
                "is_stub": predictions_input.is_stub,
                "model_id": predictions_input.model_id,
                "model_type": predictions_input.model_type,
                "visualisation_request_id": predictions_input.visualisation_request_id,
                "latency_report": predictions_input.latency_report,
                "frame_id": getattr(predictions_input, 'frame_id', None) # If available
            }

            # Handle 'predictions' specifically based on type
            if hasattr(predictions_input, 'predictions') and predictions_input.predictions is not None:
                if isinstance(predictions_input.predictions, list): # Common for ObjectDetection, InstanceSegmentation
                    response_dict["predictions"] = [p.dict(exclude_none=True) if hasattr(p, 'dict') else p for p in predictions_input.predictions]
                elif hasattr(predictions_input.predictions, 'dict'): # For single prediction objects like ClassificationPrediction
                     response_dict["predictions"] = predictions_input.predictions.dict(exclude_none=True)
                else:
                    response_dict["predictions"] = predictions_input.predictions # Fallback

            # Handle top-level fields like 'image' if they exist and are simple
            if hasattr(predictions_input, 'image') and predictions_input.image is not None:
                if isinstance(predictions_input.image, dict): # e.g. {'width': w, 'height': h}
                    response_dict["image"] = predictions_input.image
                # elif hasattr(predictions_input.image, 'dict'):
                #     response_dict["image"] = predictions_input.image.dict()

            # Add other known serializable fields if they exist
            for key in ['confidence', 'parent_id', 'ground_truth_image_id', 'visualisation']:
                if hasattr(predictions_input, key):
                    value = getattr(predictions_input, key)
                    if value is not None:
                        response_dict[key] = value
            
            return response_dict

        elif isinstance(predictions_input, dict):
            # If it's already a dict, assume it's serializable or handle specific known structures
            # This could be from a workflow that outputs a dict.
            logger.debug(f"AIProcessor._predictions_to_dict: Input is already a dict: {type(predictions_input)}")
            return predictions_input 
        else:
            logger.warning(f"AIProcessor._predictions_to_dict: Unhandled prediction type: {type(predictions_input)}. Returning as is.")
            return {"raw_predictions": predictions_input}


    def _on_prediction(self, predictions: Any, image_np: np.ndarray) -> None:
        """
        Callback executed by InferencePipeline when new predictions are available.
        This method is called from a thread managed by InferencePipeline.
        It needs to schedule the async on_prediction_callback onto the main asyncio event loop.
        """
        # ERROR level is used here to make it highly visible during debugging that this callback is being hit.
        # Change to INFO or DEBUG in production.
        logger.error(f"!!!!!!!!!! AIProcessor._on_prediction CALLED by InferencePipeline. Predictions type: {type(predictions)}, Image shape: {image_np.shape} !!!!!!!!!!")
        
        self.fps_counter.tick()
        current_fps = self.fps_counter.get_fps()
        if current_fps is not None:
            logger.debug(f"AI Estimated FPS: {current_fps:.2f}")

        if not self.on_prediction_callback:
            logger.warning("AIProcessor._on_prediction: on_prediction_callback is None. Predictions will not be handled.")
            return

        if not self.main_event_loop:
            logger.error("AIProcessor._on_prediction: Main asyncio event loop not captured. Cannot schedule callback.")
            return

        try:
            # Convert predictions to a serializable dictionary
            predictions_dict = self._predictions_to_dict(predictions)

            frame_id_val = getattr(image_np, 'frame_id', getattr(predictions, 'frame_id', None))
            frame_timestamp_val = None
            
            if self.frame_producer:
                if hasattr(self.frame_producer, '_last_read_video_frame') and self.frame_producer._last_read_video_frame:
                    if frame_id_val is None and hasattr(self.frame_producer._last_read_video_frame, 'frame_id'):
                        frame_id_val = self.frame_producer._last_read_video_frame.frame_id
                    if hasattr(self.frame_producer._last_read_video_frame, 'frame_timestamp'):
                        frame_timestamp_val = self.frame_producer._last_read_video_frame.frame_timestamp
            
            if frame_id_val is None: 
                logger.warning("AIProcessor._on_prediction: Frame ID not found on image_np or producer. Using FPSCounter timestamp count as fallback ID.")
                frame_id_val = len(self.fps_counter.timestamps)


            frame_info_for_callback = {
                "frame_id": frame_id_val,
                "frame_timestamp": frame_timestamp_val.isoformat() if frame_timestamp_val else None,
                "image_shape": image_np.shape,
                "estimated_fps": current_fps,
                "source_id": self.video_source_id
            }
            logger.info(f"AIProcessor._on_prediction: Preparing to schedule callback for Frame ID {frame_id_val} with predictions: {type(predictions_dict)}, frame_info: {frame_info_for_callback}")

            # Schedule the asynchronous on_prediction_callback to be run on the main event loop
            # self.on_prediction_callback is expected to be an async function.
            future = asyncio.run_coroutine_threadsafe(
                self.on_prediction_callback(predictions_dict, frame_info_for_callback),
                self.main_event_loop
            )

            # Optional: Add a callback to the future to handle exceptions from the scheduled coroutine
            def _handle_future_result(f):
                try:
                    f.result() # Raise exception if one occurred in the coroutine
                    logger.info(f"AIProcessor._on_prediction: Successfully executed on_prediction_callback for Frame ID {frame_id_val}.")
                except Exception as e_callback:
                    logger.error(f"AIProcessor._on_prediction: Error during on_prediction_callback execution for Frame ID {frame_id_val}: {e_callback}", exc_info=True)
            
            future.add_done_callback(_handle_future_result)
            logger.debug(f"AIProcessor._on_prediction: on_prediction_callback scheduled for Frame ID {frame_id_val}.")

        except Exception as e:
            logger.error(f"AIProcessor._on_prediction: Error processing prediction or scheduling callback: {e}", exc_info=True)


    async def start(self):
        """启动 AI 处理流程"""
        if self.is_running:
            logger.warning("AIProcessor.start(): AI processor is already running.")
            return
        
        logger.info("AIProcessor.start(): Starting AI processor...")
        try:
            self.main_event_loop = asyncio.get_running_loop() # Capture the main event loop
            logger.info(f"AIProcessor.start(): Captured main event loop: {self.main_event_loop}")

            video_reference_for_pipeline: Any # Define type for clarity
            if self.frame_producer: # This check should satisfy the linter for subsequent accesses
                logger.info("AIProcessor.start(): Using provided GStreamerFrameProducer.")
                video_reference_for_pipeline = self.frame_producer
                
                if hasattr(self.frame_producer, 'start') and callable(self.frame_producer.start):
                     logger.info("AIProcessor.start(): Frame producer found. Calling self.frame_producer.start()")
                     self.frame_producer.start()
                     producer_running_state = getattr(self.frame_producer, 'running', 'Attribute `running` not found')
                     logger.info(f"AIProcessor.start(): self.frame_producer.start() called. Producer running state: {producer_running_state}")
                else:
                    logger.warning("AIProcessor.start(): Frame producer does not have a callable 'start' method or is not defined.")

            elif self.rtsp_url:
                logger.info(f"AIProcessor.start(): Using RTSP URL: {self.rtsp_url}")
                video_reference_for_pipeline = self.rtsp_url
            else:
                logger.error("AIProcessor.start(): CRITICAL - Neither frame_producer nor rtsp_url is provided. Cannot start inference.")
                raise ValueError("Either frame_producer or rtsp_url must be provided to AIProcessor.")

            self.inference_pipeline = InferencePipeline.init(
                model_id=self.model_id,
                video_reference=video_reference_for_pipeline, # This can be RTSP URL or GStreamerFrameProducer
                on_prediction=self._on_prediction,
                api_key=self.api_key,
                max_fps=settings.MAX_FPS_SERVER, # Control internal pipeline FPS
                # other parameters as needed, e.g., confidence_threshold, iou_threshold
            )
            logger.info("AIProcessor.start(): InferencePipeline initialized.")
            logger.info(f"AIProcessor.start(): Pipeline video_reference type: {type(video_reference_for_pipeline)}")


            # 启动推理管道
            logger.info("AIProcessor.start(): Calling self.inference_pipeline.start()")
            self.inference_pipeline.start() # This is typically non-blocking
            logger.info("AIProcessor.start(): self.inference_pipeline.start() called.")
            
            self.is_running = True
            asyncio.create_task(self._run_inference_loop()) # Keep processor alive, was correctly kept
            logger.info("AIProcessor.start(): AI processor started successfully and _run_inference_loop task created.")

        except Exception as e:
            logger.error(f"AIProcessor.start(): Failed to start AI processor: {e}", exc_info=True)
            self.is_running = False
            # if self.inference_pipeline:
            #     self.inference_pipeline.stop() # Attempt to clean up
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
