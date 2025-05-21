from threading import RLock
from typing import Callable, List, Optional, Union
from datetime import datetime
from queue import Queue

from inference.core.interfaces.camera.entities import StatusUpdate, VideoFrame, SourceProperties
from inference.core.interfaces.camera.video_source import (
    VideoSource,
    BufferFillingStrategy,
    BufferConsumptionStrategy,
    send_video_source_status_update,
    UpdateSeverity,
    StreamState,
    POISON_PILL
)
from app.services.gstreamer_frame_producer import GStreamerFrameProducer
from loguru import logger


class GStreamerVideoSource(VideoSource):
    """一个专门包装 GStreamerFrameProducer 的 VideoSource 子类，
    用于在 InferencePipeline 中正确使用 GStreamer 生成的帧。
    """

    def __init__(
        self,
        gstreamer_producer: GStreamerFrameProducer,
        status_update_handlers: Optional[List[Callable[[
            StatusUpdate], None]]] = None,
        buffer_consumption_strategy: Optional[BufferConsumptionStrategy] = None
    ):
        """初始化 GStreamerVideoSource

        Args:
            gstreamer_producer: 实现了 VideoFrameProducer 接口的 GStreamer 视频源
            status_update_handlers: 状态更新处理器列表
            buffer_consumption_strategy: 缓冲区消费策略
        """
        # 使用适当的缓冲区消费策略
        if buffer_consumption_strategy is None:
            # 默认为EAGER，因为GStreamer通常用于实时流
            buffer_consumption_strategy = BufferConsumptionStrategy.EAGER

        # 初始化父类
        super().__init__(
            stream_reference="gstreamer_pipeline",
            frames_buffer=gstreamer_producer.frame_queue,  # 直接使用 GStreamerFrameProducer 的队列
            status_update_handlers=status_update_handlers or [],
            buffer_consumption_strategy=buffer_consumption_strategy,
            video_consumer=None,  # 我们将重写方法，这不会被使用
            video_source_properties={},
            source_id=gstreamer_producer.get_source_id() if hasattr(
                gstreamer_producer, 'get_source_id') else gstreamer_producer._source_id
        )

        self._gstreamer_producer = gstreamer_producer
        self._lock = RLock()  # 线程安全锁

        # 设置其他必要属性
        self._state = StreamState.NOT_STARTED
        self._ready_to_consume = False
        self._stoppable = False
        self._playback_allowed = None  # 会在 _start 中初始化

        # 保存 GStreamerFrameProducer 的属性
        self._source_properties = SourceProperties(
            width=gstreamer_producer._width,
            height=gstreamer_producer._height,
            total_frames=0,  # 流没有固定帧数
            is_file=False,  # GStreamer通常处理流
            fps=gstreamer_producer._fps,
            timestamp_created=None
        )

        logger.info(f"GStreamerVideoSource 已初始化, source_id: {self._source_id}")

    def _start(self):
        """重写 _start 方法，直接使用 GStreamerFrameProducer"""
        with self._lock:
            logger.info(f"GStreamerVideoSource._start() 被调用")

            # 初始化视频源
            self._video = self._gstreamer_producer

            # 启动帧生产者
            if not self._gstreamer_producer.running:
                self._gstreamer_producer.start()
                logger.info(
                    f"GStreamerVideoSource: 已启动 GStreamerFrameProducer")

            # 设置状态
            self._ready_to_consume = True
            self._stoppable = True

            # 无需创建消费线程，因为 GStreamerFrameProducer 已经处理了帧的获取和队列管理
            logger.info(f"GStreamerVideoSource._start(): 启动成功，已就绪可以消费帧")

    def terminate(self, wait_on_frames_consumption: bool = True, purge_frames_buffer: bool = False):
        """终止视频源"""
        with self._lock:
            logger.info(f"GStreamerVideoSource.terminate() 被调用")

            # 确保在终止前停止帧生产者 (但不需要停止，因为 GStreamerFrameProducer 被设计成长期运行)
            # 我们只需要清理队列
            if purge_frames_buffer:
                while not self._frames_buffer.empty():
                    try:
                        self._frames_buffer.get_nowait()
                        self._frames_buffer.task_done()
                    except:
                        break

            # 改变状态
            self._state = StreamState.ENDED
            self._ready_to_consume = False

            logger.info(f"GStreamerVideoSource.terminate(): 已终止")

    def read_frame(self, timeout: Optional[float] = None) -> Optional[VideoFrame]:
        """从队列读取帧

        注意：这个方法会被 InferencePipeline 内部调用
        """
        if not self._ready_to_consume:
            logger.warning("GStreamerVideoSource.read_frame(): 视频源未就绪")
            return None

        try:
            # 从队列获取帧
            video_frame = self._gstreamer_producer.read_frame()

            # 如果获取到帧，发送状态更新
            if video_frame is not None:
                send_video_source_status_update(
                    severity=UpdateSeverity.DEBUG,
                    event_type="FRAME_CONSUMED_EVENT",
                    payload={
                        "frame_timestamp": video_frame.frame_timestamp,
                        "frame_id": video_frame.frame_id,
                        "source_id": video_frame.source_id,
                    },
                    status_update_handlers=self._status_update_handlers,
                )
                logger.debug(
                    f"GStreamerVideoSource.read_frame(): 已获取帧 ID: {video_frame.frame_id}")
            return video_frame
        except Exception as e:
            logger.error(f"GStreamerVideoSource.read_frame(): 读取帧时出错: {e}")
            return None

    def frame_ready(self) -> bool:
        """检查是否有帧可用"""
        return not self._frames_buffer.empty()

    def get_state(self) -> StreamState:
        """获取当前状态"""
        return self._state

    def describe_source(self):
        """提供视频源的描述信息"""
        from inference.core.interfaces.camera.video_source import SourceMetadata

        return SourceMetadata(
            source_properties=self._source_properties,
            source_reference="gstreamer_pipeline",
            buffer_size=self._frames_buffer.maxsize,
            state=self._state,
            buffer_filling_strategy=None,  # 由 GStreamerFrameProducer 管理
            buffer_consumption_strategy=self._buffer_consumption_strategy,
            source_id=self._source_id
        )

    def _change_state(self, target_state: StreamState) -> None:
        """更改状态并发送通知"""
        payload = {
            "previous_state": self._state,
            "new_state": target_state,
            "source_id": self._source_id,
        }
        self._state = target_state
        send_video_source_status_update(
            severity=UpdateSeverity.INFO,
            event_type="SOURCE_STATE_UPDATE_EVENT",
            payload=payload,
            status_update_handlers=self._status_update_handlers,
        )
        logger.info(
            f"GStreamerVideoSource: 状态从 {payload['previous_state']} 变为 {target_state}")
