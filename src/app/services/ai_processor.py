"""
AI 处理模块，使用 Roboflow InferencePipeline 处理视频帧数据
通过GStreamer appsink和VideoFrameProducer接口处理推送到服务器的帧
"""
from app.core.config import get_settings
from inference.core.interfaces.stream.sinks import render_boxes
from inference.core.interfaces.stream.inference_pipeline import InferencePipeline
from inference.core.interfaces.stream.watchdog import NullPipelineWatchdog
from app.services.gstreamer_video_source import GStreamerVideoSource
from app.services.gstreamer_frame_producer import GStreamerFrameProducer
from app.utils.fps_counter import FPSCounter
from app.utils.gstreamer_utils import create_and_setup_gstreamer_frame_producer
from gi.repository import Gst  # type: ignore
import json
import asyncio
from queue import Queue
import time
from typing import Any, Callable, Coroutine, Dict, Optional, List, Tuple, cast, Union
from loguru import logger
from inference.core.interfaces.camera.entities import VideoFrame, VideoFrameProducer
import numpy as np
from datetime import datetime
from inference.core.interfaces.stream.entities import ModelConfig
from inference.core.interfaces.camera.video_source import BufferConsumptionStrategy
from inference.models.utils import get_model
from app.utils.gstreamer_utils import create_and_setup_gstreamer_frame_producer

# Define PREDICTIONS_QUEUE_SIZE
PREDICTIONS_QUEUE_SIZE = 100  # Default size, adjust as needed

# Initialize settings
settings = get_settings()

# Create FPS counter instance
fps_counter = FPSCounter()

# 尝试导入 VideoFrame，如果 inference 库的结构是这样的话
# 在实际的 inference 库中，VideoFrame 通常在 inference.core.interfaces.stream.entities 中
try:
    from inference.core.interfaces.stream.entities import VideoFrame
except ImportError:
    logger.warning(
        "Could not import VideoFrame from inference.core.interfaces.stream.entities. "
        "Will rely on duck-typing for frame objects."
    )
    VideoFrame = None # Placeholder if import fails, duck-typing will be used


# Attempt to import Detections from supervision for SVRPrediction
try:
    from supervision import Detections as SVRPrediction
except ImportError:
    SVRPrediction = None # If supervision is not installed, SVRPrediction will be None

class AIProcessor:
    """
    封装 Roboflow InferencePipeline，用于处理视频帧并进行 AI 分析。
    支持两种模式：
    通过GStreamerFrameProducer处理来自appsink的帧
    """

    def __init__(
        self,
        model_id: str,
        on_prediction_callback: Optional[Callable[[
            Dict[str, Any], Dict[str, Any]], Coroutine[Any, Any, None]]] = None,
        api_key: Optional[str] = None,
        frame_producer: Optional[GStreamerFrameProducer] = None,
        rtsp_url: Optional[str] = None, # 保留参数，但其直接使用已被注释/修改
    ):
        logger.info(
            f"AIProcessor.__init__: Initializing with model_id: {model_id}, "
            f"on_prediction_callback: {on_prediction_callback is not None}, "
            f"frame_producer: {frame_producer is not None}, "
            f"rtsp_url (currently not directly used for pipeline if frame_producer is set): {rtsp_url is not None}"
        )
        self.model_id = model_id
        self.api_key = api_key if api_key else settings.ROBOFLOW_API_KEY

        self.on_prediction_callback = on_prediction_callback
        self.frame_producer = frame_producer
        self.video_source_id = frame_producer.get_source_id(
        ) if frame_producer and hasattr(frame_producer, 'get_source_id') else 0

        if not self.api_key:
            logger.error(
                "AIProcessor.__init__: Roboflow API key is not set. Please set ROBOFLOW_API_KEY environment variable.")
            raise ValueError("Roboflow API key is not set.")

        # Initialize model and config. Fail fast if not successful.
        try:
            logger.info(f"AIProcessor.__init__: Loading model: {model_id}")
            self.model = get_model(model_id=model_id)
            self.config = ModelConfig(
                class_agnostic_nms=False,
                confidence=0.1,
                iou_threshold=0.5,
                max_candidates=100,
                max_detections=100,
                mask_decode_mode="simple",
                tradeoff_factor=1.0
            )
            logger.info(
                f"AIProcessor.__init__: Model and config loaded successfully: {type(self.model)}")
        except Exception as e:
            logger.error(
                f"AIProcessor.__init__: CRITICAL - Failed to load model or initialize config: {e}", exc_info=True)
            raise ValueError(f"Failed to initialize AI model/config for {model_id}: {e}") from e

        self.inference_pipeline: Optional[InferencePipeline] = None
        self.is_running = False
        self.fps_counter = FPSCounter()
        self.main_event_loop = None
        logger.info("AIProcessor.__init__: Initialization complete.")

    @staticmethod
    def _predictions_to_dict(predictions_input: Any) -> Dict[str, Any]:
        """
        将不同类型的预测结果统一转换为字典列表。
        特别处理 Roboflow 的 DetectionPrediction, InstanceSegmentationPrediction 等。
        也处理直接的字典或字典列表。
        """
        if predictions_input is None:
            return {"predictions": []}

        # 如果 predictions_input 是 SVRPrediction (Roboflow Supervision)
        if SVRPrediction is not None and isinstance(predictions_input, SVRPrediction):
            # SVRPrediction 通常包含 detections,ซึ่งเป็น Supervision Detections object
            # 我们需要将其转换为更通用的格式
            # 在这个例子中，我们假设它有一个 .model_dump() 方法或类似的序列化方式
            # 或者可以访问其内部的 detections 属性
            try:
                # 尝试 model_dump()，如果存在 (Pydantic v2)
                return predictions_input.model_dump(exclude_none=True)
            except AttributeError:
                try:
                    # 尝试 dict() (Pydantic v1 or other custom objects)
                    return predictions_input.dict(exclude_none=True)
                except AttributeError:
                    # 如果是 Supervision Detections 对象
                    if hasattr(predictions_input, 'xyxy') and hasattr(predictions_input, 'confidence') and hasattr(predictions_input, 'class_id'):
                        processed_predictions = []
                        for i in range(len(predictions_input.xyxy)):
                            pred_item = {
                                'x_min': float(predictions_input.xyxy[i][0]),
                                'y_min': float(predictions_input.xyxy[i][1]),
                                'x_max': float(predictions_input.xyxy[i][2]),
                                'y_max': float(predictions_input.xyxy[i][3]),
                                'confidence': float(predictions_input.confidence[i]) if predictions_input.confidence is not None and i < len(predictions_input.confidence) else None,
                                'class_id': int(predictions_input.class_id[i]) if predictions_input.class_id is not None and i < len(predictions_input.class_id) else None,
                                'class_name': predictions_input.data.get('class_name', [])[i] if 'class_name' in predictions_input.data and isinstance(predictions_input.data.get('class_name'), list) and i < len(predictions_input.data['class_name']) else None,
                            }
                            processed_predictions.append(pred_item)
                        return {"predictions": processed_predictions, "source": "supervision"}
                    else:
                        logger.warning(f"SVRPrediction type unhandled for _predictions_to_dict. Type: {type(predictions_input)}")
                        return {"predictions": [], "raw_type": str(type(predictions_input))}


        # Roboflow SDK (inference client) 返回的 Prediction 对象 (旧版或特定模型类型)
        if hasattr(predictions_input, 'json') and callable(predictions_input.json):
            # 通常 Roboflow 的 Prediction 对象有一个 .json() 方法可以返回字典
            # 或者 .dict() 方法
            try:
                data = predictions_input.json() #  {'predictions': [...], 'image': {'width': ..., 'height': ...}}
                # 我们只需要 'predictions' 部分，如果回调的期望是这样的话
                # 或者返回整个 data，让回调处理
                if isinstance(data, dict) and "predictions" in data:
                     # 确保每个 prediction 也是字典
                    if isinstance(data["predictions"], list):
                        return {"predictions": [p if isinstance(p, dict) else (p.dict() if hasattr(p, 'dict') else vars(p)) for p in data["predictions"]]}
                    else: # 如果 data["predictions"] 不是列表，尝试转换
                        logger.warning(f"predictions_input.json()['predictions'] is not a list. Type: {type(data['predictions'])}")
                        return {"predictions": [data["predictions"].dict() if hasattr(data["predictions"], 'dict') else vars(data["predictions"])]}

                return data #  返回整个JSON结构
            except Exception as e:
                logger.error(f"Error calling .json() on prediction object: {e}", exc_info=True)
                # Fallback to vars or simple dict if .json() fails or not as expected
                if hasattr(predictions_input, 'predictions'):
                     return {"predictions": [p if isinstance(p, dict) else (p.dict() if hasattr(p, 'dict') else vars(p)) for p in predictions_input.predictions]}
                return {"predictions": [vars(p) for p in predictions_input] if isinstance(predictions_input, list) else [vars(predictions_input)]}


        # 如果已经是字典，直接返回 (假设它符合期望的结构)
        if isinstance(predictions_input, dict):
            if "predictions" not in predictions_input: # 包装一下
                return {"predictions": [predictions_input]}
            return predictions_input

        # 如果是 Prediction 对象列表 (例如，来自某些批处理或特定回调)
        if isinstance(predictions_input, list) and all(hasattr(p, 'dict') for p in predictions_input):
            return {"predictions": [p.dict() for p in predictions_input]}
        
        # 如果是普通对象列表，尝试 vars()
        if isinstance(predictions_input, list):
            try:
                return {"predictions": [vars(p) for p in predictions_input]}
            except TypeError: # vars() argument must have __dict__ attribute
                 logger.warning(f"Could not convert list of predictions using vars(). List items type: {type(predictions_input[0]) if predictions_input else 'empty list'}")
                 return {"predictions": []}


        # 最后尝试，如果它是一个单一的对象，用 vars()
        try:
            return {"predictions": [vars(predictions_input)]}
        except TypeError:
            logger.error(f"Unhandled prediction input type for _predictions_to_dict: {type(predictions_input)}")
            return {"predictions": [], "error": "Unknown prediction type"}

    def _extract_frame_details(self, video_frame_from_pipeline: Any) -> Optional[Dict[str, Any]]:
        """
        从 pipeline 返回的视频帧对象中提取图像数据、帧ID、时间戳和图像形状。
        """
        image_np: Optional[np.ndarray] = None
        frame_id: Any = "N/A"
        timestamp: Any = datetime.now() # Default timestamp
        image_shape_for_payload: Optional[Tuple[int, ...]] = None

        if hasattr(video_frame_from_pipeline, 'image') and \
           hasattr(video_frame_from_pipeline, 'frame_id') and \
           hasattr(video_frame_from_pipeline, 'frame_timestamp'):

            potential_image = getattr(video_frame_from_pipeline, 'image')
            if isinstance(potential_image, np.ndarray):
                image_np = potential_image # Assign to image_np
                frame_id = getattr(video_frame_from_pipeline, 'frame_id')
                raw_timestamp = getattr(video_frame_from_pipeline, 'frame_timestamp')

                if isinstance(raw_timestamp, datetime):
                    timestamp = raw_timestamp
                elif isinstance(raw_timestamp, (int, float)):
                    try:
                        timestamp = datetime.fromtimestamp(raw_timestamp)
                    except Exception as ts_e:
                        logger.warning(f"Could not convert numeric timestamp {raw_timestamp} to datetime: {ts_e}. Using current time.")
                        timestamp = datetime.now() # Fallback
                else:
                    timestamp = raw_timestamp if raw_timestamp else datetime.now()
                
                # Now that image_np is confirmed to be an ndarray, we can get its shape
                assert image_np is not None # Assure linter image_np is not None here
                image_shape_for_payload = image_np.shape
                logger.info(
                    f"AIProcessor._extract_frame_details (from VideoFrame-like object): "
                    f"Frame ID: {frame_id}, Timestamp: {timestamp}, Image shape: {image_shape_for_payload}"
                )
            else:
                logger.error(
                    f"AIProcessor._extract_frame_details: video_frame_from_pipeline.image is not a NumPy array. "
                    f"Actual type: {type(potential_image)}. Frame ID: {getattr(video_frame_from_pipeline, 'frame_id', 'N/A')}"
                )
                return None
        elif isinstance(video_frame_from_pipeline, np.ndarray):
            image_np = video_frame_from_pipeline # Assign to image_np
            # image_np is confirmed to be an ndarray here
            assert image_np is not None # Assure linter image_np is not None here
            image_shape_for_payload = image_np.shape
            logger.info(
                f"AIProcessor._extract_frame_details (from np.ndarray): "
                f"Image shape: {image_shape_for_payload}. Frame ID and timestamp will be defaults."
            )
        else:
            logger.error(
                f"AIProcessor._extract_frame_details: video_frame_from_pipeline (type: {type(video_frame_from_pipeline)}) "
                f"is not a valid VideoFrame object or NumPy array."
            )
            return None

        # This check might seem redundant if the logic above is flawless, but it's a good safeguard.
        if image_np is None or image_shape_for_payload is None: 
            logger.error("AIProcessor._extract_frame_details: Failed to obtain valid image numpy array or shape. Cannot process frame.")
            return None

        return {
            # "image_np": image_np, # Not returning image_np as it's not directly used by the caller (_on_prediction)
            "frame_id": frame_id,
            "timestamp": timestamp,
            "image_shape": image_shape_for_payload
        }

    def _on_prediction(self, predictions: Any, video_frame_from_pipeline: Any) -> None:
        """
        当从 InferencePipeline 接收到新的预测结果时调用的回调函数。
        注意：此函数在 InferencePipeline 的内部线程中执行。
        """
        logger.debug(f"AIProcessor._on_prediction: Received predictions type: {type(predictions)}, frame data type: {type(video_frame_from_pipeline)}")
        try:
            frame_details = self._extract_frame_details(video_frame_from_pipeline)

            if not frame_details:
                logger.error("AIProcessor._on_prediction: Failed to extract frame details. Predictions cannot be processed for this frame.")
                return

            predictions_dict = AIProcessor._predictions_to_dict(predictions) # Call as static method

            try:
                logger.info(f"AIProcessor._on_prediction: Predictions content: {json.dumps(predictions_dict, indent=2, default=str)}")
            except Exception as e_json_dump:
                logger.error(f"AIProcessor._on_prediction: Failed to dump predictions_dict to JSON for logging: {e_json_dump}. Raw dict: {predictions_dict}")

            if self.main_event_loop and self.on_prediction_callback:
                frame_info_for_callback = {
                    "frame_id": frame_details["frame_id"],
                    "timestamp": frame_details["timestamp"], # Already a datetime object or suitable raw value
                    "image_shape": frame_details["image_shape"]
                }
                logger.debug(f"AIProcessor._on_prediction: Preparing to schedule on_prediction_callback for frame ID {frame_details['frame_id']}. Loop running: {self.main_event_loop.is_running()}")

                future = asyncio.run_coroutine_threadsafe(
                    self.on_prediction_callback(predictions_dict, frame_info_for_callback), self.main_event_loop)
                logger.info(
                    f"AIProcessor._on_prediction: SUBMITTED/QUEUED on_prediction_callback for frame ID {frame_details['frame_id']}. Future state: {future._state if hasattr(future, '_state') else 'N/A'}")
            else:
                if not self.main_event_loop:
                    logger.warning("AIProcessor._on_prediction: Event loop not available for scheduling callback.")
                if not self.on_prediction_callback:
                    logger.warning("AIProcessor._on_prediction: on_prediction_callback not set.")

        except AttributeError as e:
            logger.error(
                f"AIProcessor._on_prediction: AttributeError: {e}. Predictions type: {type(predictions)}, "
                f"Received frame data type: {type(video_frame_from_pipeline)}", exc_info=True)
        except Exception as e:
            logger.error(
                f"AIProcessor._on_prediction: Error processing prediction: {e}", exc_info=True)

    async def start(self):
        """启动 AI 处理流程"""
        if self.is_running:
            logger.warning(
                "AIProcessor.start(): AI processor is already running.")
            return

        logger.info("AIProcessor.start(): Starting AI processor...")
        try:
            self.main_event_loop = asyncio.get_running_loop()
            logger.info(
                f"AIProcessor.start(): Captured main event loop: {self.main_event_loop}")

            video_source: Optional[GStreamerVideoSource] = None

            if self.frame_producer:
                if not isinstance(self.frame_producer, GStreamerFrameProducer):
                    logger.error(
                        "AIProcessor.start(): CRITICAL - self.frame_producer is not an instance of GStreamerFrameProducer. "
                        f"Actual type: {type(self.frame_producer)}. Cannot start inference with frame producer."
                    )
                    raise ValueError(
                        "frame_producer must be an instance of GStreamerFrameProducer if provided to AIProcessor for GStreamerVideoSource."
                    )
                logger.info(
                    "AIProcessor.start(): Using provided GStreamerFrameProducer.")

                if hasattr(self.frame_producer, 'start') and callable(self.frame_producer.start):
                    logger.info(
                        "AIProcessor.start(): Frame producer has start method. Calling self.frame_producer.start()")
                    self.frame_producer.start()
                    producer_running_state = getattr(
                        self.frame_producer, 'running', 'Attribute `running` not found')
                    logger.info(
                        f"AIProcessor.start(): self.frame_producer.start() called. Producer running state: {producer_running_state}")
                else:
                    logger.warning(
                        "AIProcessor.start(): Frame producer does not have a callable 'start' method or is not defined.")
                
                # 创建自定义 VideoSource
                logger.info("AIProcessor.start(): Creating GStreamerVideoSource.")
                video_source = GStreamerVideoSource(
                    self.frame_producer, # self.frame_producer is now confirmed to be GStreamerFrameProducer
                    buffer_consumption_strategy=BufferConsumptionStrategy.EAGER
                )
                # 初始化并启动 video_source
                video_source.start()
                logger.info("AIProcessor.start(): GStreamerVideoSource started.")

            else: # This 'else' now correctly implies that frame_producer was not provided.
                logger.error(
                    "AIProcessor.start(): CRITICAL - GStreamerFrameProducer (frame_producer) is not provided. Cannot start inference."
                )
                raise ValueError(
                    "A GStreamerFrameProducer (via frame_producer argument) must be provided to create the video source."
                )

            # 创建推理管道 - 使用视频源和模型
            logger.info("AIProcessor.start(): Creating InferencePipeline.")

            from inference.core.interfaces.stream.model_handlers.roboflow_models import default_process_frame
            from functools import partial

            # Model and config are now guaranteed to be initialized in __init__ or an error would have been raised.
            if self.model is None or self.config is None: # Should not happen if __init__ is successful
                 logger.error("AIProcessor.start(): CRITICAL - Model or config is None despite __init__ completion. This indicates an unexpected state.")
                 raise ValueError("Model or config not available for InferencePipeline.")


            # 创建处理函数
            on_video_frame = partial(
                default_process_frame,
                model=self.model,
                inference_config=self.config
            )
            '''
            self.inference_pipeline = InferencePipeline.init(
                model_id=self.model_id,
                # This can be RTSP URL or GStreamerFrameProducer
                video_reference=video_reference_for_pipeline,
                on_prediction=self._on_prediction,
                api_key=self.api_key,
                max_fps=settings.MAX_FPS_SERVER,  # Control internal pipeline FPS
                # other parameters as needed, e.g., confidence_threshold, iou_threshold
            )
            '''
            # 创建管道
            if video_source is None:
                logger.error("AIProcessor.start(): CRITICAL - video_source was not created. This indicates an issue with frame_producer setup or logic flow.")
                raise ValueError("Failed to initialize video_source for InferencePipeline. A GStreamerFrameProducer is required for this path.")

            self.inference_pipeline = InferencePipeline(
                on_video_frame=on_video_frame,
                video_sources=[video_source],
                predictions_queue=Queue(maxsize=PREDICTIONS_QUEUE_SIZE),
                watchdog=NullPipelineWatchdog(),
                status_update_handlers=[],
                on_prediction=self._on_prediction,
                max_fps=settings.MAX_FPS_SERVER
            )
            # 新增更改 end --------------------------------------------------
            logger.info("AIProcessor.start(): InferencePipeline initialized.")
            logger.info(
                f"AIProcessor.start(): Pipeline video_reference type: {type(video_source)}")

            # 启动推理管道
            logger.info(
                "AIProcessor.start(): Calling self.inference_pipeline.start()")
            if self.inference_pipeline:
                self.inference_pipeline.start(use_main_thread=False)  # 修改这里！确保在独立线程中分发
                logger.info(
                    "AIProcessor.start(): self.inference_pipeline.start(use_main_thread=False) called.")
            else:
                logger.error("AIProcessor.start(): self.inference_pipeline is None after initialization attempt, cannot start pipeline.")
                raise ValueError("InferencePipeline failed to initialize properly and is None.")

            self.is_running = True
            # Keep processor alive, was correctly kept
            asyncio.create_task(self._run_inference_loop())
            logger.info(
                "AIProcessor.start(): AI processor started successfully and _run_inference_loop task created.")

        except Exception as e:
            logger.error(
                f"AIProcessor.start(): Failed to start AI processor: {e}", exc_info=True)
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
            await asyncio.sleep(1)  # 保持任务存活并检查运行状态
        logger.info("AIProcessor 推理主循环已退出。")

    async def stop(self):
        """停止 AI 处理流程"""
        if not self.is_running:
            return

        logger.info(f"AIProcessor.stop(): Attempting to stop AI processor. Current is_running: {self.is_running}") # More verbose logging
        try:
            if self.inference_pipeline:
                logger.info("AIProcessor.stop(): Calling self.inference_pipeline.terminate()...")
                self.inference_pipeline.terminate() # Changed from stop() to terminate()
                logger.info("AIProcessor.stop(): InferencePipeline.terminate() called.")

            # 如果使用GStreamerFrameProducer，停止它
            if self.frame_producer:
                if hasattr(self.frame_producer, 'release') and callable(self.frame_producer.release):
                    logger.info("AIProcessor.stop(): Calling self.frame_producer.release()...")
                    self.frame_producer.release()
                    logger.info("AIProcessor.stop(): Frame producer released.")
                elif hasattr(self.frame_producer, 'stop') and callable(self.frame_producer.stop): # Fallback, if 'stop' is the method
                    logger.info("AIProcessor.stop(): Calling self.frame_producer.stop()...")
                    self.frame_producer.stop()
                    logger.info("AIProcessor.stop(): Frame producer stopped.")
                else:
                    logger.warning("AIProcessor.stop(): Frame producer does not have a recognized release or stop method.")

            self.inference_pipeline = None # Clear the reference
            self.is_running = False
            logger.info(f"AIProcessor.stop(): AI processor stopped successfully. is_running set to {self.is_running}")
        except Exception as e:
            logger.error(f"AIProcessor.stop(): Error stopping AI processor: {e}", exc_info=True)
            # self.is_running = False # Ensure is_running is false even on error
            raise

# 用于测试的回调函数


async def example_prediction_handler(predictions_data: Dict[str, Any], frame_info: Dict[str, Any]) -> None:
    """示例回调函数，用于处理预测结果。"""
    logger.info(
        f"[示例回调] 收到预测! Frame ID: {frame_info.get('frame_id', 'N/A')}, Timestamp: {frame_info.get('timestamp', 'N/A')}, "
        f"Predictions Data Type: {type(predictions_data)}, Predictions: {predictions_data}"
    )
    # 在这里，你可以添加将结果发送到 WebSocket 或其他地方的逻辑
    await asyncio.sleep(0.01)  # 模拟异步IO操作

