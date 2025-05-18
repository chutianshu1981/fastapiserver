#!/usr/bin/env python3
"""
单独启动RTSP服务器的测试脚本。
这个脚本用于验证RTSP服务器是否能够正常启动和运行，并显示详细的调试信息。
"""

import os
import sys
import time
import logging
from pathlib import Path

# 设置环境变量
os.environ['GST_DEBUG'] = '3,GstRtspServer:4,rtsp*:4,rtspsrc:4,udpsrc:4'
print(f"GST_DEBUG={os.environ['GST_DEBUG']}")

# 将项目根目录添加到Python路径
sys.path.insert(0, str(Path(__file__).parent))

# 设置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 导入GStreamer和RtspServer
try:
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('GstRtspServer', '1.0')
    from gi.repository import GLib, Gst, GstRtspServer
    from src.app.rtsp.server import RtspServer
    from src.app.core.config import get_settings

    # 初始化GStreamer
    Gst.init(None)
except ImportError as e:
    logger.error(f"导入GStreamer或RtspServer失败: {e}")
    sys.exit(1)


def main():
    try:
        settings = get_settings()
        logger.info(f"RTSP端口: {settings.RTSP_PORT}, 路径: {settings.RTSP_PATH}")

        # 创建GLib主循环
        mainloop = GLib.MainLoop()

        # 创建并启动RTSP服务器
        logger.info("创建RTSP服务器...")
        rtsp_server = RtspServer()

        logger.info("启动RTSP服务器...")
        rtsp_server.start()

        logger.info(
            f"RTSP服务器已启动于 rtsp://0.0.0.0:{settings.RTSP_PORT}{settings.RTSP_PATH}")
        logger.info("等待客户端连接...")

        # 运行主循环
        try:
            mainloop.run()
        except KeyboardInterrupt:
            logger.info("收到键盘中断，停止服务器...")
        finally:
            if rtsp_server.is_running:
                logger.info("停止RTSP服务器...")
                rtsp_server.stop()
            logger.info("RTSP服务器已停止")

    except Exception as e:
        logger.error(f"运行RTSP服务器时出错: {e}", exc_info=True)


if __name__ == "__main__":
    logger.info("开始测试RTSP服务器...")
    main()
