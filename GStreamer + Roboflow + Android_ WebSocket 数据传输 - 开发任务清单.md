# GStreamer + Roboflow + Android: WebSocket 数据传输 - 开发任务清单

## I. 项目设置与配置回顾

- [ ] 1.1. 确认 Android RTSP 推流细节：H.264 编码，640x480 分辨率，无音频。
- [ ] 1.2. 审阅 Python GStreamer 管道配置，用于接收 RTSP 流并转换为 BGR 格式。
    - GStreamer 管道参考: `rtspsrc location=<RTSP_URL> ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR ! appsink name=push_appsink emit-signals=true drop=true max-buffers=1 sync=false`
    - 如果 Roboflow `InferencePipeline` 从虚拟摄像头设备读取，考虑备选方案: `... ! v4l2sink device=/dev/videoX`
- [ ] 1.3. Roboflow `InferencePipeline` 设置确认：
    - 输入源：来自 GStreamer 的 BGR 格式视频帧 (通过 `appsink` 回调获取 或 `v4l2loopback` 虚拟设备)。
    - 输出：JSON 格式的结构化检测结果。
- [ ] 1.4. 定义 WebSocket 传输的 JSON 数据结构 (包含检测信息、帧ID、时间戳等)。
    ```json
    {
      "frame_id": "integer", 
      "timestamp": "integer", 
      "detections": [
        {
          "class": "string",
          "confidence": "float",
          "x_center": "float",
          "y_center": "float",
          "width": "float",
          "height": "float"
        }
      ]
    }
    ```
- [ ] 1.5. 性能目标：推理和数据传输达到 2-10 FPS。

## II. Python 服务器端实现

- [ ] 2.1. GStreamer 视频帧捕获：
    - [ ] 2.1.1. (如果使用 appsink) 实现 `appsink` 的 `new-sample` 信号回调函数，从中获取 `Gst.Buffer`。
    - [ ] 2.1.2. (如果使用 appsink) 将 `Gst.Buffer` 中的数据转换为 NumPy BGR 数组。
    - [ ] 2.1.3. (如果使用 v4l2loopback) 确保服务器已安装 `v4l2loopback-dkms` 并成功加载内核模块 (例如，创建 `/dev/videoX` 设备)。
- [ ] 2.2. Roboflow `InferencePipeline` 集成：
    - [ ] 2.2.1. 使用模型 ID 和 API 密钥初始化 `InferencePipeline`。
    - [ ] 2.2.2. (如果使用 appsink) 编程方式将 NumPy 帧数据送入 `InferencePipeline` 进行处理。
    - [ ] 2.2.3. (如果使用 v4l2loopback) 设置 `InferencePipeline` 的 `video_reference` 参数为对应的虚拟摄像头设备路径 (例如 `/dev/videoX`)。
    - [ ] 2.2.4. 实现 `on_prediction` 回调函数：
        - 从回调参数中提取检测结果 (类别、置信度、边界框等)。
        - 将提取的数据格式化为预定义的 JSON 结构。
- [ ] 2.3. WebSocket 服务器实现：
    - [ ] 2.3.1. 选择并集成 Python WebSocket 服务器库 (例如 `websockets` 库)。
    - [ ] 2.3.2. 实现 WebSocket 服务器逻辑，用于管理客户端连接 (连接、断开、多客户端广播)。
    - [ ] 2.3.3. 在 `on_prediction` 回调函数中，将格式化后的 JSON 数据通过 WebSocket 推送给所有已连接的 Android 客户端。
    - [ ] 2.3.4. 实现基本的 WebSocket 通信错误处理机制。

## III. Android App 端实现

- [ ] 3.1. RTSP 推流功能 (审阅现有实现)：
    - 确保 Android 应用能稳定地将 H.264 编码的 640x480 视频流推送到 Python 服务器的 RTSP 接收端点。
- [ ] 3.2. WebSocket 客户端实现：
    - [ ] 3.2.1. 集成 Android WebSocket 客户端库 (例如 OkHttp 内置的 WebSocket 支持)。
    - [ ] 3.2.2. 实现连接到 Python WebSocket 服务器的逻辑。
    - [ ] 3.2.3. 实现 `onMessage` 回调，用于接收服务器推送的 JSON 数据字符串。
    - [ ] 3.2.4. 解析接收到的 JSON 字符串，并将其转换为结构化数据对象。
    - [ ] 3.2.5. 在 Android UI 上展示检测结果 (例如，在视频预览上叠加边界框和标签)。
    - [ ] 3.2.6. 实现 WebSocket 连接管理和错误处理 (例如，断线自动重连机制)。

## IV. 系统集成与测试

- [ ] 4.1. 测试 GStreamer 到 Roboflow `InferencePipeline` 的视频帧流转是否通畅。
- [ ] 4.2. 测试 Roboflow 推理功能及 `on_prediction` 回调输出的 JSON 数据是否正确。
- [ ] 4.3. 测试 Python WebSocket 服务器能否正确发送 JSON 数据。
- [ ] 4.4. 测试 Android WebSocket 客户端能否正确接收并解析 JSON 数据。
- [ ] 4.5. 进行端到端测试：从 Android App RTSP 推流开始，到服务器处理，最终在 Android App UI 上展示检测结果。
- [ ] 4.6. 验证系统性能是否达到 2-10 FPS 的目标。

