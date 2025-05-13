# AI 识别模块开发方案

## 1. 目标

将 Gstreamer RTSP 服务器接收到的视频流接入 Roboflow `inference` 库进行实时盲道识别分析，并将分析结果（如 JSON 格式）返回给客户端 (Android app)。

## 2. 技术选型

-   **RTSP 服务器:** 现有的基于 Python Gstreamer 的服务器 (位于 `src/app/rtsp/server.py`)，它将提供 RTSP 流。
-   **AI 模型:** Roboflow `next-level-i0lpn/3` (盲道识别)。
-   **AI 推理库:** `roboflow-inference` Python 库，特别是其 `InferencePipeline` 组件，用于直接处理 RTSP 流并进行 CPU 推理。
-   **API 密钥:** `vQBqeX1kgPouPr8aWDd5` (需设置为环境变量 `ROBOFLOW_API_KEY` 或在代码中配置)。

## 3. 开发步骤

### 3.1. RTSP 流准备与接入

-   **RTSP 源:** 确保 `src/app/rtsp/server.py` 中的 GStreamer RTSP 服务器正在运行，并提供一个可访问的 RTSP 流 URL (例如, `rtsp://0.0.0.0:8554/push` 或 `rtsp://<server_ip>:<port>/<path>`)。
-   **`InferencePipeline` 作为消费者:** `roboflow-inference` 库的 `InferencePipeline` 将直接连接到此 RTSP URL 来获取视频帧。这简化了帧提取过程，不再需要手动在 GStreamer 管道中为 Roboflow 集成配置 `appsink` 和进行 `GstBuffer` 到 NumPy 数组的转换。

### 3.2. Roboflow `InferencePipeline` 集成

-   **Pipeline 初始化:**
    -   在服务器应用启动时（例如，在 FastAPI 的 `lifespan` 事件中或一个专门的服务初始化逻辑中），初始化 `InferencePipeline`。
    -   关键参数包括 `model_id`, `video_reference` (RTSP 流 URL), 和 `on_prediction` 回调函数。
        ```python
        # 示例:
        # from inference import InferencePipeline
        # from inference.core.interfaces.camera.entities import VideoFrame # 用于类型提示

        # ROBOFLOW_API_KEY 应该通过环境变量或应用配置设置
        # import os
        # os.environ["ROBOFLOW_API_KEY"] = "vQBqeX1kgPouPr8aWDd5"

        # TARGET_CLASS_NAME = "tactile_paving" # 示例：从配置加载
        # CONFIDENCE_THRESHOLD = 0.7           # 示例：从配置加载

        # def custom_on_prediction(predictions: dict, video_frame: VideoFrame) -> None:
        #     # 在此处理预测结果 (详见 3.3)
        #     # print(f"Frame ID: {video_frame.frame_id}, Timestamp: {video_frame.frame_timestamp}")
        #     # print("Predictions:", predictions)
        #     # for detection in predictions.get("predictions", []):
        #     #     if detection.get("class") == TARGET_CLASS_NAME and detection.get("confidence", 0) > CONFIDENCE_THRESHOLD:
        #     #         print(f"Detected {TARGET_CLASS_NAME} with confidence {detection['confidence']}")
        #     #         # TODO: 将结果发送给客户端
        #     pass

        # pipeline = InferencePipeline.init(
        #     model_id="next-level-i0lpn/3",
        #     video_reference="rtsp://0.0.0.0:8554/push", # 使用实际的 RTSP URL
        #     on_prediction=custom_on_prediction,
        #     # api_key="YOUR_API_KEY", # 如果环境变量未设置
        #     # max_fps=10 # 可选：限制处理帧率
        # )
        ```
-   **Pipeline 控制:**
    -   使用 `pipeline.start()` 启动推理流程。
    -   使用 `pipeline.join()` (如果在一个独立的脚本/线程中运行 pipeline) 或管理其生命周期以确保其持续运行。在 FastAPI 应用中，`start()` 可能在应用启动时调用，而 `stop()` (或类似的清理) 在应用关闭时调用。

### 3.3. 预测结果处理与回传 (`on_prediction` 回调)

-   **回调函数:** `on_prediction` 函数是处理模型输出的核心。它接收 `predictions` (dict) 和 `video_frame` (VideoFrame 对象) 作为参数。
-   **`predictions` 对象结构 (针对目标检测):**
    -   通常是一个字典，包含一个名为 `"predictions"` 的键，其值为检测到的对象列表。
    -   每个检测对象是一个字典，包含：
        -   `"x"`: 边界框中心 x 坐标。
        -   `"y"`: 边界框中心 y 坐标。
        -   `"width"`: 边界框宽度。
        -   `"height"`: 边界框高度。
        -   `"confidence"`: 置信度得分 (0-1)。
        -   `"class"`: 检测到的类别名称 (例如, `"tactile_paving"`)。
        -   `"class_id"`: 类别的数字 ID。
    -   **注意:** 强烈建议在 `custom_on_prediction` 中首先打印 `predictions` 对象 (例如 `print(predictions)`) 以确认其实际结构，因为不同模型或版本可能略有差异。
-   **`video_frame` 对象:**
    -   `image`: NumPy 数组格式的视频帧图像数据。
    -   `frame_id`: 帧的唯一标识符。
    -   `frame_timestamp`: 帧被抓取时的时间戳。
-   **自定义逻辑:**
    -   在 `custom_on_prediction` 中，根据 `predictions` 提取所需信息（如盲道位置、置信度）。
    -   参考 `src/app_next_level.py` 中的后处理逻辑（如置信度阈值过滤、NMS，如果需要的话）可以在此回调中实现。初始阶段建议从简单的置信度过滤开始。
    -   将处理后的结果格式化为 JSON。
-   **数据回传机制:**
    -   **推荐:** 扩展现有的 FastAPI 应用，使用新的 HTTP (例如长轮询, Server-Sent Events) 或 WebSocket 端点。
    -   Android 应用连接到此端点以接收 AI 分析结果。

### 3.4. 异步处理与性能

-   **`InferencePipeline` 的异步性:** `InferencePipeline` 本身设计为异步处理，将视频解码、模型推理和结果分派到不同线程。
-   **FastAPI 集成:** 在 FastAPI 应用中，`InferencePipeline` 的启动和管理应以非阻塞方式进行，例如在后台任务或应用生命周期事件中处理。
-   **帧采样:** `InferencePipeline.init()` 的 `max_fps` 参数可用于限制处理帧率，以管理 CPU 负载。
-   **资源监控:** 在开发和测试过程中，请留意 CPU 和内存使用情况。

## 4. 代码结构与修改点 (预期)

-   **`src/app/rtsp/server.py`:**
    -   主要职责是运行 GStreamer RTSP 服务器，为 `InferencePipeline` 提供视频流。其内部 GStreamer 管道逻辑不需要为 Roboflow 进行特定的 `appsink` 修改。
-   **新模块 (例如 `src/app/services/ai_processor.py`):**
    -   封装 `InferencePipeline` 的初始化、启动和停止逻辑。
    -   包含 `custom_on_prediction` 回调函数的实现。
    -   管理 AI 相关的配置（模型 ID, API Key, 置信度阈值等，最好从 `config.py` 读取）。
    -   处理将检测结果发送到客户端的逻辑（例如，通过一个队列传递给 FastAPI 端点）。
-   **`src/app/main.py`:**
    -   在应用启动时初始化并启动 `ai_processor` 服务。
    -   在应用关闭时妥善停止 `ai_processor` 服务。
-   **`src/app/api/routes.py` (或新的 API 路由文件):**
    -   定义新的 API 端点 (HTTP/WebSocket) 供 Android 客户端获取 AI 分析结果。
-   **`src/app/core/config.py`:**
    -   添加 Roboflow API 密钥 (`ROBOFLOW_API_KEY`)、模型 ID (`ROBOFLOW_MODEL_ID`)、推理置信度阈值 (`ROBOFLOW_CONFIDENCE_THRESHOLD`)、目标类别名 (`ROBOFLOW_TARGET_CLASS`) 等配置。

## 5. 测试策略

-   **单元测试:**
    -   测试 `custom_on_prediction` 函数对模拟 `predictions` 数据的解析逻辑。
-   **集成测试:**
    -   启动完整的 FastAPI 应用和 GStreamer RTSP 服务器。
    -   使用测试客户端向 RTSP 服务器推流。
    -   验证 `InferencePipeline` 是否成功连接到 RTSP 流并调用 `on_prediction`。
    -   确认 `on_prediction` 正确处理结果，并通过 API 端点将数据回传。
-   **性能测试:** 评估端到端的处理延迟和资源消耗。

## 6. 待讨论/决策点

-   **结果传输的具体 API 设计:** 确定使用 HTTP 长轮询、Server-Sent Events 还是 WebSockets，并设计其消息格式。
-   **目标实时处理帧率:** 结合 `max_fps` 设置，确定理想的 AI 处理帧率。
-   **预处理/后处理的复杂性:** 初始阶段，`on_prediction` 中的后处理逻辑（如NMS）可以简化，后续根据需求迭代。
-   **错误处理和状态报告:** 如何管理和报告 `InferencePipeline` 的错误、模型加载失败、RTSP 连接问题等，并向客户端或日志报告状态。
-   **多流处理 (如果未来需要):** `InferencePipeline` 支持多视频源，但当前方案针对单流。