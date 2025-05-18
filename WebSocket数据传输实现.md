# WebSocket数据传输实现

## 概述

本文档描述WebSocket连接的实现方式，用于将AI处理结果从服务器传输到Android客户端。

## 架构

该实现包含以下组件：

1. **WebSocket连接管理器**：
   - 位于 `app/services/websocket_manager.py`
   - 负责管理所有WebSocket客户端连接
   - 提供广播和点对点消息发送功能

2. **WebSocket API端点**：
   - 位于 `app/api/routes.py`
   - 提供 `/api/v1/ws` 端点供客户端连接

3. **AI处理器集成**：
   - AI处理器结果通过回调函数发送到WebSocket连接管理器
   - 所有AI检测结果实时广播给所有连接的客户端

## 数据流

```
[RTSP视频流] -> [GStreamer处理] -> [AIProcessor] -> [WebSocket广播] -> [Android客户端]
```

## 消息格式

WebSocket服务器发送的消息采用JSON格式，包含以下类型：

### 1. AI检测结果消息

```json
{
  "type": "ai_detection",
  "data": {
    "frame_id": 12345,
    "timestamp": 1652489122000,
    "fps": 25.5,
    "detections": [
      {
        "class": "blind_lane",
        "confidence": 0.92,
        "x_center": 0.45,
        "y_center": 0.65,
        "width": 0.12,
        "height": 0.08
      },
      ... 
    ]
  }
}
```

### 2. 连接状态消息

```json
{
  "type": "connection_status",
  "status": "connected",
  "message": "成功连接到AI分析服务器",
  "timestamp": 1652489100000,
  "client_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 3. Ping消息（保持连接）

```json
{
  "type": "ping",
  "timestamp": 1652489150000
}
```

## 测试

可以使用提供的测试客户端脚本测试WebSocket连接：

```bash
python src/test_websocket_client.py --host localhost --port 8000
```

## Android客户端实现建议

Android客户端应实现WebSocket客户端，可以使用以下库：
* OkHttp WebSocket
* Java-WebSocket

连接URI格式：
```
ws://{server_ip}:8000/api/v1/ws
```

客户端应处理连接断开并实现自动重连逻辑。
