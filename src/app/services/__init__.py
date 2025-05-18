"""
服务模块集合

本模块包含各种服务类，包括：
- AI 处理服务
- 帧生产者服务
- 监控服务
- 视频服务
- WebSocket 服务
"""

# 从各子模块导出主要类
from app.services.ai_processor import AIProcessor, example_prediction_handler
from app.services.gstreamer_frame_producer import GStreamerFrameProducer
from app.services.websocket_manager import ConnectionManager, manager
