# RTSP 视频流接收服务器方案书

## **项目概述**

设计并实现一个基于 FastAPI 的现代化服务端应用，用于接收和处理 SafePath Android 应用推送的 RTSP 视频流。本方案采用最新的流媒体处理技术和依赖管理实践，推荐使用 **Python 3.12**，确保与当前 Android 项目的无缝集成，同时优化性能、可维护性和部署可靠性。

## **技术栈**

* **Python 版本**: **Python 3.12** (兼顾性能、稳定性和 Debian 12 系统兼容性)  
* **后端框架**：FastAPI (异步高性能 Python Web 框架)  
* **流媒体处理**：GStreamer (推荐使用 Debian Bookworm 系统自带版本 1.22.0 以简化部署)  
* **视频处理**：OpenCV (通过 pip 安装)  
* **数据验证**: Pydantic V2 (高性能数据验证与序列化)  
* **依赖管理**: **PDM** (配合 **uv** 加速) 使用 pyproject.toml 和 pdm.lock  
* **容器化**：Docker & Docker Compose (部署与扩展)

## **与 Android 客户端的兼容性**

本方案专门针对 SafePath Android 应用的 RTSP 推流进行了优化：

* 默认监听端口配置为 554，与 Android 客户端的 RTSP\_SERVER\_URL 完全匹配  
* 支持 Android 客户端使用的 H.264 编码格式  
* 实现与 RtspCamera2 类兼容的服务端接收机制 (基于 GStreamer 1.22)  
* 处理 Android 客户端的重连逻辑

## **系统架构**

SafePath Android 客户端        GStreamer (1.22) \+ FastAPI 服务器 (Python 3.12)  
\+----------------+              \+----------------------+  
| | RTSP协议(554端口) | |  
| RtspCamera2 | \----------------\> | RTSP 接收器 |  
| (推流客户端) | | (基于GStreamer系统包) |  
\+----------------+              \+----------+-----------+  
|  
| 内部处理  
                                       v  
                               \+----------------------+  
| |  
| 视频处理模块 |  
| (GStreamer \+ OpenCV) |  
                               \+----------+-----------+  
|  
| REST API (Pydantic V2)  
                                       v  
                               \+----------------------+  
| FastAPI 接口 |  
| /status /snapshot 等 |  
                               \+----------------------+

## **功能需求**

1. **RTSP 流接收**  
   * 接收来自 Android 应用的 RTSP 流 (端口 554，路径 /live)  
   * 确保与 Android 端 RTSP\_SERVER\_URL 格式完全兼容  
   * 支持多并发连接  
2. **视频处理**  
   * 实时视频处理，支持格式转换 (基于 GStreamer 1.22)  
   * 高性能视频帧提取与保存 (使用 OpenCV)  
3. **API 接口**  
   * 连接状态监控 API  
   * 实时截图获取 (使用 Pydantic V2 进行数据校验)  
4. **状态管理**  
   * 实时监控连接状态  
   * 自动处理重连，与 Android 端的重试机制配合  
   * 详细日志记录系统

## **架构设计原则**

在设计和开发过程中，项目遵循以下架构原则，确保代码质量和可维护性：

### **1\. 模块化原则**

* 将系统拆分为独立的模块，每个模块专注于单一功能  
* 每个模块的代码量控制在300行以内，绝不超过500行  
* 模块间通过清晰定义的接口通信，避免直接修改其他模块的内部状态

### **2\. 高内聚低耦合**

* 确保每个模块/类具有明确的职责边界  
* 最小化模块间的依赖关系  
* 采用依赖注入模式传递服务和配置 (FastAPI 内建支持)

### **3\. 分层架构**

项目采用清晰的分层架构：

* **API 层**：处理 HTTP 请求和响应 (FastAPI, Pydantic V2)  
* **服务层**：实现业务逻辑  
* **基础设施层**：包括 RTSP 服务器 (GStreamer 系统包)、视频处理 (OpenCV) 等底层功能  
* **工具层**：提供通用辅助功能

## **技术实现方案**

注意：以下代码仅供参考，实际实现需确保与 Pydantic V2 和 Python 3.12 兼容。GStreamer Pipeline 可能需要根据 GStreamer 1.22 版本进行微调。

### **1\. RTSP 服务器模块 (app/rtsp/server.py)**

负责接收和处理 RTSP 视频流 (使用系统 GStreamer 库)：

Python

\# 注意：需要确保 gi 库来自系统安装的 python3-gi (for Python 3.12)  
from gi.repository import Gst, GstRtspServer, GObject  
import os  
import logging

class RtspServer:  
    def \_\_init\_\_(self, port=554, path="/live", output\_dir="./videos"):  
        self.port \= port  
        self.path \= path  
        self.output\_dir \= output\_dir  
        self.server \= None  
        self.factory \= None  
        self.log \= logging.getLogger("RtspServer")  
        \# 确保 GObject 线程初始化在应用启动时完成 (通常在 main.py)

    def initialize(self):  
        \# 初始化 GStreamer (通常在应用启动时完成)  
        \# Gst.init(None) \# 移至 main.py 启动时

        \# 创建输出目录  
        os.makedirs(self.output\_dir, exist\_ok=True)

        \# 创建RTSP服务器  
        self.server \= GstRtspServer.RTSPServer()  
        self.server.set\_service(str(self.port))

        \# 创建媒体工厂  
        self.factory \= GstRtspServer.RTSPMediaFactory()

        \# 配置流水线 (基于 GStreamer 1.22)  
        \# 接收RTSP流，将其分流为两路：一路保存为视频文件，一路用于实时处理 (通过 appsink 或类似方式传递给 OpenCV)  
        \# 注意：以下 pipeline 仅为示例，具体元素和属性需根据 GStreamer 1.22 和实际需求调整  
        \# 可能需要使用 appsink 将帧传递给 Python/OpenCV 进行处理，而不是直接用 multifilesink  
        pipeline \= (  
            "rtspsrc name=src latency=0\! rtph264depay\! h264parse\! "  
            "tee name=t "  
            \# 分支1: 保存为 MP4 文件 (示例，可能需要调整 muxer 和 sink)  
            "t.\! queue\! mp4mux\! "  
            f"filesink location={self.output\_dir}/recent.mp4 async=false "  
            \# 分支2: 解码并传递给应用处理 (示例，使用 appsink)  
            "t.\! queue\! avdec\_h264\! videoconvert\! video/x-raw,format=BGR\! "  
            "appsink name=sink emit-signals=true max-buffers=1 drop=true"  
            \# 如果仍需保存 JPEG 帧，可以从 appsink 获取帧后用 OpenCV 保存  
        )  
        self.factory.set\_launch(pipeline)  
        self.factory.set\_shared(True) \# 允许多个客户端连接到同一流

        \# 将媒体工厂与路径绑定  
        mount\_points \= self.server.get\_mount\_points()  
        mount\_points.add\_factory(self.path, self.factory)

        \# 启动服务器 (在后台线程中)  
        self.server.attach(None) \# 使用默认主循环上下文  
        self.log.info(f"RTSP服务器配置完成，将在 rtsp://0.0.0.0:{self.port}{self.path} 监听")

        \# 连接事件回调设置 (需要连接到 GstRtspServer 的信号)  
        \# self.server.connect("client-connected", self.\_on\_client\_connected\_cb)  
        \# self.factory.connect("media-configure", self.\_on\_media\_configure\_cb) \# 获取 appsink

    \# \--- 回调函数和帧处理逻辑 \---  
    \# def \_on\_client\_connected\_cb(self, server, client):  
    \#     self.log.info(f"客户端连接: {client.get\_connection().get\_ip()}")  
    \#     if hasattr(self, '\_on\_client\_connected'):  
    \#         self.\_on\_client\_connected()  
    \#     client.connect("closed", self.\_on\_client\_disconnected\_cb)

    \# def \_on\_client\_disconnected\_cb(self, client):  
    \#     self.log.info(f"客户端断开: {client.get\_connection().get\_ip()}")  
    \#     if hasattr(self, '\_on\_client\_disconnected'):  
    \#         self.\_on\_client\_disconnected()

    \# def \_on\_media\_configure\_cb(self, factory, media):  
    \#      \# 获取 pipeline 中的 appsink 元素  
    \#      pipeline \= media.get\_element()  
    \#      appsink \= pipeline.get\_by\_name('sink')  
    \#      if appsink:  
    \#          appsink.connect("new-sample", self.\_on\_new\_sample, appsink) \# 传递 appsink 实例

    \# def \_on\_new\_sample(self, appsink, user\_data):  
    \#      \# 处理从 appsink 获取的新样本 (视频帧)  
    \#      sample \= appsink.emit("pull-sample")  
    \#      if sample:  
    \#          \# 在这里将 Gst.Sample 转换为 OpenCV Mat 对象进行处理或保存  
    \#          \#... 实现 Gst Sample 到 OpenCV Mat 的转换...  
    \#          \# 例如：buffer \= sample.get\_buffer(); caps \= sample.get\_caps();...  
    \#          \# self.latest\_frame \= converted\_cv\_mat  
    \#          \# self.save\_latest\_frame\_if\_needed(converted\_cv\_mat)  
    \#          return Gst.FlowReturn.OK  
    \#      return Gst.FlowReturn.ERROR

    def set\_connection\_callbacks(self, on\_client\_connected, on\_client\_disconnected):  
        """设置客户端连接和断开的回调函数 (通过信号连接实现)"""  
        self.\_on\_client\_connected \= on\_client\_connected  
        self.\_on\_client\_disconnected \= on\_client\_disconnected  
        \# 实际连接应在 initialize 或启动时完成

    def get\_latest\_frame\_path(self) \-\> Optional\[str\]:  
        """获取最新的视频帧图像路径 (需要修改为从内存或临时文件获取)"""  
        \# 注意：原 multifilesink 方式已更改为 appsink  
        \# 需要实现从 appsink 获取帧并保存为临时文件或直接从内存返回  
        \# 以下为示例逻辑，需要替换  
        try:  
            \# 假设有一个机制将最新帧保存到特定文件 snapshot.jpg  
            latest\_frame\_file \= os.path.join(self.output\_dir, "snapshot.jpg")  
            if os.path.exists(latest\_frame\_file):  
                 return latest\_frame\_file  
            else:  
                 \# 或者查找最近的 jpg 文件 (如果采用其他保存策略)  
                 jpg\_files \= sorted(\[f for f in os.listdir(self.output\_dir) if f.endswith('.jpg')\])  
                 if jpg\_files:  
                     return os.path.join(self.output\_dir, jpg\_files\[-1\])  
                 return None  
        except Exception as e:  
            self.log.error(f"获取最新帧失败: {e}")  
            return None

### **2\. 视频处理服务 (app/services/video\_service.py)**

负责视频文件管理（主要针对录制的 MP4 文件）：

Python

import os  
import time  
import logging  
from typing import List, Optional  
from datetime import datetime

class VideoService:  
    """视频处理服务，负责视频文件管理和处理"""

    def \_\_init\_\_(self, output\_dir: str, max\_storage\_days: int \= 7):  
        """初始化视频服务

        Args:  
            output\_dir: 视频文件存储目录  
            max\_storage\_days: 视频文件保留最大天数  
        """  
        self.output\_dir \= output\_dir  
        self.max\_storage\_days \= max\_storage\_days  
        self.logger \= logging.getLogger("video\_service")

        \# 确保输出目录存在  
        os.makedirs(self.output\_dir, exist\_ok=True)

    def cleanup\_old\_videos(self) \-\> int:  
        """清理超过保留期限的视频文件 (主要针对.mp4)

        Returns:  
            int: 已清理的文件数量  
        """  
        cleaned\_count \= 0  
        try:  
            current\_time \= time.time()  
            max\_age \= self.max\_storage\_days \* 86400  \# 转换为秒

            for filename in os.listdir(self.output\_dir):  
                \# 主要清理录制的 mp4 文件  
                if filename.endswith('.mp4'):  
                    file\_path \= os.path.join(self.output\_dir, filename)  
                    \# 检查是否为文件且超过了最大存储时间  
                    if os.path.isfile(file\_path) and (current\_time \- os.path.getmtime(file\_path)) \> max\_age:  
                        os.remove(file\_path)  
                        cleaned\_count \+= 1  
                        self.logger.info(f"已清理旧 MP4 文件: {filename}")  
        except Exception as e:  
            self.logger.error(f"清理旧视频文件失败: {e}")

        return cleaned\_count

    def get\_video\_list(self) \-\> List\[str\]:  
        """获取可用的视频文件列表 (仅 MP4)

        Returns:  
            List\[str\]: 视频文件名列表  
        """  
        try:  
            return \[f for f in os.listdir(self.output\_dir) if f.endswith('.mp4')\]  
        except Exception as e:  
            self.logger.error(f"获取视频列表失败: {e}")  
            return

    def get\_video\_path(self, filename: str) \-\> Optional\[str\]:  
        """获取指定视频文件的完整路径

        Args:  
            filename: 视频文件名

        Returns:  
            Optional\[str\]: 视频文件的完整路径，如果文件不存在则返回None  
        """  
        video\_path \= os.path.join(self.output\_dir, filename)  
        return video\_path if os.path.exists(video\_path) and filename.endswith('.mp4') else None

    \# 可以增加处理从 appsink 获取的帧的函数  
    \# def process\_frame(self, frame\_data):  
    \#     \# 使用 OpenCV 处理帧，例如保存快照  
    \#     pass

### **3\. API 路由模块 (app/api/routes.py)**

负责定义和处理 API 请求 (使用 Pydantic V2 模型)：

Python

from fastapi import APIRouter, HTTPException, Depends, Response  
from fastapi.responses import FileResponse  
import base64  
from datetime import datetime  
from typing import Dict, List, Optional  
from pydantic import BaseModel, Field \# 导入 Pydantic V2

from..services.video\_service import VideoService  
from..rtsp.server import RtspServer  
from..core.config import get\_settings

router \= APIRouter()

\# 使用 Pydantic V2 定义响应模型  
class ServerStatus(BaseModel):  
    is\_running: bool  
    start\_time: Optional\[datetime\] \= None  
    connections: int \= 0  
    last\_frame\_time: Optional\[datetime\] \= None  
    server\_ip: Optional\[str\] \= None

class StatusResponse(BaseModel):  
    status: ServerStatus  
    rtsp\_url: str

class SnapshotResponse(BaseModel):  
    image\_base64: str

class VideoListResponse(BaseModel):  
    videos: List\[str\]

class HealthResponse(BaseModel):  
    status: str \= "ok"

\# 状态信息 (应考虑使用更健壮的状态管理机制，例如类或依赖注入)  
server\_status\_data \= {  
    "is\_running": False,  
    "start\_time": None,  
    "connections": 0,  
    "last\_frame\_time": None,  
    "server\_ip": None  
}

\# 依赖注入函数 (假设在 main.py 或其他地方定义和实例化)  
def get\_rtsp\_server() \-\> RtspServer:  
    \# Placeholder: 实际应返回全局或请求作用域的 RtspServer 实例  
    from..main import rtsp\_server \# 示例：从 main 导入  
    return rtsp\_server

def get\_video\_service() \-\> VideoService:  
    \# Placeholder: 实际应返回全局或请求作用域的 VideoService 实例  
    from..main import video\_service \# 示例：从 main 导入  
    return video\_service

@router.get("/status", response\_model=StatusResponse)  
async def get\_status() \-\> StatusResponse:  
    """获取RTSP服务器状态"""  
    settings \= get\_settings()  
    status \= ServerStatus(\*\*server\_status\_data) \# 使用 Pydantic 模型验证/转换  
    rtsp\_url \= f"rtsp://{status.server\_ip or 'localhost'}:{settings.RTSP\_PORT}{settings.RTSP\_PATH}"  
    return StatusResponse(status=status, rtsp\_url=rtsp\_url)

@router.get("/snapshot")  
async def get\_snapshot(  
    as\_file: bool \= False,  
    rtsp\_server: RtspServer \= Depends(get\_rtsp\_server)  
) \-\> Response: \# 返回通用 Response 以支持 FileResponse 或 JSON  
    """获取当前视频帧截图"""  
    if not server\_status\_data\["is\_running"\]:  
        raise HTTPException(status\_code=503, detail="RTSP服务未运行")

    frame\_path \= rtsp\_server.get\_latest\_frame\_path()  
    if not frame\_path or not os.path.exists(frame\_path):  
        raise HTTPException(status\_code=404, detail="没有可用的视频帧")

    \# 更新最后帧时间 (注意线程安全，如果状态被多线程访问)  
    server\_status\_data\["last\_frame\_time"\] \= datetime.now()

    if as\_file:  
        return FileResponse(frame\_path, media\_type="image/jpeg", filename="snapshot.jpg")  
    else:  
        try:  
            with open(frame\_path, "rb") as image\_file:  
                encoded\_string \= base64.b64encode(image\_file.read()).decode()  
            \# 返回符合 Pydantic V2 模型的 JSON 响应  
            return SnapshotResponse(image\_base64=encoded\_string)  
        except Exception as e:  
             logging.getLogger("api").error(f"读取或编码快照失败: {e}")  
             raise HTTPException(status\_code=500, detail="无法处理快照图像")

@router.get("/videos", response\_model=VideoListResponse)  
async def list\_videos(  
    video\_service: VideoService \= Depends(get\_video\_service)  
) \-\> VideoListResponse:  
    """获取可用的视频片段列表 (MP4)"""  
    return VideoListResponse(videos=video\_service.get\_video\_list())

@router.get("/video/{filename}")  
async def get\_video(  
    filename: str,  
    video\_service: VideoService \= Depends(get\_video\_service)  
) \-\> FileResponse:  
    """获取特定的视频片段文件 (MP4)"""  
    video\_path \= video\_service.get\_video\_path(filename)  
    if not video\_path:  
        raise HTTPException(status\_code=404, detail="视频文件不存在或非 MP4 文件")

    return FileResponse(  
        video\_path,  
        media\_type="video/mp4",  
        filename=filename  
    )

@router.get("/health", response\_model=HealthResponse)  
async def health\_check() \-\> HealthResponse:  
    """健康检查，用于监控和负载均衡"""  
    return HealthResponse(status="ok")

\# \--- 辅助函数更新状态 (需要考虑线程安全) \---  
def update\_server\_status(key: str, value: any):  
    \# 注意：直接修改全局字典在多线程/多进程环境下不安全  
    \# 应使用线程安全的结构或状态管理模式  
    server\_status\_data\[key\] \= value

def increment\_connection\_count():  
    \# 同上，需要线程安全  
    server\_status\_data\["connections"\] \+= 1  
    logging.getLogger("api").info(f"当前连接数: {server\_status\_data\['connections'\]}")

def decrement\_connection\_count():  
    \# 同上，需要线程安全  
    server\_status\_data\["connections"\] \-= 1  
    logging.getLogger("api").info(f"当前连接数: {server\_status\_data\['connections'\]}")

### **4\. 主应用模块 (app/main.py)**

整合所有组件并启动应用：

Python

from fastapi import FastAPI  
from fastapi.middleware.cors import CORSMiddleware  
import threading  
import socket  
from datetime import datetime  
import logging  
import asyncio  
import signal

\# 导入 GObject 和 GStreamer (确保来自系统安装)  
from gi.repository import GObject, Gst

from.api.routes import router as api\_router, update\_server\_status, increment\_connection\_count, decrement\_connection\_count  
from.rtsp.server import RtspServer  
from.services.video\_service import VideoService  
from.core.config import get\_settings  
from.core.logger import setup\_logging

\# 配置日志  
logger \= setup\_logging()

\# 初始化 GStreamer 和 GObject 线程  
GObject.threads\_init()  
Gst.init(None)

app \= FastAPI(title="SafePath RTSP Receiver (Optimized)")

\# 导入设置  
settings \= get\_settings()

\# 启用CORS  
app.add\_middleware(  
    CORSMiddleware,  
    allow\_origins=\["\*"\], \# 生产环境应配置具体来源  
    allow\_credentials=True,  
    allow\_methods=\["\*"\],  
    allow\_headers=\["\*"\],  
)

\# 注册API路由  
app.include\_router(api\_router)

\# 实例化服务 (全局实例，注意线程安全和状态管理)  
rtsp\_server \= RtspServer(  
    port=settings.RTSP\_PORT,  
    path=settings.RTSP\_PATH,  
    output\_dir=settings.OUTPUT\_DIR  
)

video\_service \= VideoService(  
    output\_dir=settings.OUTPUT\_DIR,  
    max\_storage\_days=settings.MAX\_VIDEO\_STORAGE\_DAYS  
)

\# GObject 主循环  
mainloop \= GObject.MainLoop()

\# 获取服务器IP地址  
def get\_server\_ip():  
    try:  
        \# 尝试连接到一个外部地址来获取本机用于外网通信的 IP  
        s \= socket.socket(socket.AF\_INET, socket.SOCK\_DGRAM)  
        s.connect(("8.8.8.8", 80)) \# 连接 Google DNS (不会实际发送数据)  
        ip\_address \= s.getsockname()  
        s.close()  
        return ip\_address  
    except Exception as e:  
        logger.warning(f"无法自动检测外部 IP 地址: {e}. 回退到 hostname.")  
        try:  
            \# 回退到获取主机名对应的 IP (可能只是内网 IP)  
            hostname \= socket.gethostname()  
            ip\_address \= socket.gethostbyname(hostname)  
            return ip\_address  
        except Exception as e\_inner:  
            logger.error(f"获取服务器 IP 地址失败: {e\_inner}")  
            return "0.0.0.0" \# 返回默认值

\# 启动 RTSP 服务器的后台任务 (运行 GObject MainLoop)  
def run\_rtsp\_server\_loop():  
    try:  
        rtsp\_server.initialize()  
        \# 设置连接回调 (需要确保 RtspServer 内部正确连接了信号)  
        rtsp\_server.set\_connection\_callbacks(  
            on\_client\_connected=increment\_connection\_count,  
            on\_client\_disconnected=decrement\_connection\_count  
        )  
        update\_server\_status("is\_running", True)  
        update\_server\_status("start\_time", datetime.now())  
        update\_server\_status("server\_ip", get\_server\_ip())  
        logger.info("RTSP 服务器初始化完成，启动 GObject 主循环...")  
        mainloop.run() \# 阻塞直到 mainloop.quit() 被调用  
    except Exception as e:  
        logger.error(f"启动或运行 RTSP 服务器 GObject 主循环失败: {e}", exc\_info=True)  
        update\_server\_status("is\_running", False)  
    finally:  
        logger.info("GObject 主循环已退出。")

\# 定期执行的后台任务 (使用 asyncio)  
async def periodic\_tasks():  
    while True:  
        try:  
            logger.info("开始执行定期清理任务...")  
            \# 在异步任务中运行同步阻塞代码  
            files\_cleaned \= await asyncio.to\_thread(video\_service.cleanup\_old\_videos)  
            logger.info(f"清理了 {files\_cleaned} 个过期视频文件")  
        except Exception as e:  
            logger.error(f"定期清理任务失败: {e}", exc\_info=True)  
        \# 每天执行一次清理 (86400 秒)  
        await asyncio.sleep(86400)

\# 优雅关闭处理  
async def shutdown\_event():  
    logger.info("收到关闭信号，开始优雅关闭...")  
    if mainloop.is\_running():  
        logger.info("正在停止 GObject 主循环...")  
        mainloop.quit()  
    \# 等待 RTSP 服务器线程结束 (如果需要)  
    if rtsp\_thread and rtsp\_thread.is\_alive():  
         logger.info("等待 RTSP 服务器线程退出...")  
         rtsp\_thread.join(timeout=5) \# 等待最多 5 秒  
         if rtsp\_thread.is\_alive():  
              logger.warning("RTSP 服务器线程未在超时内退出。")  
    \# 取消定期任务  
    if periodic\_task:  
        logger.info("正在取消定期任务...")  
        periodic\_task.cancel()  
        try:  
            await periodic\_task  
        except asyncio.CancelledError:  
            logger.info("定期任务已取消。")  
    logger.info("关闭完成。")

rtsp\_thread \= None  
periodic\_task \= None

@app.on\_event("startup")  
async def startup\_event():  
    global rtsp\_thread, periodic\_task  
    logger.info("应用启动，正在初始化...")

    \# 在单独线程中启动 GObject 主循环以运行 RTSP 服务器  
    rtsp\_thread \= threading.Thread(target=run\_rtsp\_server\_loop, daemon=True)  
    rtsp\_thread.start()

    \# 启动定期任务  
    periodic\_task \= asyncio.create\_task(periodic\_tasks())

    logger.info("应用启动完成。")

@app.on\_event("shutdown")  
async def shutdown\_app():  
    await shutdown\_event()

\# 添加信号处理以支持优雅关闭 (uvicorn 会处理 SIGINT/SIGTERM)  
\# 但如果直接运行 Python 脚本，可能需要手动添加  
\# signal.signal(signal.SIGINT, lambda s, f: asyncio.create\_task(shutdown\_event()))  
\# signal.signal(signal.SIGTERM, lambda s, f: asyncio.create\_task(shutdown\_event()))

\# \--- 服务注入函数 (用于 FastAPI Depends) \---  
\# 这些函数现在可以直接返回全局实例  
\# 注意：如果未来需要更复杂的依赖管理（如请求作用域），则需要调整  
def get\_rtsp\_server\_instance() \-\> RtspServer:  
    return rtsp\_server

def get\_video\_service\_instance() \-\> VideoService:  
    return video\_service

\# 更新 API 路由中的依赖项以使用这些新函数名  
\# (在 routes.py 中: Depends(get\_rtsp\_server\_instance), Depends(get\_video\_service\_instance))

## **优化的项目目录结构 (使用 PDM)**

src/  
├── app/                      \# 应用程序主目录  
│   ├── \_\_init\_\_.py  
│   ├── main.py               \# 主应用入口 (FastAPI app)  
│   ├── api/                  \# API层  
│   │   ├── \_\_init\_\_.py  
│   │   ├── routes.py         \# API路由定义  
│   │   └── models.py         \# Pydantic V2 API数据模型 (可选, 可放在 routes.py 或单独文件)  
│   ├── core/                 \# 核心配置  
│   │   ├── \_\_init\_\_.py  
│   │   ├── config.py         \# 应用配置 (Pydantic Settings)  
│   │   └── logger.py         \# 日志配置  
│   ├── rtsp/                 \# RTSP相关模块  
│   │   ├── \_\_init\_\_.py  
│   │   └── server.py         \# RTSP服务器核心 (使用系统 GStreamer)  
│   ├── services/             \# 服务层  
│   │   ├── \_\_init\_\_.py  
│   │   └── video\_service.py  \# 视频处理服务  
│   └── utils/                \# 工具函数 (可选)  
│       ├── \_\_init\_\_.py  
│       └── helpers.py        \# 辅助函数  
├── videos/                   \# 视频存储目录 (运行时创建)  
├── tests/                    \# 测试代码  
│   ├── \_\_init\_\_.py  
│   ├── test\_api.py           \# API测试  
│   └── test\_video\_service.py \# 视频服务测试  
├── docker/                   \# Docker相关  
│   ├── Dockerfile            \# 优化后的 Dockerfile  
│   └── docker-compose.yml    \# Docker Compose 配置  
├──.github/                  \# GitHub 相关配置 (可选)  
│   └── workflows/            \# CI/CD 工作流 (可选)  
├── pyproject.toml            \# PDM 配置文件 (替代 requirements.txt)  
├── pdm.lock                  \# PDM 锁文件 (确保依赖一致性)  
└── README.md                 \# 项目说明 (包含系统依赖列表)

## **部署方案**

项目使用 Docker 进行容器化部署，确保环境一致性和简化部署流程。依赖管理使用 PDM。

### **pyproject.toml (示例)**

Ini, TOML

\[project\]  
name \= "rtsp-receiver-service"  
version \= "0.1.0"  
description \= "RTSP Video Stream Receiver Service using FastAPI and GStreamer"  
authors \= \[  
    {name \= "Your Name", email \= "your.email@example.com"},  
\]  
dependencies \= \[  
    "fastapi\[standard\]\>=0.115.0,\<0.116.0", \# 包含 uvicorn, pydantic 等  
    "uvicorn\[standard\]\>=0.34.0,\<0.35.0",   \# 明确指定以获取标准性能库  
    "pydantic\>=2.11.0,\<3.0.0",  
    "opencv-python\>=4.11.0,\<4.12.0",      \# 或 opencv-python-headless  
    "python-dotenv\>=1.0.0",  
    \# PyGObject 和 GStreamer 通过系统包安装，不在此列出  
\]  
requires-python \= "\>=3.12,\<3.13" \# 明确指定 Python 3.12

\[project.optional-dependencies\]  
dev \= \[  
    "pytest\>=7.0.0",  
    "httpx\>=0.25.0", \# 用于异步 API 测试  
\]

\[build-system\]  
requires \= \["pdm-backend"\]  
build-backend \= "pdm.backend"

\[tool.pdm\]  
\# PDM 配置，例如使用 uv  
\[tool.pdm.tool-options\]  
use\_uv \= true

\[tool.pdm.dev-dependencies\]  
\# 开发依赖也可以放在这里  
dev \= \[  
    "pytest\>=7.0.0",  
    "httpx\>=0.25.0",  
\]

### **Docker Compose 配置 (docker/docker-compose.yml)**

YAML

version: '3.8' \# 使用较新版本

services:  
  rtsp-server:  
    build:  
      context:..  
      dockerfile: docker/Dockerfile  
    ports:  
      \- "8000:8000"   \# FastAPI API端口  
      \- "554:554/tcp" \# RTSP TCP 端口  
      \# RTSP 可能还需要 UDP 端口，范围取决于 GStreamer 配置  
      \# \- "5000-5010:5000-5010/udp" \# 示例 UDP 端口范围  
    volumes:  
      \-../videos:/app/videos \# 挂载视频存储目录  
    restart: unless-stopped  
    environment:  
      \# 从.env 文件或直接设置环境变量  
      \- RTSP\_PORT=554  
      \- RTSP\_PATH=/live  
      \- OUTPUT\_DIR=/app/videos  
      \- MAX\_VIDEO\_STORAGE\_DAYS=7  
      \- LOG\_LEVEL=info  
      \# GStreamer 相关环境变量 (可选)  
      \# \- GST\_DEBUG=2  
    healthcheck:  
      test: \["CMD", "curl", "-f", "http://localhost:8000/health"\]  
      interval: 30s  
      timeout: 10s  
      retries: 3  
      start\_period: 30s \# 给应用启动留出时间

### **Dockerfile (docker/Dockerfile)**

Dockerfile

\# 使用与 Debian Bookworm 匹配的 Python 3.12 基础镜像  
FROM python:3.12\-slim-bookworm

WORKDIR /app

\# 设置推荐的 PDM 版本和 pipx (用于安装 PDM)  
ENV PDM\_VERSION=2.15.4 \\  
    PIPX\_HOME=/opt/pipx \\  
    PIPX\_BIN\_DIR=/usr/local/bin  
ENV PATH="${PATH}:${PIPX\_BIN\_DIR}"

\# 安装 pipx 和 PDM  
RUN apt-get update && apt-get install \-y \--no-install-recommends \\  
    pipx \\  
    git \\  
    && pipx install pdm==${PDM\_VERSION} \\  
    && apt-get purge \-y \--auto-remove \\  
    && rm \-rf /var/lib/apt/lists/\*

\# 安装系统依赖 (基于 Debian Bookworm 的 GStreamer 1.22)  
\# 包含核心库、插件、RTSP 服务器、Python 绑定和 GI 数据  
RUN apt-get update && apt-get install \-y \--no-install-recommends \\  
    \# GStreamer 核心和插件  
    gstreamer1.0\-tools \\  
    gstreamer1.0\-plugins-base \\  
    gstreamer1.0\-plugins-good \\  
    gstreamer1.0\-plugins-bad \\  
    gstreamer1.0\-plugins-ugly \\  
    gstreamer1.0\-libav \\  
    \# RTSP 服务器  
    gstreamer1.0\-rtsp \\  
    libgstrtspserver-1.0\-0 \\  
    \# Python 绑定和 GObject Introspection 数据  
    python3-gi \\  
    gir1.2\-glib-2.0 \\  
    gir1.2\-gobject-2.0 \\  
    gir1.2\-gst-plugins-base-1.0 \\  
    gir1.2\-gstreamer-1.0 \\  
    \# OpenCV 运行时依赖 (部分可能已包含)  
    libglib2.0\-0 \\  
    libsm6 \\  
    libxext6 \\  
    libxrender1 \\  
    \# 其他工具  
    curl \\  
    \# 清理  
    && apt-get clean \\  
    && rm \-rf /var/lib/apt/lists/\*

\# 设置 Python 环境变量  
ENV PYTHONUNBUFFERED=1 \\  
    \# PYTHONPATH 可能不需要，PDM 会处理虚拟环境  
    \# PYTHONPATH=/app  
    \# GStreamer 调试级别 (可选)  
    GST\_DEBUG=2

\# 复制 PDM 配置文件  
COPY pyproject.toml pdm.lock./

\# 安装项目依赖 (使用 PDM 和 uv)  
\# \--prod 表示只安装生产依赖  
\# \--no-editable 表示不以可编辑模式安装  
RUN pdm install \--prod \--no-editable

\# 创建视频存储目录并设置权限  
RUN mkdir \-p /app/videos && chmod 777 /app/videos

\# 复制应用代码  
\# 注意：如果项目结构是 src/app，需要调整 COPY 命令  
\# 假设代码在 src/ 目录下  
COPY./src/app /app/app  
\# 如果 main.py 在 src/ 下，则 COPY./src /app

\# 暴露 FastAPI 端口  
EXPOSE 8000  
\# 暴露 RTSP 端口 (TCP)  
EXPOSE 554

\# 启动命令 (使用 uvicorn 运行 FastAPI 应用)  
\# 注意：如果 main.py 在 app/ 目录下，则为 app.main:app  
CMD \["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"\]

## **与 Android 客户端的兼容细节**

为确保与 SafePath Android 客户端的无缝兼容，我们进行了以下特定设计：

1. **URL 格式匹配**：  
   * 服务器监听端口 554（标准 RTSP 端口）  
   * 路径设置为 "/live"，与 Android 端的 RTSP\_SERVER\_URL 相匹配  
2. **错误处理协调**：  
   * 服务器能够识别和响应 Android 客户端的连接尝试  
   * 支持客户端的重试机制，在连接中断后可快速重建连接  
3. **编码兼容性**：  
   * GStreamer 配置支持 H.264 视频编码，与 Android 客户端默认使用的编码格式兼容  
   * 处理 RTP 封包，正确解析 Android 推流的数据 (由 GStreamer 处理)  
4. **状态监控**：  
   * 提供 /status API，可用于向 Android 客户端反馈连接情况  
   * 提供 /health 健康检查端点，便于监控服务是否正常运行

## **性能与资源优化**

1. **流媒体处理优化**：  
   * 使用 GStreamer (系统优化版本 1.22) 进行流处理。  
   * Pipeline 设计考虑使用 appsink 高效传递帧到应用层进行处理。  
2. **资源管理**：  
   * 自动清理旧的视频文件 (.mp4)，防止磁盘空间耗尽。  
   * 使用 Python 3.12 和 Pydantic V2 获得更好的内存和 CPU 效率。  
   * 容器化部署限制资源使用。  
3. **高并发支持**：  
   * FastAPI 和 Uvicorn 提供异步处理能力，支持多客户端同时连接。  
   * GStreamer RTSPMediaFactory 设置为 shared=True 以支持多客户端访问同一流。

## **验收标准**

1. 服务器能成功接收 SafePath Android 应用的 RTSP 流 (H.264)。  
2. 在 Android 客户端设置 RTSP\_SERVER\_URL 后，可一键连接成功。  
3. 连接断开后，能配合 Android 客户端的重试机制自动重连。  
4. API 接口 (/status, /snapshot) 响应时间小于 100ms (在合理负载下)。  
5. 支持至少 10 个并发 RTSP 连接 (需进行压力测试验证)。  
6. 视频帧处理延迟（从接收到 API 可获取快照）小于 500ms (需测试验证)。

## **开发与测试计划**

1. **阶段一**：环境与基础框架搭建  
   * 配置 PDM 和 Python 3.12 开发环境。  
   * 搭建 Docker 环境，安装系统 GStreamer 1.22 和 Python 绑定。  
   * 实现基础 GStreamer RTSP 服务器逻辑 (使用 appsink)。  
   * 与 Android 客户端进行初步连接和流接收测试。  
2. **阶段二**：API 与核心功能实现  
   * 开发 FastAPI 接口 (使用 Pydantic V2 模型)。  
   * 实现从 appsink 获取视频帧并使用 OpenCV 处理/保存快照的逻辑。  
   * 实现 MP4 文件录制和管理 (VideoService)。  
3. **阶段三**：集成与测试  
   * 实现状态监控和连接回调逻辑。  
   * 编写单元测试和集成测试 (使用 pytest 和 httpx)。  
   * 与 Android 客户端进行完整流程测试，包括重连。  
4. **阶段四**：优化与部署  
   * 性能调优 (GStreamer pipeline, 异步代码)。  
   * 完善 Dockerfile 和 Docker Compose 配置。  
   * 部署到测试/生产环境，添加日志和监控。

## **未来扩展方向**

1. **视频分析功能**：  
   * 在 appsink 的回调中使用 OpenCV 或其他 AI 库进行实时分析 (物体识别、动作检测等)。  
2. **云存储集成**：  
   * 将录制的 MP4 文件或关键帧自动上传到云存储服务 (S3, Google Cloud Storage 等)。  
3. **多路 RTSP 支持**：  
   * 扩展 RTSP 服务器以支持动态创建或管理多个不同的 RTSP 流路径。  
4. **WebRTC 直播**：  
   * 添加 WebRTC 支持，允许浏览器直接低延迟观看直播流。  
5. **管理界面**：  
   * 开发一个简单的 Web UI 用于查看状态、管理录制的视频等。

## **总结**

本方案采纳了 **Python 3.12**、**Pydantic V2** 和 **PDM** 等现代化工具和实践，旨在提升 RTSP 视频流接收服务器的性能、可维护性和部署可靠性。通过推荐使用 Debian Bookworm 系统自带的 **GStreamer 1.22** 版本，简化了复杂系统依赖的管理。方案强调了**容器化 (Docker)** 的重要性，并提供了更新的 pyproject.toml、Dockerfile 和 docker-compose.yml 配置示例。代码示例也相应调整以反映推荐的技术栈和设计模式（如使用 appsink）。该方案在满足核心需求的同时，为未来的功能扩展奠定了坚实的基础。