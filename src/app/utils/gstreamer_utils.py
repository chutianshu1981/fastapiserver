"""
GStreamer 工具函数模块

该模块提供处理GStreamer视频流的各种实用函数，包括：
1. 创建帧队列
2. 处理appsink回调
3. 设置FrameProducer
"""
import queue
import numpy as np
from typing import Tuple
from loguru import logger
from gi.repository import Gst, GLib, GstApp  # type: ignore
from app.services.gstreamer_frame_producer import GStreamerFrameProducer


def create_frame_queue() -> queue.Queue:
    """
    创建用于存储视频帧的队列

    Returns:
        Queue对象，用于存储视频帧
    """
    return queue.Queue(maxsize=60)  # 限制队列大小，防止内存溢出


def on_new_sample_callback(sink: Gst.Element, frame_queue: queue.Queue) -> Gst.FlowReturn:
    """
    GStreamer appsink的回调函数，用于处理新的视频帧样本

    Args:
        sink: GStreamer appsink元素
        frame_queue: 存储帧数据的队列

    Returns:
        Gst.FlowReturn: GStreamer流控制返回值
    """
    try:
        # 从appsink获取样本
        sample = sink.emit("pull-sample")
        if not sample:
            logger.warning("Failed to get sample from appsink")
            return Gst.FlowReturn.ERROR

        # 获取buffer
        buffer = sample.get_buffer()
        if not buffer:
            logger.warning("Sample contains no buffer")
            return Gst.FlowReturn.ERROR

        # 获取caps(包含视频宽度、高度等元数据)
        caps = sample.get_caps()
        if not caps:
            logger.warning("Sample has no caps")
            return Gst.FlowReturn.ERROR

        # 获取结构体(包含具体的视频信息)
        structure = caps.get_structure(0)
        if not structure:
            logger.warning("Caps has no structure")
            return Gst.FlowReturn.ERROR

        # 获取视频宽度和高度
        width = structure.get_value("width")
        height = structure.get_value("height")

        # 获取缓冲区时间戳
        pts_time = buffer.pts / Gst.SECOND if buffer.pts != Gst.CLOCK_TIME_NONE else None

        # 映射buffer以获取数据
        success, map_info = buffer.map(Gst.MapFlags.READ)
        if not success:
            logger.warning("Failed to map buffer")
            return Gst.FlowReturn.ERROR

        try:
            # 构建numpy数组
            frame_data = np.ndarray(
                (height, width, 3),  # BGR格式，(高度, 宽度, 通道数)
                buffer=map_info.data,
                dtype=np.uint8
            )

            # 复制数据(因为buffer.unmap()后数据将不可用)
            frame_copy = frame_data.copy()

            # 将帧放入队列(带时间戳)
            if not frame_queue.full():
                frame_queue.put((frame_copy, pts_time), block=False)
            else:
                # 队列已满，丢弃最老的帧并添加新帧
                try:
                    _ = frame_queue.get_nowait()
                    frame_queue.put((frame_copy, pts_time), block=False)
                except queue.Empty:
                    pass  # 不应该发生，但为安全起见

        finally:
            # 释放buffer映射
            buffer.unmap(map_info)

        return Gst.FlowReturn.OK

    except Exception as e:
        logger.error(
            f"Error processing frame in appsink callback: {e}", exc_info=True)
        return Gst.FlowReturn.ERROR


def create_and_setup_gstreamer_frame_producer(
    rtsp_server_appsink: Gst.Element,
    fps: float = 5.0,
    width: int = 640,
    height: int = 480
) -> Tuple[GStreamerFrameProducer, queue.Queue]:
    """
    创建并设置GStreamerFrameProducer

    Args:
        rtsp_server_appsink: GStreamer appsink元素
        fps: 视频帧率
        width: 视频宽度
        height: 视频高度

    Returns:
        元组，包含(GStreamerFrameProducer实例, 帧队列)
    """
    # 创建帧队列
    frame_queue = create_frame_queue()

    # 创建VideoFrameProducer
    frame_producer = GStreamerFrameProducer(
        frame_queue=frame_queue,
        fps=fps,
        width=width,
        height=height
    )

    # 设置appsink回调
    if rtsp_server_appsink:
        # 确保appsink已正确配置
        rtsp_server_appsink.set_property("emit-signals", True)
        rtsp_server_appsink.set_property("max-buffers", 1)
        rtsp_server_appsink.set_property("drop", True)
        rtsp_server_appsink.set_property("sync", False)

        # 连接回调函数
        rtsp_server_appsink.connect(
            "new-sample", lambda sink: on_new_sample_callback(sink, frame_queue))
        logger.info("Connected appsink callback to GStreamerFrameProducer")
    else:
        logger.warning("rtsp_server_appsink is None, cannot setup callback")

    return frame_producer, frame_queue
