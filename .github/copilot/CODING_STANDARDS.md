# SafePath RTSP 服务器编码规范

## 核心编码原则

本项目遵循以下核心编码原则，这些原则将指导所有开发工作：

1. **单一职责原则** - 每个模块、类或函数应该只有一个职责
2. **模块化** - 将代码拆分为逻辑清晰的模块，限制文件大小
3. **低耦合** - 减少组件之间的依赖，使用依赖注入
4. **可测试性** - 编写易于单元测试的代码
5. **显式胜于隐式** - 避免魔法方法和隐式行为

## 技术规范

- **Python 版本**: 严格使用 Python 3.12
- **依赖管理**: 使用 PDM (配合 uv 加速)，维护 pyproject.toml 和 pdm.lock
- **数据验证**: 使用 Pydantic V2 进行数据验证和序列化
- **代码格式化**: Black 格式化工具 (行长度 88 字符)
- **类型检查**: 使用 mypy 进行静态类型检查

## 代码组织

### 文件大小限制

* 单个Python文件不超过**300行**代码（不包括注释和空行）
* 绝对不超过**500行**代码
* 如文件超出限制，应将其拆分为多个逻辑相关但功能独立的模块

### 目录结构

项目采用src布局和分层架构，目录结构应遵循以下模式：

```
src/
├── app/                      # 应用程序主目录
│   ├── __init__.py
│   ├── main.py               # 主应用入口 (FastAPI app)
│   ├── api/                  # API层
│   │   ├── __init__.py
│   │   ├── routes.py         # API路由定义
│   │   └── models.py         # Pydantic V2 API数据模型
│   ├── core/                 # 核心配置
│   │   ├── __init__.py
│   │   ├── config.py         # 应用配置 (Pydantic Settings)
│   │   └── logger.py         # 日志配置
│   ├── rtsp/                 # RTSP相关模块
│   │   ├── __init__.py
│   │   └── server.py         # RTSP服务器核心 (使用系统GStreamer)
│   ├── services/             # 服务层
│   │   ├── __init__.py
│   │   └── video_service.py  # 视频处理服务
│   └── utils/                # 工具函数
│       ├── __init__.py
│       └── helpers.py        # 辅助函数
```

## Python 代码风格

本项目严格遵循 [PEP 8](https://peps.python.org/pep-0008/) 编码规范，并采用以下特定约定：

### 命名规范

* **类名**：使用 `PascalCase` (例如: `RtspServer`, `VideoProcessor`)
* **函数/方法名**：使用 `snake_case` (例如: `get_latest_frame`, `update_connection_count`)
* **变量名**：使用 `snake_case` (例如: `frame_path`, `connection_count`)
* **常量名**：使用全大写 `SNAKE_CASE` (例如: `RTSP_PORT`, `OUTPUT_DIR`)
* **模块名**：使用 `snake_case` (例如: `rtsp_server.py`, `video_service.py`)
* **私有方法/属性**：使用单下划线前缀 `_` (例如: `_parse_config`)
* **保护方法/属性**：使用双下划线前缀 `__` (例如: `__secure_token`)
* **Pydantic模型名称**：使用 `PascalCase` 并附加相应后缀 (例如: `ServerStatus`, `VideoListResponse`)

### 代码格式

* 缩进使用 4 个空格（不使用制表符）
* 最大行长度为 88 字符
* 使用双引号 `"` 作为字符串默认引号
* 顶级函数和类之间空两行，方法之间空一行
* 使用 Black 自动格式化工具确保格式一致性

### 导入规范

按以下顺序组织导入语句，各组之间空一行：

```python
# 标准库导入
import os
import sys
from datetime import datetime

# 第三方库导入
import cv2
from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel, Field

# 本地应用/库导入
from app.rtsp.server import RtspServer
from app.services.video_service import VideoService
```

导入规则：
- 总是使用绝对导入而不是相对导入
- 避免使用通配符导入 (`from module import *`)
- 对于大型库，只导入需要的部分
- 对于相同模块的多个导入，使用多行导入格式

## 文档规范

### 模块文档

每个Python模块开头应该包含模块文档字符串，描述模块的用途和主要组件：

```python
"""
RTSP服务器模块

该模块实现了基于GStreamer 1.22.0的RTSP服务器，负责接收Android客户端
推送的视频流，并处理视频帧提取和存储。
"""
```

### 类文档

所有类应该有清晰的文档字符串，描述其用途、责任和使用方式：

```python
class RtspServer:
    """RTSP服务器，处理视频流接收和处理
    
    该类封装了GStreamer RTSP服务器的功能，负责监听指定端口
    接收RTSP流，并提供视频帧提取和处理功能。
    
    Attributes:
        port: RTSP服务器监听端口
        path: RTSP媒体路径
        output_dir: 视频输出目录
    """
```

### 函数/方法文档

所有函数和方法都应有文档字符串，采用三引号 `"""` 格式，包含简短描述、参数说明和返回值说明：

```python
def get_latest_frame_path(self) -> Optional[str]:
    """获取最新视频帧的文件路径
    
    搜索输出目录，找到最新的JPG文件并返回其完整路径。
    
    Returns:
        str: 最新视频帧的完整文件路径，如果不存在则返回None
        
    Raises:
        IOError: 如果输出目录不可访问
    """
```

## 类型提示

本项目强制使用 Python 类型提示，提高代码可读性和IDE支持：

```python
def update_connection_count(delta: int) -> None:
    """更新当前连接数
    
    Args:
        delta: 连接数变化值，连接时+1，断开时-1
    """
    server_status["connections"] += delta
    logger.info(f"当前连接数: {server_status['connections']}")
```

对于复杂类型，使用 `typing` 模块：

```python
from typing import Dict, List, Optional, Union, Callable

def get_video_metadata(
    filename: str, 
    include_frames: bool = False
) -> Dict[str, Union[str, int, float]]:
    """获取视频元数据"""
    # 实现...
```

## Pydantic V2 模型规范

使用 Pydantic V2 定义所有API数据模型和配置：

```python
from pydantic import BaseModel, Field

class ServerStatus(BaseModel):
    is_running: bool
    start_time: Optional[datetime] = None
    connections: int = Field(default=0, ge=0)
    last_frame_time: Optional[datetime] = None
    server_ip: Optional[str] = None

class StatusResponse(BaseModel):
    status: ServerStatus
    rtsp_url: str
```

## 错误处理

错误处理遵循以下原则：

* 使用异常处理捕获可预见的错误
* 在日志中记录异常信息
* 使用具体的异常类型，避免捕获所有异常
* 使用 FastAPI 的 HTTPException 返回正确的状态码和错误信息

```python
try:
    frame_path = rtsp_server.get_latest_frame_path()
    if not frame_path或 not os.path.exists(frame_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                            detail="没有可用的视频帧")
except IOError as e:
    logger.error(f"读取视频帧失败: {e}")
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                        detail="无法读取视频帧")
```

## 异步编程

利用 Python 3.12 的改进异步功能和 FastAPI 的异步编程模型：

* 使用 `async/await` 语法处理 I/O 绑定操作
* API 路由处理函数应设为异步函数
* 使用 `asyncio.to_thread()` 包装同步阻塞操作，替代过去的线程池
* 避免在异步函数中直接执行阻塞操作

```python
import asyncio

@router.get("/videos", response_model=VideoListResponse)
async def list_videos(
    video_service: VideoService = Depends(get_video_service)
) -> VideoListResponse:
    """获取视频列表"""
    # 避免在异步路由中直接执行同步阻塞操作
    videos = await asyncio.to_thread(video_service.get_video_list)
    return VideoListResponse(videos=videos)
```

## 日志记录

使用Python标准库的`logging`模块进行日志记录：

* 为每个模块创建专用的 logger 实例
* 根据重要性选择适当的日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
* 日志消息应提供足够上下文，便于调试

```python
import logging
logger = logging.getLogger("rtsp_server")

# 不同级别的日志使用
logger.debug("开始处理视频帧 %s", frame_id)  # 使用%s格式化，避免字符串拼接
logger.info("成功连接客户端 %s", client_ip)
logger.warning("接收到异常帧大小: %d bytes", frame_size)
logger.error("无法保存视频文件: %s", str(e))
logger.critical("RTSP服务器崩溃: %s", error_msg)
```

## 依赖管理

使用 PDM 进行依赖管理：

* 所有项目依赖记录在 `pyproject.toml` 文件中
* 明确指定版本范围，如 `fastapi>=0.115.0,<0.116.0`
* 区分开发依赖和生产依赖
* 使用 `pdm.lock` 确保依赖的确定性

```toml
[project]
name = "rtsp-receiver-service"
version = "0.1.0"
description = "RTSP Video Stream Receiver Service"
dependencies = [
    "fastapi[standard]>=0.115.0,<0.116.0",
    "uvicorn[standard]>=0.34.0,<0.35.0",
    "pydantic>=2.11.0,<3.0.0",
    "opencv-python>=4.11.0,<4.12.0",
    "python-dotenv>=1.0.0",
]
requires-python = ">=3.12,<3.13"  # 明确指定Python版本
```

## 测试规范

* 使用 `pytest` 框架编写单元测试和集成测试
* 测试文件命名为 `test_*.py` 并放在 `tests/` 目录下
* 使用异步测试处理异步代码 (pytest-asyncio)
* 使用 `httpx` 测试 FastAPI 端点
* 提供高测试覆盖率，特别是核心功能

```python
# tests/test_api.py (异步测试示例)
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_health_endpoint():
    """测试健康检查端点"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
```