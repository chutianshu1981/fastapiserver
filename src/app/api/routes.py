"""API 路由模块

本模块实现了所有API端点，包括:
- GET /status: 获取服务器状态
- GET /snapshot: 获取当前视频帧
- GET /videos: 获取视频列表
- GET /video/{filename}: 获取指定视频
- GET /health: 健康检查端点
- WS /ws: WebSocket连接点，用于推送AI检测结果

包含了请求限流、CORS支持、错误处理等功能。
"""
from typing import Any, Dict, List, Optional, Callable, Coroutine
import asyncio
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi.encoders import jsonable_encoder
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.requests import Request

from app.api.models import (
    StatusResponse, SnapshotResponse, VideoListResponse,
    HealthResponse, ErrorResponse, HealthStatus, ServerStatus,
    ServerState, VideoInfo, AIDetectionResult, DetectionObject
)
from app.rtsp.server import RtspServer
from app.services.video_service import VideoService
from app.services.websocket_manager import manager as websocket_manager
from app.core.logger import get_logger
from app.core.config import get_settings, Settings

# 创建路由器
router = APIRouter()
logger = get_logger(__name__)
settings: Settings = get_settings()

# 创建限流器
limiter = Limiter(key_func=get_remote_address)

# 安全头中间件


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全头中间件，添加基本的安全响应头"""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


# 服务管理器
class ServiceManager:
    """服务管理器，负责管理全局服务实例"""

    def __init__(self):
        """初始化服务管理器"""
        self._rtsp_server: Optional[RtspServer] = None
        self._video_service: Optional[VideoService] = None

    @property
    def rtsp_server(self) -> RtspServer:
        """获取RTSP服务器实例"""
        if not self._rtsp_server:
            raise HTTPException(status_code=503, detail="RTSP服务尚未初始化")
        return self._rtsp_server

    @property
    def video_service(self) -> VideoService:
        """获取视频服务实例"""
        if not self._video_service:
            raise HTTPException(status_code=503, detail="视频服务尚未初始化")
        return self._video_service

    async def initialize(self) -> None:
        """初始化服务"""
        self._rtsp_server = RtspServer()
        self._video_service = VideoService()
        await self._video_service.start()
        logger.info("服务已初始化")

    async def cleanup(self) -> None:
        """清理服务"""
        tasks = []

        if self._rtsp_server and hasattr(self._rtsp_server, 'stop'):
            tasks.append(self._rtsp_server.stop())

        if self._video_service:
            tasks.append(self._video_service.stop())

        if tasks:
            try:
                await asyncio.gather(*tasks)
                logger.info("服务已清理")
            except Exception as e:
                logger.error(f"服务清理异常: {e}")
                # 继续抛出异常，让FastAPI处理
                raise
        else:
            logger.info("无需清理的服务")


# 创建服务管理器实例
service_manager = ServiceManager()


# 依赖注入函数
def get_rtsp_server() -> RtspServer:
    """获取RTSP服务器实例"""
    return service_manager.rtsp_server


def get_video_service() -> VideoService:
    """获取视频服务实例"""
    return service_manager.video_service


# 错误处理
async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """处理 HTTP 异常"""
    error_response = ErrorResponse(
        error=str(exc.detail),
        code=exc.status_code,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(error_response)
    )


# 事件处理器
async def startup_event() -> None:
    """启动事件处理器"""
    await service_manager.initialize()


async def shutdown_event() -> None:
    """关闭事件处理器"""
    await service_manager.cleanup()


# 路由实现
@router.get(
    "/status",
    response_model=StatusResponse,
    description="获取服务器状态",
    responses={500: {"model": ErrorResponse}},
)
@limiter.limit("10/minute")
async def get_status(
    request: Request,
    rtsp_server: RtspServer = Depends(get_rtsp_server)
) -> StatusResponse:
    """获取服务器状态"""
    try:
        # 获取系统状态
        status = ServerStatus(
            state=ServerState.RUNNING if rtsp_server.is_running else ServerState.STOPPED,
            uptime=0.0,  # TODO: 从监控服务获取
            connections=rtsp_server.get_client_count(),
            cpu_usage=0.0,  # TODO: 从系统监控获取
            memory_usage=0.0  # TODO: 从系统监控获取
        )
        return StatusResponse(status=status)
    except Exception as e:
        logger.error(f"获取服务器状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get(
    "/snapshot",
    response_model=SnapshotResponse,
    description="获取当前视频帧",
    responses={500: {"model": ErrorResponse}},
)
@limiter.limit("30/minute")
async def get_snapshot(
    request: Request,
    video_service: VideoService = Depends(get_video_service)
) -> SnapshotResponse:
    """获取当前视频帧"""
    try:
        # TODO: 实现从视频服务获取当前帧
        raise HTTPException(status_code=501, detail="功能未实现")
    except Exception as e:
        logger.error(f"获取视频帧失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取视频帧失败")


@router.get(
    "/videos",
    response_model=VideoListResponse,
    description="获取视频列表",
    responses={500: {"model": ErrorResponse}},
)
@limiter.limit("20/minute")
async def list_videos(
    request: Request,
    page: int = 1,
    page_size: int = 10,
    video_service: VideoService = Depends(get_video_service)
) -> VideoListResponse:
    """获取视频列表"""
    try:
        # TODO: 实现从VideoService获取视频列表
        videos: List[VideoInfo] = []
        total = 0
        return VideoListResponse(
            videos=videos,
            total=total,
            page=page,
            page_size=page_size
        )
    except Exception as e:
        logger.error(f"获取视频列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取视频列表失败")


@router.get(
    "/video/{filename}",
    description="获取指定视频",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    },
)
@limiter.limit("30/minute")
async def get_video(
    request: Request,
    filename: str,
    video_service: VideoService = Depends(get_video_service)
) -> StreamingResponse:
    """获取指定视频文件"""
    try:
        # TODO: 实现从VideoService获取视频文件流
        raise HTTPException(status_code=501, detail="功能未实现")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取视频文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取视频文件失败")


@router.get(
    "/health",
    response_model=HealthResponse,
    description="健康检查端点",
    responses={500: {"model": ErrorResponse}},
)
@limiter.limit("60/minute")
async def health_check(
    request: Request,
    rtsp_server: RtspServer = Depends(get_rtsp_server),
    video_service: VideoService = Depends(get_video_service)
) -> HealthResponse:
    """系统健康检查"""
    try:
        # 获取服务健康状态
        vs_status = video_service.get_health_status()
        rs_status = rtsp_server.is_running

        # 确定整体健康状态
        if rs_status and vs_status.get('healthy', False):
            status = HealthStatus.HEALTHY
        elif not rs_status and not vs_status.get('healthy', False):
            status = HealthStatus.UNHEALTHY
        else:
            status = HealthStatus.DEGRADED

        return HealthResponse(
            status=status,
            version="1.0.0",  # TODO: 从配置获取版本号
            details={
                "rtsp_server": "healthy" if rs_status else "unhealthy",
                "video_service": vs_status
            }
        )
    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}")
        raise HTTPException(status_code=500, detail="健康检查失败")


# 配置CORS
def setup_cors(app: FastAPI) -> None:
    """配置CORS中间件"""
    # TODO: 从配置获取CORS设置
    origins = ["*"]  # 默认允许所有源

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 添加安全头中间件
    app.add_middleware(SecurityHeadersMiddleware)


# 配置应用
def setup_app(app: FastAPI) -> None:
    """配置FastAPI应用"""
    # 添加异常处理器
    app.exception_handler(HTTPException)(http_exception_handler)

    # 配置CORS
    setup_cors(app)

    # 包含路由器
    app.include_router(router, prefix="/api/v1")

    # 注册启动和关闭事件
    app.add_event_handler("startup", startup_event)
    app.add_event_handler("shutdown", shutdown_event)


# WebSocket路由
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket端点，用于实时推送AI检测结果

    客户端可以通过该端点接收实时AI检测结果
    """
    # 生成唯一客户端ID
    client_id = str(uuid.uuid4())

    try:
        # 接受WebSocket连接
        await websocket_manager.connect(websocket, client_id)
        logger.info(f"客户端 {client_id} 已成功连接到WebSocket")

        # 持续接收消息，以保持连接活跃
        while True:
            try:
                data = await websocket.receive_text()
                # 可以处理来自客户端的消息
                # 这里简单地回显收到的消息
                await websocket_manager.send_personal_message(
                    {"type": "echo", "message": data},
                    client_id
                )
            except WebSocketDisconnect:
                logger.info(f"客户端 {client_id} 断开了WebSocket连接")
                break
    except Exception as e:
        logger.error(f"WebSocket连接处理错误: {e}")
    finally:
        # 确保断开连接
        await websocket_manager.disconnect(client_id)
