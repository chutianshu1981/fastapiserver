# SafePath RTSP 服务器架构说明

## 系统架构概览

SafePath RTSP 服务器采用分层模块化设计，将系统划分为明确的功能层和组件：

```
+------------------------------------------+
|               客户端层                    |
|  SafePath Android App (RTSP流推送源)      |
+------------------+---------------------+
                   |
                   v
+------------------------------------------+
|               接入层                      |
|  RTSP服务器模块（GStreamer 1.22.0 系统包） |
+------------------+---------------------+
                   |
                   v
+------------------------------------------+
|               服务层                      |
| +----------------+  +------------------+ |
| | 视频处理服务     |  | 存储管理服务     | |
| +----------------+  +------------------+ |
+------------------+---------------------+
                   |
                   v
+------------------------------------------+
|               API层                      |
|  FastAPI路由和端点 (Pydantic V2模型)      |
+------------------+---------------------+
                   |
                   v
+------------------------------------------+
|               客户应用                    |
|  浏览器/监控系统/其他客户端               |
+------------------------------------------+
```

## 分层架构

### 1. API层 (`app/api/`)

处理HTTP请求和响应，负责API接口的定义和路由。

**文件结构**:
- `routes.py` - 定义API路由和端点处理函数
- `models.py` - 定义Pydantic V2请求和响应数据模型

**设计原则**:
- API端点专注于请求处理和响应格式化
- 业务逻辑委托给服务层处理
- 使用依赖注入获取所需服务
- 保持端点处理函数简洁，每个函数不超过30行

### 2. 服务层 (`app/services/`)

包含应用的核心业务逻辑，协调不同组件的工作。

**文件结构**:
- `video_service.py` - 视频处理和管理服务

**设计原则**:
- 每个服务类专注于单一业务领域
- 服务之间通过明确的接口通信
- 避免服务之间的循环依赖
- 使用依赖注入获取基础设施组件

### 3. 基础设施层

处理底层功能实现，如RTSP服务器、视频处理等。

#### 3.1 RTSP服务器模块 (`app/rtsp/`)

基于GStreamer 1.22.0系统包实现RTSP服务器，负责接收视频流。

**文件结构**:
- `server.py` - RTSP服务器核心实现

**主要职责**:
- 监听RTSP端口(默认554)并处理连接
- 解析H.264编码的视频流
- 通过appsink提取视频帧
- 录制视频片段为MP4格式
- 管理客户端连接状态

**核心类**: `RtspServer`

**主要方法**:
- `initialize()` - 初始化GStreamer和RTSP服务器
- `set_connection_callbacks()` - 设置客户端连接/断开事件回调
- `get_latest_frame_path()` - 获取最新视频帧路径

#### 3.2 核心配置和工具 (`app/core/` 和 `app/utils/`)

提供全局配置和通用工具函数。

**文件结构**:
- `app/core/config.py` - 应用配置管理 (使用Pydantic V2 Settings)
- `app/core/logger.py` - 日志系统配置
- `app/utils/helpers.py` - 工具函数

### 4. 主应用模块 (`app/main.py`)

应用的入口点，负责组装和启动各组件。

**主要职责**:
- 初始化FastAPI应用
- 初始化GStreamer和GObject线程
- 注册中间件和路由
- 配置跨域资源共享(CORS)
- 启动RTSP服务器
- 初始化和调度后台任务

## 数据流说明

### 1. RTSP流接收和处理流程

```
Android客户端 ---> RTSP服务器模块 ---> appsink
    |                                     |
    v                                     v
H.264编码流     帧处理 ---> OpenCV处理 ---> 存储为图像文件(JPG)
                 |
                 v
              视频封装 ---> 存储为视频文件(MP4)
```

### 2. API请求处理流程

```
客户端请求 ---> FastAPI路由 ---> API端点处理函数
                                    |
                                    v
                                服务层方法
                                    |
                                    v
                                基础设施组件
                                    |
                                    v
                           Pydantic V2响应模型 ---> HTTP响应
```

### 3. 后台任务处理流程

```
定时触发器(asyncio) ---> 视频服务 ---> 检查文件时间 ---> 删除过期视频
```

## 组件交互

### 1. 依赖注入

系统使用依赖注入模式管理组件间依赖，提高代码的可测试性和灵活性。

```python
# 服务注入函数示例
def get_video_service_instance() -> VideoService:
    """获取视频服务实例，用于依赖注入"""
    return video_service

# API端点中使用依赖注入
@router.get("/videos", response_model=VideoListResponse)
async def list_videos(
    video_service: VideoService = Depends(get_video_service_instance)
) -> VideoListResponse:
    """获取视频列表"""
    return VideoListResponse(videos=video_service.get_video_list())
```

### 2. 事件回调

RTSP服务器使用GStreamer信号和回调机制通知连接状态变化：

```python
# 设置连接事件回调
rtsp_server.set_connection_callbacks(
    on_client_connected=increment_connection_count,
    on_client_disconnected=decrement_connection_count
)
```

### 3. 异步处理

系统使用Python 3.12的异步编程模型处理I/O密集型操作，提高并发性能：

```python
# 定期任务使用asyncio
async def periodic_tasks():
    while True:
        # 将同步操作包装在异步任务中
        files_cleaned = await asyncio.to_thread(
            video_service.cleanup_old_videos
        )
        logger.info(f"清理了 {files_cleaned} 个过期视频文件")
        # 睡眠24小时
        await asyncio.sleep(86400)
```

## 部署架构

系统采用Docker容器化部署，基于Debian Bookworm确保环境一致性和简化部署流程：

```
+-----------------------------------+
|        Docker容器 (Debian 12)      |
|                                   |
| +-------------+  +-------------+  |
| | FastAPI应用 |  | GStreamer   |  |
| +-------------+  |   1.22.0    |  |
|                  +-------------+  |
|                                   |
| +--------------------------------+|
| |           Python 3.12         | |
| +--------------------------------+|
+----------------+------------------+
                 |
                 v
+----------------+------------------+
|        持久化存储卷                |
|     (视频文件和图像存储)           |
+-----------------------------------+
```

**网络配置**:
- API端口: 8000 (HTTP)
- RTSP端口: 554 (RTSP协议)

**依赖管理**:
- 使用PDM管理Python依赖 (pyproject.toml)
- 系统级依赖通过Dockerfile安装

## 扩展点

系统设计考虑了以下扩展点：

1. **视频分析集成**
   - 通过appsink回调可以接入计算机视觉算法
   - 预设帧处理钩子便于插入分析组件

2. **多路RTSP支持**
   - 服务器设计允许扩展为支持多个RTSP端点
   - 可通过配置添加额外的媒体路径和处理管道

3. **云存储集成**
   - 存储服务接口支持扩展为将视频上传至云存储
   - 可实现额外的存储提供者适配器

4. **WebRTC直播**
   - 可添加WebRTC支持，允许浏览器直接低延迟观看直播流

## 性能考量

1. **内存使用优化**
   - 使用Python 3.12和Pydantic V2获得更好的内存效率
   - 视频处理采用流式处理，避免加载完整视频到内存
   - 定期清理过期视频文件，防止磁盘空间耗尽

2. **CPU使用优化**
   - 利用GStreamer 1.22.0的硬件加速能力降低CPU使用
   - 将CPU密集任务放入专用线程池或使用asyncio.to_thread，避免阻塞事件循环

3. **扩展性**
   - 基于容器的部署支持水平扩展
   - 组件间的低耦合设计便于单独扩展瓶颈组件