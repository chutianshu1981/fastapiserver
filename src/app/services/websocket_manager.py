"""
WebSocket 连接管理器

该模块实现 WebSocket 连接管理，负责：
1. 管理多客户端 WebSocket 连接
2. 广播 AI 检测结果到所有连接的客户端
3. 保持连接活跃检查
"""
from typing import Dict, List, Set, Any
import json
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger
from datetime import datetime


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        """初始化连接管理器"""
        self.active_connections: Dict[str, WebSocket] = {}
        self.ping_task = None
        self.is_running = False

    async def connect(self, websocket: WebSocket, client_id: str):
        """
        建立与客户端的连接

        Args:
            websocket: WebSocket连接对象
            client_id: 客户端标识符
        """
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(
            f"客户端 {client_id} 已连接. 当前活跃连接数: {len(self.active_connections)}")

        # 发送欢迎消息
        welcome_message = {
            "type": "connection_status",
            "status": "connected",
            "message": "成功连接到AI分析服务器",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "client_id": client_id
        }
        await self.send_personal_message(welcome_message, client_id)

        # 确保ping任务在运行
        if not self.is_running and not self.ping_task:
            self.is_running = True
            self.ping_task = asyncio.create_task(self._ping_clients())

    async def disconnect(self, client_id: str):
        """
        断开与客户端的连接

        Args:
            client_id: 客户端标识符
        """
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(
                f"客户端 {client_id} 已断开连接. 当前活跃连接数: {len(self.active_connections)}")

        # 如果没有连接了，停止ping任务
        if not self.active_connections and self.ping_task and self.is_running:
            self.is_running = False
            self.ping_task.cancel()
            try:
                await self.ping_task
            except asyncio.CancelledError:
                logger.info("Ping任务已取消")
            self.ping_task = None

    async def send_personal_message(self, message: Dict[str, Any], client_id: str):
        """
        发送消息给指定客户端

        Args:
            message: 要发送的消息
            client_id: 客户端标识符
        """
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            try:
                if isinstance(message, str):
                    await websocket.send_text(message)
                else:
                    await websocket.send_json(message)
            except Exception as e:
                logger.error(f"发送消息给客户端 {client_id} 失败: {e}")
                await self.disconnect(client_id)

    async def broadcast(self, message: Dict[str, Any]):
        """
        广播消息给所有连接的客户端

        Args:
            message: 要广播的消息
        """
        disconnected_clients = []

        for client_id, websocket in self.active_connections.items():
            try:
                if isinstance(message, str):
                    await websocket.send_text(message)
                else:
                    await websocket.send_json(message)
            except Exception as e:
                logger.error(f"广播消息给客户端 {client_id} 失败: {e}")
                disconnected_clients.append(client_id)

        # 清理断开的连接
        for client_id in disconnected_clients:
            await self.disconnect(client_id)

    async def broadcast_ai_result(self, result: Dict[str, Any]):
        """
        广播AI检测结果给所有连接的客户端

        Args:
            result: AI检测结果
        """
        # 添加消息类型标识
        message = {
            "type": "ai_detection",
            "data": result
        }
        await self.broadcast(message)

    async def _ping_clients(self):
        """定期发送ping消息以保持连接活跃"""
        try:
            while self.is_running:
                if self.active_connections:
                    ping_message = {
                        "type": "ping",
                        "timestamp": int(datetime.now().timestamp() * 1000)
                    }
                    await self.broadcast(ping_message)
                await asyncio.sleep(30)  # 每30秒ping一次
        except asyncio.CancelledError:
            logger.info("Ping任务已取消")
        except Exception as e:
            logger.error(f"Ping任务异常: {e}")
            self.is_running = False
            self.ping_task = None


# 创建全局连接管理器实例
manager = ConnectionManager()
