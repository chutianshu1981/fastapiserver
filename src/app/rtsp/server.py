"""
RTSP 服务器模块

该模块实现基于 GStreamer 的 RTSP 服务器，支持：
   - H.264 视频流处理
   - RTSP 推流接收 (用于AI分析)
   - 多客户端并发连接
   """

from ..core.logger import get_logger
from ..core.config import get_settings
from gi.repository import Gst, GstRtspServer, GstRtsp, GLib  # type: ignore
import os
import gi
import time
import threading
import queue
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable, cast
import numpy as np

# 设置GStreamer版本
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
gi.require_version('GstRtsp', '1.0')

# 获取日志记录器
logger = get_logger(__name__)


class RtspServer:
    """RTSP 服务器类

    实现基于 GStreamer 的 RTSP 服务器，支持：
    - 推流端点 (/push)：接收 RTSP 推流并处理帧数据用于AI分析
    - 多客户端并发连接
    """

    def __init__(self):
        """初始化 RTSP 服务器"""
        self.settings = get_settings()
        self._init_gstreamer()

        # 服务器状态
        self._running = False
        self._clients: Dict[str, GstRtspServer.RTSPClient] = {}
        self._lock = threading.Lock()  # General lock for client list

        # GStreamer 组件
        self.server: Optional[GstRtspServer.RTSPServer] = None
        self.push_factory: Optional[GstRtspServer.RTSPMediaFactory] = None
        self.mainloop: Optional[GLib.MainLoop] = None
        # For /push endpoint processing
        self.push_appsink: Optional[Gst.Element] = None

        # 帧队列 - 用于存储从appsink获取的帧，供AI处理使用
        self.frame_queue: Optional[queue.Queue] = None

        # Roboflow model (placeholder - initialize appropriately)
        # self.roboflow_model = None
        # Example:
        # from roboflow import Roboflow
        # rf = Roboflow(api_key="YOUR_ROBOFLOW_API_KEY")
        # project = rf.workspace().project("YOUR_PROJECT_ID")
        # self.roboflow_model = project.version(YOUR_VERSION_NUMBER).model

        logger.info("RTSP 服务器初始化完成")

    def _init_gstreamer(self) -> None:
        """初始化 GStreamer"""
        Gst.init(None)

    def _create_push_pipeline(self) -> str:
        """创建推流端点的 GStreamer pipeline，输出解码后的 BGR 帧

        Returns:
            str: Pipeline 描述字符串
        """
        logger.info(
            "创建 /push 推流端点管道 (rtph264depay ! h264parse config-interval=-1 ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR ! appsink)")
        # 此管道将解码H264并输出BGR原始视频帧到 appsink
        pipeline = (
            "rtph264depay name=depay0 ! "
            "h264parse name=parse0 config-interval=-1 ! "  # 添加 config-interval=-1
            "avdec_h264 ! "  # 解码 H264
            "videoconvert ! "  # 转换颜色空间
            "video/x-raw,format=BGR ! "  # 指定输出BGR格式
            "appsink name=push_appsink emit-signals=true drop=true max-buffers=1 sync=false"  # 尽快处理最新帧
        )
        logger.debug(f"/push 推流端点处理管道: {pipeline}")
        return pipeline

    def _setup_media_factories(self) -> None:
        """配置 RTSP MediaFactory"""
        # 创建推流端点的媒体工厂
        self.push_factory = GstRtspServer.RTSPMediaFactory()
        if self.push_factory is None:
            raise RuntimeError("无法创建推流端点 RTSPMediaFactory")

        # 配置推流端点
        push_pipeline = self._create_push_pipeline()
        self.push_factory.set_launch(push_pipeline)
        self.push_factory.set_transport_mode(
            GstRtspServer.RTSPTransportMode.RECORD)
        # 对于 RECORD 模式，每个客户端获取自己的媒体实例
        self.push_factory.set_shared(False)
        self.push_factory.set_latency(0)
        self.push_factory.set_eos_shutdown(False)  # Keep push endpoint alive

        # 为推流端点添加权限
        permissions = GstRtspServer.RTSPPermissions()
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.ANNOUNCE.value_names[0], True)
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.RECORD.value_names[0], True)
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.SETUP.value_names[0], True)
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.TEARDOWN.value_names[0], True)
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.OPTIONS.value_names[0], True)
        # 保留 GET_PARAMETER 和 SET_PARAMETER 用于可能的协商
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.GET_PARAMETER.value_names[0], True)
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.SET_PARAMETER.value_names[0], True)
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.TEARDOWN.value_names[0], True)
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.OPTIONS.value_names[0], True)
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.DESCRIBE.value_names[0], True)
        self.push_factory.set_permissions(permissions)
        logger.info("为推流端点 /push 设置了更严格的权限 (移除了 PLAY)")

        self.push_factory.connect(
            'media-configure', self._on_push_media_configure)
        self.push_factory.connect(
            'media-constructed', self._on_media_constructed)

        logger.debug("已配置 RTSP MediaFactory (仅 /push 端点)")

    def _on_media_constructed(self, factory: GstRtspServer.RTSPMediaFactory,
                              media: GstRtspServer.RTSPMedia) -> None:
        """媒体构建回调 (仅 /push)"""
        logger.info(f"媒体已构建 for /push factory: {factory}")
        element = media.get_element()
        ret, state, pending = element.get_state(Gst.SECOND)
        logger.info(
            f"/push 媒体构建后状态: {state.value_nick}, 待定状态: {pending.value_nick}")

    def _on_push_media_configure(self, factory: GstRtspServer.RTSPMediaFactory,
                                 media: GstRtspServer.RTSPMedia) -> None:
        """推流端点媒体配置回调"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        logger.info(
            f"[{timestamp}] _on_push_media_configure invoked for /push. Media: {media}, Factory: {factory}")
        pipeline = media.get_element()
        if not pipeline:
            logger.error(
                f"[{timestamp}] Failed to get pipeline from media for /push.")
            return

        appsink = pipeline.get_by_name("push_appsink")
        if not appsink:
            logger.error(
                f"[{timestamp}] 'push_appsink' not found in /push pipeline.")
            return

        logger.info(
            f"[{timestamp}] Configuring /push appsink (push_appsink) properties.")
        # Properties are already set in pipeline string, but can be confirmed or overridden here if needed.
        # appsink.set_property("emit-signals", True)
        # appsink.set_property("max-buffers", 1)
        # appsink.set_property("drop", True)
        # appsink.set_property("sync", False)

        appsink.connect("new-sample", self._on_new_sample_from_push)
        self.push_appsink = appsink  # Keep a reference

        logger.info(
            f"[{timestamp}] /push appsink (push_appsink) configured and 'new-sample' signal connected: "
            f"emit-signals={appsink.get_property('emit-signals')}, "
            f"max-buffers={appsink.get_property('max-buffers')}, "
            f"drop={appsink.get_property('drop')}, "
            f"sync={appsink.get_property('sync')}"
        )

        self._configure_media(media, "Push endpoint (/push)")
        logger.info(f"[{timestamp}] Finished configuring /push media.")

    def _on_new_sample_from_push(self, appsink: Gst.Element) -> Gst.FlowReturn:
        """从 /push 管道的 appsink 接收到新样本时的回调"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        # logger.debug( # 减少此高频日志的冗余
        #     f"[{timestamp}] _on_new_sample_from_push invoked for appsink: {appsink.get_name()}")

        sample = appsink.emit("pull-sample")
        if not sample:
            # logger.warning( # 减少冗余
            #     f"[{timestamp}] push_appsink pull-sample did not return a sample. Appsink: {appsink.get_name()}. Returning FLUSHING.")
            return Gst.FlowReturn.FLUSHING  # Or OK if we want to ignore this and continue

        buffer = sample.get_buffer()
        if not buffer:
            logger.warning(
                f"[{timestamp}] push_appsink pull-sample returned a sample with no buffer. Appsink: {appsink.get_name()}. Returning ERROR.")
            return Gst.FlowReturn.ERROR

        # --- 开始 Roboflow 集成准备 ---
        caps = sample.get_caps()
        if not caps:
            logger.warning(
                f"[{timestamp}] Sample from {appsink.get_name()} has no caps. Cannot process for Roboflow.")
            return Gst.FlowReturn.OK  # Or ERROR, depending on how strictly to handle

        structure = caps.get_structure(0)
        if not structure:
            logger.warning(
                f"[{timestamp}] Caps from {appsink.get_name()} has no structure. Cannot process for Roboflow.")
            return Gst.FlowReturn.OK

        try:
            height = structure.get_value("height")
            width = structure.get_value("width")
            expected_format = structure.get_value("format")
            if expected_format != "BGR":
                logger.warning(
                    f"[{timestamp}] Expected BGR format from push_appsink, got {expected_format}. Roboflow might not work as expected.")
        except TypeError as e:  # More specific exception
            logger.error(
                f"[{timestamp}] Error getting caps structure (height, width, format) from {appsink.get_name()}: {e}. Caps: {caps.to_string()}")
            return Gst.FlowReturn.OK

        success, map_info = buffer.map(Gst.MapFlags.READ)
        if not success:
            logger.error(
                f"[{timestamp}] Failed to map buffer data from {appsink.get_name()} for Roboflow processing.")
            # buffer.unmap(map_info) # Should not be called if map failed
            return Gst.FlowReturn.ERROR

        try:
            # 创建 NumPy 数组，确保数据类型和形状正确
            # BGR 格式通常是 (height, width, 3)
            frame_data = np.ndarray(
                (height, width, 3),  # (height, width, channels)
                buffer=map_info.data,
                dtype=np.uint8
            )
            
            # --- 将帧数据和时间戳放入队列 ---
            if self.frame_queue is not None:
                try:
                    # 强制使用当前时间的纳秒级 Epoch 时间戳
                    gst_timestamp_ns = int(time.time() * 1_000_000_000)

                    # 创建一个 frame_data 的深拷贝，因为 buffer 将被 GStreamer 回收
                    frame_to_queue = np.copy(frame_data)
                    self.frame_queue.put((frame_to_queue, gst_timestamp_ns), block=False)
                    logger.debug(f"Frame (shape: {frame_to_queue.shape}, pts_ns: {gst_timestamp_ns}) put into queue. Queue size: {self.frame_queue.qsize()}")
                except queue.Full:
                    logger.warning(
                        f"[{timestamp}] Frame queue is full. Dropping frame from {appsink.get_name()}. "
                        f"Queue size: {self.frame_queue.qsize()}"
                    )
                except Exception as e:
                    logger.error(
                        f"[{timestamp}] Error putting frame to queue from {appsink.get_name()}: {e}", exc_info=True)
            else:
                logger.warning(
                    f"[{timestamp}] Frame queue is not initialized in RtspServer. Cannot put frame from {appsink.get_name()}.")
            # ------------------------------------

        finally:
            buffer.unmap(map_info)  # 确保 unmap 操作在 try/finally 中

        # logger.debug( # 可以按需开启此日志
        #     f"[{timestamp}] Converted Gst.Buffer to NumPy array for Roboflow. Shape: {frame_for_roboflow.shape}")

        return Gst.FlowReturn.OK  # 表示样本已成功处理

    def _configure_media(self, media: GstRtspServer.RTSPMedia, endpoint: str) -> None:
        """配置媒体元素

        Args:
            media: RTSP 媒体实例
            endpoint: 端点名称（用于日志）
        """
        element = media.get_element()
        bus = element.get_bus()
        if (bus):
            bus.add_signal_watch()
            bus.connect('message', self._on_bus_message)
        else:
            logger.warning(f"Could not get bus for media element {endpoint}")
        logger.info(f"媒体元素 {endpoint} 已配置总线监听。状态将由 RTSP 服务器管理。")

    def _on_client_connected(self, server: GstRtspServer.RTSPServer,
                             client: GstRtspServer.RTSPClient) -> None:
        """客户端连接回调"""
        with self._lock:
            client_id = str(id(client))
            self._clients[client_id] = client
            # 移除 mount_points 的获取和迭代，以匹配 server.py.bak3 的行为并解决 TypeError
            logger.info(f"客户端连接: {client_id}")

        client.connect('closed', self._on_client_disconnected)

    def _on_client_disconnected(self, client: GstRtspServer.RTSPClient) -> None:
        """客户端断开回调"""
        with self._lock:
            client_id = str(id(client))
            if client_id in self._clients:
                del self._clients[client_id]
                logger.info(f"客户端断开: {client_id}")

    def _on_bus_message(self, bus: Gst.Bus, message: Gst.Message) -> None:
        """处理管道总线消息"""
        t = message.type
        src_name = message.src.get_path_string() if message.src else 'Unknown Source'
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error(f"GStreamer错误 from {src_name}: {err.message}")
            logger.debug(f"调试信息: {debug}")
        elif t == Gst.MessageType.WARNING:
            warn, debug = message.parse_warning()
            logger.warning(f"GStreamer警告 from {src_name}: {warn.message}")
            logger.debug(f"调试信息: {debug}")
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src and isinstance(message.src, Gst.Element):
                old_state, new_state, pending_state = message.parse_state_changed()
                logger.info(
                    f"状态变化 on {message.src.get_name()} ({src_name}): {old_state.value_nick} -> {new_state.value_nick} (待定: {pending_state.value_nick})"
                )
        elif t == Gst.MessageType.EOS:
            logger.info(f"收到流结束信号 from {src_name}")
        # else:
        #     logger.debug(f"Bus message: {t.value_nick} from {src_name}")

    def start(self) -> None:
        """启动 RTSP 服务器"""
        if self._running:
            logger.warning("服务器已在运行")
            return

        try:
            logger.info("开始创建RTSP服务器实例...")
            self.server = cast(GstRtspServer.RTSPServer,
                               GstRtspServer.RTSPServer.new())
            if self.server is None:
                raise RuntimeError("无法创建 RTSP 服务器")

            logger.info(f"设置RTSP服务器端口: {self.settings.RTSP_PORT}")
            self.server.set_service(str(self.settings.RTSP_PORT))

            logger.info("设置媒体工厂...")
            self._setup_media_factories()  # 只设置 /push

            logger.info("获取挂载点...")
            mount_points = self.server.get_mount_points()
            if mount_points is None:
                raise RuntimeError("无法获取挂载点")

            # 仅挂载 /push 端点
            logger.info("添加 /push 端点到挂载点...")
            mount_points.add_factory(
                "/push", cast(GstRtspServer.RTSPMediaFactory, self.push_factory))

            logger.info("连接客户端连接回调...")
            self.server.connect('client-connected', self._on_client_connected)

            logger.info("将服务器附加到主上下文...")
            self.server.attach(None)
            logger.info(
                f"RTSP 服务器启动:\n"
                f"- 推流地址: rtsp://0.0.0.0:{self.settings.RTSP_PORT}/push\n"
            )

            self._running = True

            logger.info("创建GLib主循环...")
            self.mainloop = GLib.MainLoop()
            if self.mainloop is None:
                raise RuntimeError("无法创建主循环")

            logger.info("启动GLib主循环线程...")
            self._mainloop_thread = threading.Thread(
                target=self.mainloop.run, daemon=True)
            self._mainloop_thread.start()

            logger.info("等待主循环启动...")
            time.sleep(1)  # 给主循环一点时间启动

            logger.info("RTSP服务器已完全启动并运行")

        except Exception as e:
            logger.error(f"启动 RTSP 服务器失败: {str(e)}", exc_info=True)
            self.stop()  # 尝试清理
            raise

    def stop(self) -> None:
        """停止 RTSP 服务器"""
        if not self._running:
            logger.info("服务器未运行或已停止")
            return

        logger.info("开始停止 RTSP 服务器...")
        try:
            with self._lock:
                logger.info(f"当前客户端数量: {len(self._clients)}")
                for client_id in list(self._clients.keys()):
                    client = self._clients.pop(client_id, None)
                    if client:
                        logger.info(f"正在尝试关闭客户端: {client_id}")
                        # client.close() # GstRtspClient.close() can be used
                        # client.get_session().flush(True) # Might help
                    logger.info(f"清理客户端: {client_id}")

            if self.mainloop and self.mainloop.is_running():
                logger.info("请求主循环退出...")
                self.mainloop.quit()

            if hasattr(self, '_mainloop_thread') and self._mainloop_thread.is_alive():
                logger.info("等待主循环线程结束...")
                self._mainloop_thread.join(timeout=5)
                if self._mainloop_thread.is_alive():
                    logger.warning("主循环线程未能在5秒内优雅退出。")
                else:
                    logger.info("主循环线程已结束。")

            # Detach server from context to release resources
            if self.server:
                logger.info("从GLib上下文中分离RTSP服务器...")
                self.server.detach()  # Important for cleanup
                # self.server = None # Optional: help garbage collection

            self._running = False
            logger.info("RTSP 服务器已停止")

        except Exception as e:
            logger.error(f"停止 RTSP 服务器时出错: {str(e)}", exc_info=True)
            # 即使停止过程中出错，也标记为未运行
            self._running = False

    @property
    def is_running(self) -> bool:
        """获取服务器运行状态"""
        return self._running

    def get_client_count(self) -> int:
        """获取当前连接的客户端数量"""
        with self._lock:
            return len(self._clients)

    def __enter__(self) -> 'RtspServer':
        """上下文管理器入口"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口"""
        self.stop()
