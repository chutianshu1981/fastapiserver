"""
RTSP 服务器模块

该模块实现基于 GStreamer 的 RTSP 服务器，支持：
   - H.264 视频流处理和播放
   - RTSP 推流接收
   - 多客户端并发连接
   """

from ..core.logger import get_logger
from ..core.config import get_settings
from gi.repository import Gst, GstRtspServer, GstRtsp, GLib  # type: ignore
import os
import gi
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable, cast

# 设置GStreamer版本
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
gi.require_version('GstRtsp', '1.0')

# 获取日志记录器
logger = get_logger(__name__)


class RtspServer:
    """RTSP 服务器类

    实现基于 GStreamer 的 RTSP 服务器，支持：
    - 播放端点 (/live)：提供测试视频源
    - 推流端点 (/push)：接收 RTSP 推流
    - 多客户端并发连接
    """

    def __init__(self):
        """初始化 RTSP 服务器"""
        self.settings = get_settings()
        self._init_gstreamer()

        # 服务器状态
        self._running = False
        self._clients: Dict[str, GstRtspServer.RTSPClient] = {}
        self._lock = threading.Lock()

        # GStreamer 组件
        self.server: Optional[GstRtspServer.RTSPServer] = None
        self.play_factory: Optional[GstRtspServer.RTSPMediaFactory] = None
        self.push_factory: Optional[GstRtspServer.RTSPMediaFactory] = None
        self.mainloop: Optional[GLib.MainLoop] = None

        logger.info("RTSP 服务器初始化完成")

    def _init_gstreamer(self) -> None:
        """初始化 GStreamer"""
        Gst.init(None)

    def _create_play_pipeline(self) -> str:
        """创建播放端点的 GStreamer pipeline

        Returns:
            str: Pipeline 描述字符串
        """
        logger.info("创建播放端点管道（测试视频源）")
        pipeline = (
            f"videotestsrc is-live=true ! "
            f"video/x-raw,width=640,height=480,framerate=30/1 ! "
            f"videoconvert ! x264enc tune=zerolatency ! "
            f"rtph264pay name=pay0 pt=96"
        )
        logger.debug(f"播放端点管道: {pipeline}")
        return pipeline

    # def _create_push_pipeline(self) -> str:
    #     """创建推流端点的 GStreamer pipeline

    #     Returns:
    #         str: Pipeline 描述字符串
    #     """
    #     # 使用 rtspsrc 接收 RTP 流 (User's new proposal)
    #     logger.info("创建推流端点管道 (rtspsrc ! rtph264depay ! ...)")
    #     pipeline = (
    #         "rtspsrc name=source protocols=GST_RTSP_LOWER_TRANS_UDP "
    #         "! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! autovideosink"
    #     )
    #     logger.debug(f"推流端点管道: {pipeline}")
    #     return pipeline

    def _setup_media_factories(self) -> None:
        """配置 RTSP MediaFactory"""
        # 创建播放端点的媒体工厂
        self.play_factory = GstRtspServer.RTSPMediaFactory()
        if self.play_factory is None:
            raise RuntimeError("无法创建播放端点 RTSPMediaFactory")

        # 配置播放端点
        play_pipeline = self._create_play_pipeline()
        self.play_factory.set_launch(play_pipeline)
        self.play_factory.set_shared(True)
        self.play_factory.set_latency(0)
        self.play_factory.set_eos_shutdown(True)
        self.play_factory.connect(
            'media-configure', self._on_play_media_configure)
        self.play_factory.connect(
            'media-constructed', self._on_media_constructed)

        # 创建推流端点的媒体工厂
        self.push_factory = GstRtspServer.RTSPMediaFactory()
        if self.push_factory is None:
            raise RuntimeError("无法创建推流端点 RTSPMediaFactory")

        # 配置推流端点
        # push_pipeline = self._create_push_pipeline() # Commented out as per recommendation
        # self.push_factory.set_launch(push_pipeline)  # Commented out as per recommendation
        # self.push_factory.set_media_type(GstRtspServer.RTSPMediaType.APPLICATION)  # REMOVED due to AttributeError - User wants this, but it causes error.
        self.push_factory.set_transport_mode(
            # Changed to RECORD as per user's latest feedback
            GstRtspServer.RTSPTransportMode.RECORD)
        self.push_factory.set_shared(False)
        self.push_factory.set_latency(0)
        self.push_factory.set_eos_shutdown(False)  # 修改为 False

        # 为推流端点添加权限
        permissions = GstRtspServer.RTSPPermissions()
        # 允许匿名用户执行关键的推流操作
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.ANNOUNCE.value_names[0], True)
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.RECORD.value_names[0], True)
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.SETUP.value_names[0], True)
        # PLAY 通常与 RECORD 一起使用，即使是推流，客户端也可能发送 PLAY (RECORD)
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.PLAY.value_names[0], True)
        # GET_PARAMETER 和 SET_PARAMETER 可能在会话协商中用到
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.GET_PARAMETER.value_names[0], True)
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.SET_PARAMETER.value_names[0], True)
        # TEARDOWN 是标准操作
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.TEARDOWN.value_names[0], True)
        # OPTIONS 和 DESCRIBE 通常默认允许，但明确添加无害
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.OPTIONS.value_names[0], True)
        permissions.add_permission_for_role(
            "anonymous", GstRtsp.RTSPMethod.DESCRIBE.value_names[0], True)
        self.push_factory.set_permissions(permissions)
        logger.info("为推流端点 /push 设置了自定义权限")

        self.push_factory.connect(
            'media-configure', self._on_push_media_configure)
        self.push_factory.connect(
            'media-constructed', self._on_media_constructed)

        logger.debug("已配置 RTSP MediaFactory")

    def _on_media_constructed(self, factory: GstRtspServer.RTSPMediaFactory,
                              media: GstRtspServer.RTSPMedia) -> None:
        """媒体构建回调"""
        logger.info("媒体已构建")
        element = media.get_element()

        # 获取元素状态
        ret, state, pending = element.get_state(Gst.SECOND)
        logger.info(f"媒体构建后状态: {state.value_nick}, 待定状态: {pending.value_nick}")

    def _on_play_media_configure(self, factory: GstRtspServer.RTSPMediaFactory,
                                 media: GstRtspServer.RTSPMedia) -> None:
        """播放端点媒体配置回调"""
        logger.info("开始配置播放端点媒体")
        self._configure_media(media, "播放端点")

    def _on_push_media_configure(self, factory: GstRtspServer.RTSPMediaFactory,
                                 media: GstRtspServer.RTSPMedia) -> None:
        """推流端点媒体配置回调"""
        logger.info("开始配置推流端点媒体")
        # element = media.get_element() # We might still need the element for _configure_media

        # 获取 source 元素并配置 (source is the rtspsrc element)
        # source = element.get_by_name("source")
        # if source:
        #     logger.info("配置 rtspsrc 元素 (source)")
        #     source.set_property("latency", 200)
        #     source.set_property("drop-on-latency", True)
        # else:
        #     logger.warning("在推流管道中未找到名为 'source' 的 rtspsrc 元素")

        # 调用基础配置
        self._configure_media(media, "推流端点")

    def _configure_media(self, media: GstRtspServer.RTSPMedia, endpoint: str) -> None:
        """配置媒体元素

        Args:
            media: RTSP 媒体实例
            endpoint: 端点名称（用于日志）
        """
        element = media.get_element()

        # 配置总线监听
        bus = element.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self._on_bus_message)

        # 检查初始状态
        # ret, state, pending = element.get_state(Gst.SECOND) # 保留element获取，但状态由media管理
        # logger.info(
        #     f"{endpoint}初始状态: {state.value_nick}, 待定: {pending.value_nick}")

        # 直接使用媒体对象的状态管理
        logger.info(f"尝试为 {endpoint} 设置媒体状态为 PLAYING")
        result = media.set_state(Gst.State.PLAYING, Gst.CLOCK_TIME_NONE)  # 使用 media.set_state
        if result == Gst.StateChangeReturn.FAILURE:
            logger.error(f"{endpoint}设置PLAYING状态失败")
            return

        # 不需要显式等待状态变化，RTSPMedia 会处理
        logger.info(f"{endpoint}媒体状态设置请求结果: {result.value_nick}")
        # 记录实际状态，但不阻塞
        _ret_state, current_state, _pending_state = element.get_state(
            0)  # 0 timeout for immediate check
        logger.info(
            f"{endpoint}媒体管道当前状态: {current_state.value_nick if _ret_state == Gst.StateChangeReturn.SUCCESS else '未知'}")

    def _on_client_connected(self, server: GstRtspServer.RTSPServer,
                             client: GstRtspServer.RTSPClient) -> None:
        """客户端连接回调"""
        with self._lock:
            client_id = str(id(client))
            self._clients[client_id] = client
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
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error(f"GStreamer错误: {err.message}")
            logger.debug(f"调试信息: {debug}")
        elif t == Gst.MessageType.WARNING:
            warn, debug = message.parse_warning()
            logger.warning(f"GStreamer警告: {warn.message}")
            logger.debug(f"调试信息: {debug}")
        elif t == Gst.MessageType.STATE_CHANGED:
            old, new, pending = message.parse_state_changed()
            logger.info(
                f"状态变化: {old.value_nick} -> {new.value_nick} (待定: {pending.value_nick})")
        elif t == Gst.MessageType.EOS:
            logger.info("收到流结束信号")

    def start(self) -> None:
        """启动 RTSP 服务器"""
        if self._running:
            logger.warning("服务器已在运行")
            return

        try:
            # 创建服务器实例
            self.server = cast(GstRtspServer.RTSPServer,
                               GstRtspServer.RTSPServer.new())
            if self.server is None:
                raise RuntimeError("无法创建 RTSP 服务器")

            self.server.set_service(str(self.settings.RTSP_PORT))

            # 配置媒体工厂
            self._setup_media_factories()
            mount_points = self.server.get_mount_points()
            if mount_points is None:
                raise RuntimeError("无法获取挂载点")

            # 添加播放和推流端点
            mount_points.add_factory(
                "/live",  # 播放端点
                cast(GstRtspServer.RTSPMediaFactory, self.play_factory)
            )
            mount_points.add_factory(
                "/push",  # 推流端点
                cast(GstRtspServer.RTSPMediaFactory, self.push_factory)
            )

            # 设置客户端连接回调
            self.server.connect('client-connected', self._on_client_connected)

            # 启动服务器
            self.server.attach(None)
            logger.info(
                f"RTSP 服务器启动:
"
                f"- 播放地址: rtsp://0.0.0.0:{self.settings.RTSP_PORT}/live
"
                f"- 推流地址: rtsp://0.0.0.0:{self.settings.RTSP_PORT}/push"
            )

            # 运行主循环
            self._running = True
            self.mainloop = GLib.MainLoop()
            if self.mainloop is None:
                raise RuntimeError("无法创建主循环")

            # 使用单独的线程运行主循环
            self._mainloop_thread = threading.Thread(target=self.mainloop.run)
            self._mainloop_thread.daemon = True
            self._mainloop_thread.start()

            # 等待服务器完全启动
            time.sleep(1)

        except Exception as e:
            logger.error(f"启动 RTSP 服务器失败: {str(e)}")
            self.stop()
            raise

    def stop(self) -> None:
        """停止 RTSP 服务器"""
        if not self._running:
            return

        try:
            # 断开所有客户端
            with self._lock:
                for client in self._clients.values():
                    client.finalize()
                self._clients.clear()

            # 停止主循环
            if self.mainloop:
                self.mainloop.quit()

            self._running = False
            logger.info("RTSP 服务器已停止")

        except Exception as e:
            logger.error(f"停止 RTSP 服务器时出错: {str(e)}")
            raise

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
