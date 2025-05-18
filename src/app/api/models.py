"""API 数据模型模块

本模块定义了API层使用的Pydantic V2数据模型,包括:
- ServerStatus: 服务器状态模型
- StatusResponse: 状态响应模型
- SnapshotResponse: 快照响应模型
- VideoListResponse: 视频列表响应模型
- HealthResponse: 健康检查响应模型
"""
from enum import Enum
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ServerState(str, Enum):
    """服务器状态枚举"""
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class ServerStatus(BaseModel):
    """服务器状态模型"""
    state: ServerState = Field(..., description="服务器当前状态")
    uptime: float = Field(..., description="服务器运行时间(秒)")
    connections: int = Field(..., description="当前连接数")
    cpu_usage: float = Field(..., description="CPU使用率(%)")
    memory_usage: float = Field(..., description="内存使用率(%)")


class StatusResponse(BaseModel):
    """状态响应模型"""
    status: ServerStatus = Field(..., description="服务器状态信息")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="响应时间戳")


class SnapshotResponse(BaseModel):
    """快照响应模型"""
    image_data: bytes = Field(..., description="图像数据(bytes格式)")
    format: str = Field(..., description="图像格式(如'jpeg')")
    width: int = Field(..., description="图像宽度")
    height: int = Field(..., description="图像高度")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="快照时间戳")


class VideoInfo(BaseModel):
    """视频信息模型"""
    filename: str = Field(..., description="视频文件名")
    size: int = Field(..., description="文件大小(bytes)")
    duration: float = Field(..., description="视频时长(秒)")
    resolution: str = Field(..., description="视频分辨率")
    created_at: datetime = Field(..., description="创建时间")


class VideoListResponse(BaseModel):
    """视频列表响应模型"""
    videos: List[VideoInfo] = Field(default_factory=list, description="视频信息列表")
    total: int = Field(..., description="视频总数")
    page: int = Field(1, description="当前页码")
    page_size: int = Field(10, description="每页数量")


class HealthStatus(str, Enum):
    """健康状态枚举"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


class HealthResponse(BaseModel):
    """健康检查响应模型"""
    status: HealthStatus = Field(..., description="系统健康状态")
    version: str = Field(..., description="API版本")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="检查时间戳")
    details: Optional[dict] = Field(default=None, description="详细健康状态信息")


class ErrorResponse(BaseModel):
    """错误响应模型"""
    error: str = Field(..., description="错误信息")
    code: int = Field(..., description="错误代码")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="错误时间戳")


class DetectionObject(BaseModel):
    """检测到的对象模型"""
    class_name: str = Field(..., description="对象类别名称")
    confidence: float = Field(..., description="置信度", ge=0.0, le=1.0)
    x_center: float = Field(..., description="对象中心点X坐标(相对于图像宽度)")
    y_center: float = Field(..., description="对象中心点Y坐标(相对于图像高度)")
    width: float = Field(..., description="对象宽度(相对于图像宽度)")
    height: float = Field(..., description="对象高度(相对于图像高度)")


class AIDetectionResult(BaseModel):
    """AI检测结果模型"""
    frame_id: int = Field(..., description="帧ID")
    timestamp: int = Field(..., description="时间戳(毫秒)")
    fps: float = Field(..., description="当前处理帧率")
    detections: List[DetectionObject] = Field(
        default_factory=list, description="检测到的对象列表")
    error: Optional[str] = Field(None, description="错误信息(如果有)")
