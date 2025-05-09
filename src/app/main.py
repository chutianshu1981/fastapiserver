'''
主应用程序入口模块

该模块负责初始化 GStreamer、RTSP 服务器和 FastAPI 应用程序，
并处理应用的启动和关闭事件。
'''

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import threading
import socket
from datetime import datetime
import logging
import asyncio
import signal
import os

# 导入 GStreamer (确保来自系统安装)
try:
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('GstRtspServer', '1.0')
    from gi.repository import GLib, Gst, GstRtspServer
except (ImportError, ValueError) as e:
    raise ImportError(
        f"无法加载 GStreamer 或 GstRtspServer: {e}. "
        f"请确保系统已安装必要的库和 Python 绑定。"
    )

from .api.routes import router as api_router, setup_app
from .rtsp.server import RtspServer
from .services.video_service import VideoService
from .core.config import get_settings
from .core.logger import setup_logging

# 配置日志
logger = setup_logging()

# 初始化 GStreamer
Gst.init(None)

# 导入设置
settings = get_settings()

# GLib 主循环
mainloop = GLib.MainLoop()

# 全局变量
rtsp_thread = None
periodic_task = None


# 获取服务器IP地址
def get_server_ip():
    """获取服务器IP地址，优先使用eth1网卡的IP地址"""
    try:
        # 优先获取eth1网卡的IP（WSL2的局域网IP）
        import subprocess
        result = subprocess.run(
            ['ip', 'addr', 'show', 'eth1'], capture_output=True, text=True)
        if result.returncode == 0:
            import re
            match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)/', result.stdout)
            if match:
                ip = match.group(1)
                logger.info(f"使用 eth1 网卡IP: {ip}")
                return ip

        # 如果上面的方法失败，尝试获取其他网络接口的IP
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            ip_address = s.getsockname()[0]
            logger.info(f"使用网络接口IP: {ip_address}")
            return ip_address
        finally:
            s.close()
    except Exception as e:
        logger.error(f"获取服务器IP失败: {e}, 使用默认IP: 127.0.0.1")
        return '127.0.0.1'


# 启动主循环的后台任务
def run_rtsp_server_loop():
    try:
        # 启动RTSP服务器
        logger.info("启动RTSP服务器...")
        rtsp_server.start()
        logger.info(
            f"RTSP 服务器已启动于 rtsp://0.0.0.0:{settings.RTSP_PORT}{settings.RTSP_PATH}")

        logger.info("主循环启动...")
        mainloop.run()
    except Exception as e:
        logger.error(f"运行主循环失败: {e}", exc_info=True)
    finally:
        # 确保停止RTSP服务器
        if rtsp_server and rtsp_server.is_running:
            rtsp_server.stop()
        logger.info("主循环已退出。")


# 定期执行的后台任务 (使用 asyncio)
async def periodic_tasks():
    while True:
        try:
            # TODO: 清理任务暂时移除
            logger.info("定期任务检查...")
            await asyncio.sleep(86400)  # 每天执行一次检查
        except Exception as e:
            logger.error(f"定期任务失败: {e}", exc_info=True)


# 优雅关闭处理
async def shutdown_event():
    logger.info("收到关闭信号，开始优雅关闭...")
    if mainloop.is_running():
        logger.info("正在停止主循环...")
        mainloop.quit()
    # 等待服务器线程结束 (如果需要)
    if rtsp_thread and rtsp_thread.is_alive():
        logger.info("等待服务器线程退出...")
        rtsp_thread.join(timeout=5)  # 等待最多 5 秒
        if rtsp_thread.is_alive():
            logger.warning("服务器线程未在超时内退出。")
    # 取消定期任务
    if periodic_task:
        logger.info("正在取消定期任务...")
        periodic_task.cancel()
        try:
            await periodic_task
        except asyncio.CancelledError:
            logger.info("定期任务已取消。")
    logger.info("关闭完成。")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global rtsp_thread, periodic_task
    # 启动
    logger.info("应用启动，正在初始化...")
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)

    # 在单独线程中启动主循环和RTSP服务器
    logger.info("正在启动RTSP服务器线程...")
    rtsp_thread = threading.Thread(target=run_rtsp_server_loop, daemon=True)
    rtsp_thread.start()
    logger.info("RTSP服务器线程已启动")

    # 启动定期任务
    periodic_task = asyncio.create_task(periodic_tasks())
    logger.info("应用启动完成。")

    # 向控制台输出服务器信息
    server_ip = get_server_ip()
    logger.info(
        f"RTSP服务器地址: rtsp://{server_ip}:{settings.RTSP_PORT}{settings.RTSP_PATH}")
    logger.info(f"请在Android设备上配置以上地址进行测试")

    yield  # 应用运行中

    # 关闭
    await shutdown_event()


# 创建应用实例
app = FastAPI(
    title="SafePath RTSP Receiver",
    lifespan=lifespan,
    debug=True  # 启用调试模式
)

# 在这里添加一个简单的测试路由，确保 FastAPI 正在运行


@app.get("/")
async def root():
    return {"message": "RTSP服务器正在运行", "status": "OK"}

# 添加另一个测试路由来检查RTSP服务器状态


@app.get("/rtsp-status")
async def rtsp_status():
    status = {
        "rtsp_running": rtsp_server.is_running if rtsp_server else False,
        "server_time": datetime.now().isoformat(),
        "rtsp_url": f"rtsp://{get_server_ip()}:{settings.RTSP_PORT}{settings.RTSP_PATH}"
    }
    return status

# 启用CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应配置具体来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置应用
setup_app(app)

# 实例化服务 (全局实例，注意线程安全和状态管理)
rtsp_server = RtspServer()

# 暂时不启用视频服务，只测试 RTSP 接收功能
# video_service = VideoService(
#     output_dir=settings.OUTPUT_DIR,
#     max_storage_days=settings.MAX_VIDEO_STORAGE_DAYS
# )
