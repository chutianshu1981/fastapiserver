#!/usr/bin/env python3
"""
WebSocket客户端测试脚本

该脚本连接到WebSocket服务器并接收AI检测结果
"""

import asyncio
import json
import websockets
import argparse
from datetime import datetime


async def connect_to_websocket(uri: str):
    """连接到WebSocket服务器并接收消息"""
    print(f"正在连接到 {uri}...")

    try:
        async with websockets.connect(uri) as websocket:
            print("已连接，等待消息...")

            # 发送一条初始消息
            await websocket.send(json.dumps({
                "type": "hello",
                "client": "test_client",
                "timestamp": int(datetime.now().timestamp() * 1000)
            }))

            # 持续接收消息
            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)

                    # 格式化输出
                    if data.get("type") == "ai_detection":
                        detections = data.get("data", {}).get("detections", [])
                        print(
                            f"\n接收到AI检测结果 [帧ID: {data.get('data', {}).get('frame_id', 'N/A')}]")
                        print(f"FPS: {data.get('data', {}).get('fps', 'N/A')}")
                        print(f"检测到 {len(detections)} 个对象:")

                        for i, det in enumerate(detections):
                            print(f"  {i+1}. 类别: {det.get('class', 'unknown')}, "
                                  f"置信度: {det.get('confidence', 0):.2f}, "
                                  f"位置: x={det.get('x_center', 0):.2f}, y={det.get('y_center', 0):.2f}, "
                                  f"大小: w={det.get('width', 0):.2f}, h={det.get('height', 0):.2f}")
                    elif data.get("type") == "ping":
                        print(".", end="", flush=True)
                    else:
                        print(f"\n接收到消息: {json.dumps(data, indent=2)}")

                except websockets.exceptions.ConnectionClosed:
                    print("\n连接已关闭")
                    break
                except Exception as e:
                    print(f"\n接收消息时出错: {e}")
                    break

    except Exception as e:
        print(f"连接失败: {e}")
        return


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="WebSocket客户端测试")
    parser.add_argument("--host", default="localhost", help="WebSocket服务器主机名")
    parser.add_argument("--port", type=int, default=8000,
                        help="WebSocket服务器端口")
    parser.add_argument("--path", default="/api/v1/ws", help="WebSocket路径")
    args = parser.parse_args()

    uri = f"ws://{args.host}:{args.port}{args.path}"

    try:
        asyncio.run(connect_to_websocket(uri))
    except KeyboardInterrupt:
        print("\n用户中断，退出...")


if __name__ == "__main__":
    main()
