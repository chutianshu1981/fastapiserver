# SafePath RTSP 服务器 API 文档

## API 设计原则

SafePath RTSP 服务器 API 遵循以下设计原则：

- **RESTful 设计**: 符合 REST 架构风格，资源导向的设计
- **强类型**: 使用 Pydantic V2 模型定义请求和响应数据结构，提高性能和安全性
- **简洁明确**: 端点命名直观，功能单一
- **一致性**: 统一的错误处理和响应格式
- **可测试性**: 接口设计便于自动化测试

## 基础信息

- **基础 URL**: `http://<server_ip>:8000`
- **认证方式**: 当前版本不需要认证 (未来可能添加)
- **默认内容类型**: `application/json`
- **数据序列化**: Pydantic V2

## API 端点概述

| 路径 | 方法 | 描述 |
|------|------|------|
| `/status` | GET | 获取服务器状态信息 |
| `/snapshot` | GET | 获取当前视频帧 |
| `/videos` | GET | 获取所有录制视频文件列表 |
| `/video/{filename}` | GET | 获取指定的视频文件 |
| `/health` | GET | 健康检查端点 |

## 详细端点说明

### 1. 获取服务器状态

**端点**: `/status`

**方法**: `GET`

**描述**: 获取 RTSP 服务器的当前运行状态，包括运行状态、启动时间、当前连接数和最后一帧接收时间。

**参数**: 无

**响应模型**:
```python
class ServerStatus(BaseModel):
    is_running: bool
    start_time: Optional[datetime] = None
    connections: int = 0
    last_frame_time: Optional[datetime] = None
    server_ip: Optional[str] = None

class StatusResponse(BaseModel):
    status: ServerStatus
    rtsp_url: str
```

**响应示例**:
```json
{
  "status": {
    "is_running": true,
    "start_time": "2025-05-03T08:30:15.123456",
    "connections": 2,
    "last_frame_time": "2025-05-03T10:15:22.654321",
    "server_ip": "192.168.1.100"
  },
  "rtsp_url": "rtsp://192.168.1.100:554/live"
}
```

**错误码**:
- `500 Internal Server Error`: 服务器内部错误

**实现源码文件**: `app/api/routes.py` 和 `app/api/models.py`

### 2. 获取当前视频帧

**端点**: `/snapshot`

**方法**: `GET`

**描述**: 获取当前视频流的最新帧。可以选择以文件形式返回或者以 Base64 编码形式返回。

**参数**:
- `as_file` (查询参数, 布尔型, 可选): 如果为 `true` 则以文件形式返回，默认为 `false`（返回 Base64 编码）

**响应模型**:
```python
class SnapshotResponse(BaseModel):
    image_base64: str
```

或返回文件流 (当 `as_file=true` 时)

**响应示例** (as_file=false):
```json
{
  "image_base64": "iVBORw0KGgoAAAANSUhEUgAA..."
}
```

**错误码**:
- `404 Not Found`: 没有可用的视频帧
- `503 Service Unavailable`: RTSP 服务未运行
- `500 Internal Server Error`: 服务器内部错误

**实现源码文件**: `app/api/routes.py`

### 3. 获取可用视频列表

**端点**: `/videos`

**方法**: `GET`

**描述**: 获取所有可用的录制视频文件列表。

**参数**: 无

**响应模型**:
```python
class VideoListResponse(BaseModel):
    videos: List[str]
```

**响应示例**:
```json
{
  "videos": [
    "video_20250503_101522.mp4",
    "video_20250503_091015.mp4",
    "video_20250502_183045.mp4"
  ]
}
```

**错误码**:
- `500 Internal Server Error`: 获取视频列表失败

**实现源码文件**: `app/api/routes.py` 和 `app/services/video_service.py`

### 4. 获取特定视频文件

**端点**: `/video/{filename}`

**方法**: `GET`

**描述**: 获取特定的视频文件进行下载或查看，仅支持MP4格式。

**参数**:
- `filename` (路径参数, 字符串): 视频文件名，从 `/videos` 接口获取

**响应**: 视频文件流，内容类型为 `video/mp4`

**错误码**:
- `404 Not Found`: 请求的视频文件不存在或非MP4格式
- `500 Internal Server Error`: 服务器内部错误

**实现源码文件**: `app/api/routes.py` 和 `app/services/video_service.py`

### 5. 健康检查

**端点**: `/health`

**方法**: `GET`

**描述**: 用于监控系统的健康检查端点。主要供自动化监控系统使用。

**参数**: 无

**响应模型**:
```python
class HealthResponse(BaseModel):
    status: str = "ok"
```

**响应示例**:
```json
{
  "status": "ok"
}
```

**错误码**:
- `503 Service Unavailable`: 服务不可用

**实现源码文件**: `app/api/routes.py`

## 异常与错误处理

所有 API 端点都使用标准 HTTP 状态码表示操作结果：

| 状态码 | 描述 | 典型场景 |
|--------|------|----------|
| 200 | OK | 请求成功 |
| 400 | Bad Request | 请求参数错误 |
| 404 | Not Found | 请求的资源不存在 |
| 500 | Internal Server Error | 服务器内部错误 |
| 503 | Service Unavailable | RTSP服务未运行 |

错误响应的标准格式为：

```json
{
  "detail": "错误描述信息"
}
```

## API 使用示例

### 使用 cURL 获取服务器状态

```bash
curl -X GET http://localhost:8000/status
```

### 使用 Python 获取当前视频帧

```python
import requests
import base64
from PIL import Image
import io

# 获取图像的base64编码
response = requests.get("http://localhost:8000/snapshot")
if response.status_code == 200:
    image_data = response.json()["image_base64"]
    
    # 将base64解码为图像
    image_bytes = base64.b64decode(image_data)
    image = Image.open(io.BytesIO(image_bytes))
    image.show()
else:
    print(f"错误: {response.status_code}, {response.json()['detail']}")
```

### 使用 JavaScript 获取视频列表

```javascript
fetch('http://localhost:8000/videos')
  .then(response => {
    if (!response.ok) {
      throw new Error(`HTTP错误 ${response.status}`);
    }
    return response.json();
  })
  .then(data => {
    const videos = data.videos;
    console.log('可用视频:', videos);
  })
  .catch(error => console.error('获取视频列表失败:', error));
```

## 安全注意事项

当前 API 版本不包含认证和授权机制，这在生产环境中可能存在安全风险。在部署到生产环境前，建议考虑以下安全措施：

1. 添加适当的认证机制（如 OAuth2、JWT 或 API Key）
2. 实施 API 速率限制，防止滥用
3. 只暴露必要的端口和 API，使用反向代理保护 API 接口
4. 添加 HTTPS 加密传输

## API 版本控制

当前 API 版本为 v1。未来可能通过以下方式实现版本控制：

1. URL 路径前缀: `/api/v2/...`
2. 请求头: `Accept: application/vnd.safepath.v2+json`

## 性能考量

API实现采用了以下性能优化措施：

1. 使用Pydantic V2进行数据验证和序列化，相比V1提升了约4倍的性能
2. 使用FastAPI的异步路由处理函数，避免阻塞
3. 对于CPU密集型操作，使用asyncio.to_thread将其移到后台线程执行
4. 使用Python 3.12提供的更快的解释器性能