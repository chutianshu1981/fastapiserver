'''
主应用程序入口模块

该模块负责初始化 GStreamer、RTSP 服务器和 FastAPI 应用程序，
并处理应用的启动和关闭事件。
'''

from app.services import AIProcessor, manager as websocket_manager  # Import AIProcessor
from app.utils.gstreamer_utils import create_and_setup_gstreamer_frame_producer
from app.core.logger import setup_logging
from app.core.config import get_settings
from app.rtsp.server import RtspServer
from app.api.routes import router as api_router, setup_app
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
import json  # For logging AI predictions
from typing import Dict, Any, Optional  # For type hinting
import copy  # 确保导入 copy 模块

# 设置环境变量，避免matplotlib错误
os.environ['MPLBACKEND'] = 'Agg'  # 使用非交互式后端
# 如果环境变量中没有设置GST_DEBUG，则设置它
if 'GST_DEBUG' not in os.environ:
    os.environ['GST_DEBUG'] = 'avdec_h264:5,h264parse:5,rtph264depay:4,rtsp*:4,default:3'

# 打印当前的GStreamer调试设置
print(f"当前GStreamer调试级别: {os.environ.get('GST_DEBUG', '未设置')}")

# 导入 GStreamer (确保来自系统安装)
try:
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('GstRtspServer', '1.0')
    from gi.repository import GLib, Gst, GstRtspServer  # type: ignore
except (ImportError, ValueError) as e:
    raise ImportError(
        f"无法加载 GStreamer 或 GstRtspServer: {e}. "
        f"请确保系统已安装必要的库和 Python 绑定。"
    )


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
rtsp_server: Optional[RtspServer] = None  # Add type hint
ai_processor: Optional[AIProcessor] = None
FF: Optional[asyncio.Task] = None


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
        return '127.0.0.1'  # 使用localhost而不是0.0.0.0，因为AIProcessor需要连接到一个实际的IP


# 启动主循环的后台任务
def run_rtsp_server_loop():
    try:
        # 启动RTSP服务器
        logger.info("启动RTSP服务器...")
        if rtsp_server:
            rtsp_server.start()
            logger.info(
                f"RTSP 服务器已启动于 rtsp://0.0.0.0:{settings.RTSP_PORT}{settings.RTSP_PATH}")

            logger.info("主循环启动...")
            mainloop.run()
        else:
            logger.error("RTSP服务器实例未初始化，无法启动主循环。")
    except Exception as e:
        logger.error(f"运行主循环失败: {e}", exc_info=True)
    finally:
        # 确保停止RTSP服务器
        if (rtsp_server and rtsp_server.is_running):
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
    global ai_processor, ai_processor_task  # Ensure globals are referenced

    # 停止 GStreamer 主循环
    if mainloop.is_running():
        logger.info("正在停止主循环...")
        mainloop.quit()

    # 等待服务器线程结束 (如果需要)
    if rtsp_thread and rtsp_thread.is_alive():
        logger.info("等待服务器线程退出...")
        rtsp_thread.join(timeout=5)  # 等待最多 5 秒
        if rtsp_thread.is_alive():
            logger.warning("服务器线程未在超时内退出。")

    # 停止 AI 处理器
    if ai_processor:
        logger.info("正在停止 AIProcessor...")
        try:
            await ai_processor.stop()
            logger.info("AIProcessor 已停止。")
        except Exception as e:
            logger.error(f"停止 AIProcessor 时出错: {e}", exc_info=True)

    # 取消 AI 处理器任务
    if ai_processor_task:
        if not ai_processor_task.done():
            logger.info("正在取消 AIProcessor 任务...")
            ai_processor_task.cancel()
            try:
                await ai_processor_task
            except asyncio.CancelledError:
                logger.info("AIProcessor 任务已成功取消。")
            except Exception as e:
                logger.error(f"AIProcessor 任务在取消期间/之后引发异常: {e}", exc_info=True)
        else:
            logger.info("AIProcessor 任务已完成。")
            if ai_processor_task.exception():
                logger.error(
                    f"AIProcessor 任务以异常结束: {ai_processor_task.exception()}", exc_info=ai_processor_task.exception())

    # 取消定期任务
    if periodic_task:
        if not periodic_task.done():
            logger.info("正在取消定期任务...")
            periodic_task.cancel()
            try:
                await periodic_task
            except asyncio.CancelledError:
                logger.info("定期任务已成功取消。")
            except Exception as e:
                logger.error(f"定期任务在取消期间/之后引发异常: {e}", exc_info=True)
        else:
            logger.info("定期任务已完成。")
            if periodic_task.exception():
                logger.error(
                    f"定期任务以异常结束: {periodic_task.exception()}", exc_info=periodic_task.exception())

    logger.info("优雅关闭完成。")


# 定义 AI 预测处理函数
async def handle_ai_prediction(predictions_data: Dict[str, Any], frame_info: Dict[str, Any]):
    """
    处理 AIProcessor 预测结果的回调函数。
    将AI检测结果记录并通过WebSocket发送给所有连接的客户端。
    """
    logger.error(
        "!!!!!!!!!! handle_ai_prediction CALLED !!!!!!!!!!")  # 强制日志，确认函数调用
    try:
        frame_id = frame_info.get("frame_id", "N/A")
        timestamp = frame_info.get("timestamp", "N/A")

        # 更详细地记录接收到的数据
        logger.info(
            f"主回调 handle_ai_prediction: 收到AI预测结果 (Frame ID: {frame_id}, Timestamp: {timestamp}), "
            f"Predictions: {'[]' if not predictions_data else '有数据'}"
        )
        try:
            # 尝试将 predictions_data 和 frame_info 序列化为 JSON 字符串进行记录
            # 使用 copy.deepcopy 来避免修改原始数据，特别是如果它们是可变类型且后续仍需使用
            predictions_data_log = copy.deepcopy(predictions_data)
            frame_info_log = copy.deepcopy(frame_info)

            # 对于 datetime 对象，需要特殊处理才能 JSON 序列化
            if isinstance(frame_info_log.get("timestamp"), datetime):
                frame_info_log["timestamp"] = frame_info_log["timestamp"].isoformat()

            # 直接记录原始 frame_info
            logger.info(f"  Raw Frame Info: {frame_info_log}")
            logger.info(
                f"  Raw Predictions Data Type: {type(predictions_data_log)}")
            # 直接记录原始 predictions_data
            logger.info(f"  Raw Predictions Data: {predictions_data_log}")

            # # 下面这两行可以帮助查看详细的JSON结构，如果直接打印不清晰
            # logger.info(f"  Frame Info (JSON): {json.dumps(frame_info_log, indent=2, default=str)}")
            # logger.info(f"  Predictions Data (JSON): {json.dumps(predictions_data_log, indent=2, default=str)}")

        except Exception as log_e:
            logger.error(
                f"主回调 handle_ai_prediction: 记录predictions_data或frame_info时出错: {log_e}")

        # 构造发送给客户端的数据
        websocket_payload = {
            "frame_id": frame_id,
            "timestamp": str(timestamp),  # 确保时间戳是可序列化的
            "predictions": predictions_data,
            "image_shape": frame_info.get("image_shape")
        }

        # # 暂时注释掉WebSocket广播，以隔离问题
        # await websocket_manager.broadcast_ai_result(websocket_payload)
        # logger.debug(f"主回调 handle_ai_prediction: 已广播 Frame ID {frame_id} 的AI结果。")
        logger.warning("主回调 handle_ai_prediction: WebSocket广播已临时禁用。")

    except Exception as e:
        logger.error(
            f"主回调 handle_ai_prediction 处理AI预测结果错误: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FASTAPI APP 应用生命周期管理"""
    global rtsp_thread, periodic_task, rtsp_server, ai_processor, ai_processor_task
    # 启动
    logger.info("FASTAPI 应用启动，正在初始化...")
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)

    # 初始化 RTSP 服务器实例
    logger.info("初始化 RTSPServer...")
    rtsp_server = RtspServer()  # Corrected: No arguments passed to constructor
    logger.info("RTSPServer 实例已创建.")

    # --- 提前初始化帧队列 ---
    import queue
    # 这个 frame_queue 实例将被 RtspServer 和 GStreamerFrameProducer 共享
    shared_frame_queue = queue.Queue(maxsize=60)  # 限制队列大小
    rtsp_server.frame_queue = shared_frame_queue  # 在服务器启动前设置队列
    logger.info("为RTSP服务器创建并设置了帧队列 (早期初始化)")
    # --- 帧队列初始化完毕 ---

    logger.info("正在启动 RTSP 服务器线程...")
    rtsp_thread = threading.Thread(target=run_rtsp_server_loop, daemon=True)
    rtsp_thread.start()
    logger.info("RTSP 服务器线程已启动")

    # 允许 RTSP 服务器启动前 AI 连接的时间
    logger.info("等待 RTSP 服务器完全启动...")
    await asyncio.sleep(5)  # 延长延迟，确保RTSP服务器完全启动

    # 初始化并启动 AIProcessor
    server_ip = get_server_ip()  # 使用实际服务器IP
    rtsp_stream_url_for_ai = f"rtsp://{server_ip}:{settings.RTSP_PORT}{settings.RTSP_PATH}"
    logger.info(f"使用 RTSP URL 初始化 AIProcessor: {rtsp_stream_url_for_ai}")

    try:
        # 创建GStreamerFrameProducer
        from app.services.gstreamer_frame_producer import GStreamerFrameProducer
        frame_producer = GStreamerFrameProducer(
            frame_queue=shared_frame_queue,  # 确保使用上面创建的同一个队列实例
            fps=10.0,  # 假设的帧率
            width=640,  # 默认宽度
            height=480  # 默认高度
        )
        logger.info(f"已创建GStreamerFrameProducer，使用默认分辨率640x480，帧率10.0")

        # 创建AIProcessor
        ai_processor = AIProcessor(
            model_id=settings.ROBOFLOW_MODEL_ID,
            on_prediction_callback=handle_ai_prediction,
            api_key=settings.ROBOFLOW_API_KEY,
            frame_producer=frame_producer
        )
        logger.info("AIProcessor 实例已创建。正在启动 AI 处理任务...")
        ai_processor_task = asyncio.create_task(ai_processor.start())
        logger.info("AIProcessor 任务已创建并开始后台处理。")
    except Exception as e:
        logger.error(f"初始化或启动 AIProcessor 失败: {e}", exc_info=True)
        ai_processor = None
        ai_processor_task = None

    # 启动定期任务
    periodic_task = asyncio.create_task(periodic_tasks())
    logger.info("定期任务已启动。")
    logger.info("应用启动完成。")

    logger.info(
        f"RTSP 服务器地址: rtsp://{server_ip}:{settings.RTSP_PORT}{settings.RTSP_PATH}")
    logger.info(f"FastAPI 服务器运行在: http://{server_ip}:{settings.API_PORT}")
    logger.info("请在 Android 设备上配置 RTSP 服务器地址进行测试。")

    yield  # 应用运行中

    # 关闭
    logger.info("应用关闭: 开始清理...")
    await shutdown_event()
    logger.info("应用关闭完成。")


# 创建应用实例
app = FastAPI(
    title="SafePath RTSP Receiver",
    lifespan=lifespan,
    debug=True  # 启用调试模式
)


@app.get("/")
async def root():
    return {"message": "RTSP服务器正在运行", "status": "OK"}


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
