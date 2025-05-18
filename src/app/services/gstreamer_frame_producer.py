"""
GStreamer 帧生产者模块

该模块实现了GStreamerFrameProducer类，用于从GStreamer appsink读取视频帧，
并转换为Roboflow所需的VideoFrame格式。
"""
import queue
import time
from typing import Optional, Tuple
from datetime import datetime
from loguru import logger
from inference.core.interfaces.camera.entities import VideoFrame, VideoFrameProducer, SourceProperties
import numpy as np
import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
gi.require_version('GstRtspServer', '1.0')


class GStreamerFrameProducer(VideoFrameProducer):
    """
    从GStreamer的appsink获取视频帧，并实现VideoFrameProducer接口以供Roboflow使用。
    这个类充当GStreamer appsink和Roboflow InferencePipeline之间的桥梁。
    """

    def __init__(self, frame_queue: queue.Queue, fps: float, width: int, height: int, source_id: int = 0):
        """
        初始化帧生产者。

        Args:
            frame_queue: 存储从GStreamer appsink获取的帧的队列
            fps: 视频的帧率
            width: 视频帧宽度
            height: 视频帧高度
            source_id: 视频源标识符
        """
        self.frame_queue = frame_queue
        self.running = False
        self._fps = fps
        self._width = width
        self._height = height
        self._source_id = source_id
        self.frame_id_counter = 0
        self._last_read_video_frame: Optional[VideoFrame] = None
        self._last_retrieved_frame_id: Optional[int] = None
        self._last_retrieved_frame_timestamp: Optional[datetime] = None
        logger.info(f"GStreamerFrameProducer initialized. Queue: {frame_queue is not None}, FPS: {fps}, Resolution: {width}x{height}")

    def start(self):
        """开始帧生产过程"""
        self.running = True
        logger.info(
            f"GStreamerFrameProducer started with resolution {self._width}x{self._height} @ {self._fps}fps")

    def read_frame(self) -> Optional[VideoFrame]:
        """
        从内部队列读取一帧，并将其包装为 VideoFrame 对象。
        如果队列为空（超时），则返回 None。
        """
        # logger.debug(f"GStreamerFrameProducer.read_frame() called. Running: {self.running}, Queue size: {self.frame_queue.qsize() if self.frame_queue else 'N/A'}")
        if not self.running:
            # logger.warning("GStreamerFrameProducer.read_frame(): Producer not running.")
            return None

        try:
            # 从队列中获取(numpy_array, timestamp_ns)元组
            # logger.debug(f"GStreamerFrameProducer: Attempting to get frame from queue (current size: {self.frame_queue.qsize()})")
            
            # 使用 timeout 来避免无限阻塞，并允许检查 self.running 状态
            numpy_frame, timestamp_ns = self.frame_queue.get(timeout=1.0) 
            
            # logger.info(f"GStreamerFrameProducer: Frame obtained from queue. Timestamp_ns: {timestamp_ns}")

            self.frame_id_counter += 1
            current_timestamp_dt: Optional[datetime] = None

            if timestamp_ns is not None:
                try:
                    current_timestamp_dt = datetime.fromtimestamp(timestamp_ns / 1_000_000_000)
                    # logger.debug(f"GStreamerFrameProducer: Converted timestamp_ns {timestamp_ns} to datetime {current_timestamp_dt.isoformat()}")
                except Exception as e:
                    logger.error(f"GStreamerFrameProducer: Error converting timestamp_ns {timestamp_ns} to datetime: {e}. Falling back to current time.")
                    current_timestamp_dt = datetime.now() # Fallback
            else:
                logger.warning("GStreamerFrameProducer: timestamp_ns is None. Falling back to current time for VideoFrame.")
                current_timestamp_dt = datetime.now() # Fallback

            # 创建VideoFrame对象，移除无效参数
            video_frame = VideoFrame(
                image=np.copy(numpy_frame), # 确保传递图像数据的副本
                frame_id=self.frame_id_counter,
                frame_timestamp=current_timestamp_dt,
                source_id=self._source_id
                # fps=self._fps, # fps 和 resolution 由 discover_source_properties 提供
                # measured_fps=None, # 通常由 pipeline 内部或更高级别的逻辑计算
            )
            # logger.info(f"GStreamerFrameProducer.read_frame(): Created VideoFrame ID: {video_frame.frame_id} with timestamp {video_frame.frame_timestamp.isoformat() if video_frame.frame_timestamp else 'None'}")
            return video_frame

        except queue.Empty:
            # logger.debug("GStreamerFrameProducer.read_frame(): Frame queue is empty (timeout).")
            return None
        except Exception as e:
            logger.error(f"GStreamerFrameProducer.read_frame(): Exception while reading frame: {e}", exc_info=True)
            return None

    def release(self):
        logger.info("GStreamerFrameProducer.release() CALLED BY PIPELINE.")
        # 对于一个期望持续接收推流的源，我们不在此处将 self.running 置为 False。
        # InferencePipeline 可能会在 grab 失败后调用 release，但我们希望它能重试。
        # self.running = False 
        logger.info(f"GStreamerFrameProducer.release(): Kept running state as {self.running} for persistent push source.")
        
        # 清理队列中的所有剩余帧
        logger.info("GStreamerFrameProducer.release(): Clearing frame queue...")
        cleared_count = 0
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
                cleared_count += 1
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"GStreamerFrameProducer.release(): Error clearing queue item: {e}")
                break # Stop if error during clearing
        logger.info(f"GStreamerFrameProducer.release(): Frame queue cleared. {cleared_count} items removed.")

    def get_fps(self) -> Optional[float]:
        """获取视频帧率"""
        return self._fps

    def get_resolution(self) -> Optional[Tuple[int, int]]:
        """获取视频分辨率"""
        return (self._width, self._height)

    def isOpened(self) -> bool:
        logger.info(f"GStreamerFrameProducer.isOpened() called, running={self.running}")
        return self.running

    def grab(self) -> bool:
        """
        从队列中抓取并处理一帧，将其存储以供 retrieve() 方法后续检索。
        """
        if not self.running:
            logger.warning("GStreamerFrameProducer.grab(): Producer not running.")
            return False
        try:
            video_frame_obj = self.read_frame()
            if video_frame_obj is not None:
                self._last_read_video_frame = video_frame_obj
                logger.debug(f"GStreamerFrameProducer.grab(): Successfully grabbed frame ID: {video_frame_obj.frame_id}, Timestamp: {video_frame_obj.frame_timestamp}")
                return True
            else:
                self._last_read_video_frame = None
                logger.debug("GStreamerFrameProducer.grab(): read_frame() returned None, grab failed.")
                return False
        except Exception as e:
            logger.error(f"GStreamerFrameProducer.grab(): Exception while grabbing frame: {e}", exc_info=True)
            self._last_read_video_frame = None
            return False

    def retrieve(self) -> tuple[bool, Optional[np.ndarray]]:
        if hasattr(self, '_last_read_video_frame') and self._last_read_video_frame is not None:
            image_to_return = self._last_read_video_frame.image
            
            self._last_retrieved_frame_id = self._last_read_video_frame.frame_id
            self._last_retrieved_frame_timestamp = self._last_read_video_frame.frame_timestamp
            
            frame_id_log = self._last_retrieved_frame_id
            frame_timestamp_log = self._last_retrieved_frame_timestamp.isoformat() if self._last_retrieved_frame_timestamp else 'None'

            self._last_read_video_frame = None
            
            if image_to_return is not None:
                logger.info(f"GStreamerFrameProducer.retrieve(): Returning image (shape: {image_to_return.shape}) for Frame ID: {frame_id_log}, Timestamp: {frame_timestamp_log}. Metadata cached.")
                return True, image_to_return
            else:
                logger.warning(f"GStreamerFrameProducer.retrieve(): Stored VideoFrame (ID: {frame_id_log}) had None image. Metadata cached.")
                return False, None
        else:
            logger.debug("GStreamerFrameProducer.retrieve(): No frame available to retrieve (self._last_read_video_frame is None).")
            return False, None

    def get_frame_id(self) -> Optional[int]:
        """返回最后一次由 retrieve() 方法处理的帧的 ID。"""
        return self._last_retrieved_frame_id

    def get_frame_timestamp(self) -> Optional[datetime]:
        """返回最后一次由 retrieve() 方法处理的帧的时间戳。"""
        return self._last_retrieved_frame_timestamp

    def discover_source_properties(self):
        from inference.core.interfaces.camera.entities import SourceProperties
        return SourceProperties(
            width=self._width,
            height=self._height,
            total_frames=0,
            is_file=False,
            fps=self._fps
        )
    '''
    def on_prediction_callback(self, predictions):
        logger.info(f"收到 AI 预测结果: {predictions}")
    '''