"""
AI 处理模块，使用 Roboflow InferencePipeline 处理 RTSP 视频流
"""
from app.core.config import get_settings
from inference import StreamClient  # Updated import path
# Kept as is, likely correct
from inference.core.interfaces.camera.entities import VideoFrame
from inference import get_model
# Added for type checking and accessing video_frame_param.image properties
import numpy as np
import asyncio
import json
import os
from typing import Any, Callable, Coroutine, Dict, Optional, List  # Added List
from loguru import logger
# Removed 'impor' typo that was here

settings = get_settings()


class AIProcessor:
    """
    封装 Roboflow InferencePipeline，用于处理 RTSP 视频流并进行 AI 分析。
    """

    def __init__(
        self,
        model_id: str,
        rtsp_url: str,
        # Updated type hint
        on_prediction_callback: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]],
        api_key: Optional[str] = None,
    ):
        """
        初始化 AIProcessor。

        Args:
            model_id: 模型 ID。
            rtsp_url: RTSP 视频流地址。
            on_prediction_callback: 异步回调函数，用于处理每帧的推理结果。
                                     回调函数接收一个字典参数，包含处理后的推理数据。
            api_key: API 密钥。
        """
        self.model_id = model_id
        self.rtsp_url = rtsp_url
        self.api_key = api_key
        self.on_prediction_callback = on_prediction_callback
        self.stream_client: Optional[StreamClient] = None
        self.model = None  # Initialize model attribute
        self.is_running = False
        # Added loop attribute
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        logger.info(
            f"Initializing AIProcessor with model_id: {model_id}, RTSP URL: {rtsp_url}"
        )
        try:
            self.model = get_model(
                model_id=self.model_id, api_key=self.api_key)
            logger.info(f"Successfully loaded model: {self.model_id}")
        except Exception as e:
            logger.error(
                f"Failed to load model {self.model_id}: {e}", exc_info=True)
            raise  # Reraise to signal initialization failure clearly

    async def start(self):
        """
        启动 AI 处理流程。
        """
        if self.is_running:
            logger.info("AIProcessor is already running.")
            return

        if not self.model:
            logger.error("AI model not loaded. Cannot start AIProcessor.")
            return

        self.loop = asyncio.get_running_loop()  # Capture the event loop

        logger.info(
            f"Configuring StreamClient for RTSP stream: {self.rtsp_url}")

        self.stream_client = StreamClient(
            model=self.model,
            rtsp_url=self.rtsp_url,
            sinks=[self._custom_on_prediction],  # Pass the method directly
            max_fps=10,  # As configured previously
        )
        # Set is_running before starting the blocking call or background task
        self.is_running = True
        logger.info(
            "StreamClient configured. AIProcessor is now considered 'running' and ready for stream start."
        )

    async def stop(self):
        """
        停止 AI 处理流程。
        """
        if not self.is_running:
            logger.info("AIProcessor is not running.")
            return

        logger.info("Stopping AIProcessor...")
        if self.stream_client:
            try:
                self.stream_client.stop()
                logger.info("StreamClient stop signal sent.")
            except Exception as e:
                logger.error(
                    f"Error stopping StreamClient: {e}", exc_info=True)

        self.is_running = False
        self.stream_client = None  # Release the client
        logger.info("AIProcessor stopped.")

    def _custom_on_prediction(
        self, predictions: Any, video_frame: VideoFrame  # Updated signature
    ) -> None:
        """
        Custom callback function to process AI predictions for each frame.
        `predictions` is the output from model.infer().
        `video_frame` is `inference.core.interfaces.camera.entities.VideoFrame`.
        """
        frame_id_for_log = "unknown"
        try:
            if hasattr(video_frame, 'frame_id'):
                frame_id_for_log = video_frame.frame_id

            # model.infer() might return a single prediction object or a list of them.
            # We typically expect one for a single frame, or the first if it's a list.
            model_prediction_object: Any
            if isinstance(predictions, list):
                if not predictions:
                    logger.error(
                        f"Frame {frame_id_for_log}: Received empty list of predictions.")
                    # Schedule error callback if necessary
                    if self.loop:
                        asyncio.run_coroutine_threadsafe(self.on_prediction_callback({
                            "frame_id": frame_id_for_log,
                            "error": "Empty prediction list from model."
                        }), self.loop)
                    return
                model_prediction_object = predictions[0]
            else:
                model_prediction_object = predictions

            if not hasattr(model_prediction_object, "model_dump"):
                logger.error(
                    f"Frame {frame_id_for_log}: Prediction object (type: {type(model_prediction_object)}) lacks model_dump method."
                )
                error_data = {
                    "frame_id": frame_id_for_log,
                    "error": "AI prediction object cannot be serialized.",
                    "details": f"Object type: {type(model_prediction_object)}",
                }
                if self.loop:
                    asyncio.run_coroutine_threadsafe(
                        self.on_prediction_callback(error_data), self.loop)
                return

            model_output_dict = model_prediction_object.model_dump(
                by_alias=True, exclude_none=True
            )

            if not isinstance(model_output_dict, dict):
                logger.error(
                    f"Frame {frame_id_for_log}: model_dump() returned {type(model_output_dict)}, expected dict."
                )
                error_data = {
                    "frame_id": frame_id_for_log,
                    "error": "AI model output serialization error.",
                    "details": f"Expected dict from model_dump(), got {type(model_output_dict)}",
                }
                if self.loop:
                    asyncio.run_coroutine_threadsafe(
                        self.on_prediction_callback(error_data), self.loop)
                return

            # Extract image dimensions
            image_width: Any = None
            image_height: Any = None

            # Try from model output (Roboflow standard)
            img_info = model_output_dict.get("image", {})
            if isinstance(img_info, dict):
                image_width = img_info.get("width")
                image_height = img_info.get("height")

            # Fallback: Check for top-level image dimension keys in model output
            if image_width is None:
                image_width = model_output_dict.get("image_width")
            if image_height is None:
                image_height = model_output_dict.get("image_height")

            # Fallback: Use video_frame (InferenceVideoFrame) dimensions
            if (image_width is None or image_height is None) and hasattr(video_frame, 'image') and \
               isinstance(video_frame.image, np.ndarray) and video_frame.image.ndim >= 2:
                h_vf, w_vf = video_frame.image.shape[:2]
                image_width = w_vf if image_width is None else image_width
                image_height = h_vf if image_height is None else image_height

            image_width = image_width if image_width is not None else "unknown"
            image_height = image_height if image_height is not None else "unknown"

            raw_detections_list = model_output_dict.get("predictions", [])
            if not isinstance(raw_detections_list, list):
                logger.warning(
                    f"Frame {frame_id_for_log}: model_output_dict['predictions'] is {type(raw_detections_list)}, expected list. Defaulting to empty."
                )
                raw_detections_list = []

            processed_detections = []
            for det_idx, det in enumerate(raw_detections_list):
                if not isinstance(det, dict):
                    logger.warning(
                        f"Frame {frame_id_for_log}, Detection {det_idx}: Item is {type(det)}, expected dict. Skipping."
                    )
                    continue

                detection_data = {
                    "class": det.get("class_name", det.get("class", "unknown")),
                    "class_id": det.get("class_id", -1),
                    "confidence": det.get("confidence", 0.0),
                    "bbox": {
                        "x_center": det.get("x", 0.0),
                        "y_center": det.get("y", 0.0),
                        "width": det.get("width", 0.0),
                        "height": det.get("height", 0.0),
                    },
                }
                tracker_id = det.get("tracker_id")
                if tracker_id is not None:
                    detection_data["tracker_id"] = tracker_id

                processed_detections.append(detection_data)

            processed_data = {
                "frame_id": frame_id_for_log,
                "image_dimensions": {
                    "width": image_width,
                    "height": image_height,
                },
                "detections": processed_detections,
            }
            if self.loop:
                asyncio.run_coroutine_threadsafe(
                    self.on_prediction_callback(processed_data), self.loop)

        except Exception as e:
            logger.error(
                f"Frame {frame_id_for_log}: Error in _custom_on_prediction: {e}",
                exc_info=True,
            )
            error_data = {
                "frame_id": frame_id_for_log,
                "error": str(e),
                "details": "Failed to process AI prediction in _custom_on_prediction. Check server logs.",
            }
            if self.loop:
                asyncio.run_coroutine_threadsafe(
                    self.on_prediction_callback(error_data), self.loop)


async def example_prediction_handler(prediction_data: Dict[str, Any]) -> None:
    """
    示例回调函数，用于处理来自 AIProcessor 的推理结果。
    在实际应用中，这里会将数据通过 WebSocket 或其他方式发送给客户端。
    """
    logger.info(
        f"[Example Handler] Received AI prediction: {json.dumps(prediction_data, indent=2)}"
    )


if __name__ == "__main__":
    import logging  # Ensure logging is imported for __main__
    logging.basicConfig(level=logging.INFO)  # Basic config for standalone run
    main_logger = logging.getLogger(__name__)
    main_logger.setLevel(logging.INFO)

    TEST_RTSP_URL = "rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mov"

    async def main_async_runner():  # Renamed main to avoid conflict if any
        main_logger.info("Starting AI Processor standalone example...")

        if not settings.ROBOFLOW_API_KEY:
            main_logger.error(
                "ROBOFLOW_API_KEY not found. Please set it in .env or environment."
            )
            return

        processor = AIProcessor(
            model_id=settings.ROBOFLOW_MODEL_ID,
            rtsp_url=TEST_RTSP_URL,
            on_prediction_callback=example_prediction_handler,
            api_key=settings.ROBOFLOW_API_KEY,
        )
        start_task = None  # Initialize start_task
        try:
            start_task = asyncio.create_task(processor.start())
            main_logger.info(
                f"AIProcessor start task created. Running for 60 seconds for testing..."
            )
            await asyncio.sleep(60)

        except KeyboardInterrupt:
            main_logger.info(
                "Keyboard interrupt received, stopping AI Processor...")
        except Exception as e:
            main_logger.error(
                f"An error occurred during standalone test: {e}", exc_info=True
            )
        finally:
            main_logger.info("Stopping AI Processor in standalone example...")
            await processor.stop()
            if start_task and not start_task.done():  # Check if start_task was assigned
                start_task.cancel()
            main_logger.info("AI Processor standalone example finished.")

    # asyncio.run(main_async_runner()) # Keep commented unless for direct testing
    pass
