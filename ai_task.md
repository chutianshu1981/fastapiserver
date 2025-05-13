# AI Recognition Module Development Plan

## 1. Objective

Integrate the video stream received by the GStreamer RTSP server with the Roboflow `inference` library for real-time blind lane detection analysis, and return the analysis results (e.g., in JSON format) to the client (Android app).

## 2. Technology Stack

-   **RTSP Server:** Existing Python GStreamer-based server (located in `src/app/rtsp/server.py`), which will provide the RTSP stream.
-   **AI Model:** Roboflow `next-level-i0lpn/3` (blind lane detection).
-   **AI Inference Library:** `roboflow-inference` Python library, specifically its `InferencePipeline` component (now `StreamClient`), for directly processing the RTSP stream and performing CPU-based inference.
-   **API Key:** `vQBqeX1kgPouPr8aWDd5` (to be set as an environment variable `ROBOFLOW_API_KEY` or configured in the code).

## 3. Development Steps

### 3.1. RTSP Stream Preparation and Access

-   **RTSP Source:** Ensure the GStreamer RTSP server in `src/app/rtsp/server.py` is running and provides an accessible RTSP stream URL (e.g., `rtsp://0.0.0.0:8554/live` or `rtsp://<server_ip>:<port>/<path>`). The current implementation uses `/live` as the path.
-   **`StreamClient` as Consumer:** The `roboflow-inference` library's `StreamClient` will connect directly to this RTSP URL to fetch video frames. This simplifies the frame extraction process, eliminating the need to manually configure an `appsink` in the GStreamer pipeline for Roboflow integration and convert `GstBuffer` to NumPy arrays.

### 3.2. Roboflow `StreamClient` Integration

-   **Client Initialization:**
    -   Initialize the `StreamClient` when the server application starts (e.g., in FastAPI's `lifespan` event or dedicated service initialization logic).
    -   Key parameters include `model_id`, `stream_url` (RTSP stream URL), `api_key`, and an `on_prediction` callback function.
        ```python
        # Example (conceptual, actual implementation in ai_processor.py):
        # from roboflow_inference.inference.enterprise.stream_client.stream_client import StreamClient
        # from roboflow_inference.inference.core.entities.stream_entities import VideoFrame # For type hinting

        # ROBOFLOW_API_KEY should be set via environment variable or app config
        # import os
        # os.environ["ROBOFLOW_API_KEY"] = "vQBqeX1kgPouPr8aWDd5" # Or read from settings

        # TARGET_CLASS_NAME = "blind-lane" # Example: load from config
        # CONFIDENCE_THRESHOLD = 0.5     # Example: load from config

        # def custom_on_prediction_sync(inference_result: VideoFrame, watchdog) -> None:
        #     # Process prediction results here (see 3.3)
        #     # This callback is executed by the StreamClient's internal thread.
        #     # It should then schedule any async operations (like sending to client)
        #     # on the main application's event loop.
        #     # print(f"Frame ID: {inference_result.frame_id}, Timestamp: {inference_result.frame_timestamp}")
        #     # print("Predictions from VideoFrame:", inference_result.predictions)
        #     # for pred in inference_result.predictions:
        #     #     if pred.class_name == TARGET_CLASS_NAME and pred.confidence > CONFIDENCE_THRESHOLD:
        #     #         print(f"Detected {TARGET_CLASS_NAME} with confidence {pred.confidence}")
        #     #         # TODO: Format and send results to the client (via an async handler)
        #     pass

        # stream_client = StreamClient(
        #     model_id="next-level-i0lpn/3",
        #     stream_url="rtsp://127.0.0.1:8554/live", # Use actual RTSP URL
        #     api_key=settings.ROBOFLOW_API_KEY,
        #     sink=Sink(callback=custom_on_prediction_sync), # Sink wraps the callback
        #     # model_configuration can be added here if needed
        #     # max_fps=10 # Optional: limit processing frame rate
        # )
        ```
-   **Client Control:**
    -   Use `stream_client.start()` to initiate the inference process. This call is blocking and starts its own thread(s).
    -   Use `stream_client.stop()` to terminate the client. In a FastAPI application, `start()` would be called during application startup, and `stop()` during application shutdown.

### 3.3. Prediction Result Processing and Transmission (`on_prediction` Callback)

-   **Callback Function:** The `on_prediction` function (passed to the `Sink`) is central to handling model outputs. It receives a `VideoFrame` object which contains the predictions.
-   **`VideoFrame` Object Structure (for object detection):**
    -   `predictions`: A list of `Detection` objects.
    -   Each `Detection` object contains attributes like:
        -   `x`, `y`: Center coordinates of the bounding box.
        -   `width`, `height`: Dimensions of the bounding box.
        -   `confidence`: Confidence score (0-1).
        -   `class_name`: Detected class name (e.g., `"blind-lane"`).
        -   `tracker_id`: Optional tracker ID if tracking is enabled.
    -   **Note:** It's crucial to inspect the `VideoFrame` and its `predictions` attribute in the `custom_on_prediction` callback (e.g., by logging) to confirm the exact structure, as it might vary slightly with library versions or model types.
-   **`VideoFrame` also contains:**
    -   `image_width`, `image_height`: Dimensions of the frame.
    -   `frame_id`: Unique identifier for the frame.
    -   `frame_timestamp`: Timestamp when the frame was captured.
-   **Custom Logic:**
    -   In `custom_on_prediction`, extract necessary information from `VideoFrame.predictions` (e.g., blind lane location, confidence).
    -   Filter detections based on `class_name` (e.g., `settings.ROBOFLOW_TARGET_CLASS_NAME`) and `confidence` (e.g., `settings.ROBOFLOW_CONFIDENCE_THRESHOLD`).
    -   Format the processed results into JSON.
-   **Data Transmission Mechanism:**
    -   **Recommendation:** Extend the existing FastAPI application with a new API endpoint (HTTP Long Polling, Server-Sent Events, or WebSockets are common choices).
    -   The Android application will connect to this endpoint to receive AI analysis results. The `handle_ai_prediction` async function in `main.py` is the entry point for this, currently logging results.

### 3.4. Asynchronous Processing and Performance

-   **`StreamClient` Asynchronicity:** `StreamClient` is designed for asynchronous processing, handling video decoding, model inference, and result dispatch in its own threads.
-   **FastAPI Integration:** In the FastAPI application, `StreamClient`'s startup and management are handled non-blockingly within the application's lifecycle events (lifespan manager). The `AIProcessor.start()` method is an `async def` function that internally calls the blocking `stream_client.start()` but is itself managed as an asyncio task.
-   **Frame Sampling:** The `max_fps` parameter in `StreamClient` initialization can be used to limit the processing frame rate to manage CPU load.
-   **Resource Monitoring:** Pay attention to CPU and memory usage during development and testing.

## 4. Code Structure and Modification Points (Expected)

-   **`src/app/rtsp/server.py`:**
    -   Primary responsibility is to run the GStreamer RTSP server, providing the video stream for `StreamClient`. Its internal GStreamer pipeline logic does not require specific `appsink` modifications for Roboflow.
-   **New Module (`src/app/services/ai_processor.py`):**
    -   Encapsulates `StreamClient` initialization, startup, and shutdown logic.
    -   Contains the implementation of the `_custom_on_prediction` callback function.
    -   Manages AI-related configurations (Model ID, API Key, confidence threshold, etc., read from `config.py`).
    -   The `_custom_on_prediction` callback schedules an async callback (`on_prediction_callback` passed during `AIProcessor` init) on the main event loop to handle sending results.
-   **`src/app/main.py`:**
    -   Initializes and starts the `ai_processor` service during application startup (within `lifespan`).
    -   Properly stops the `ai_processor` service during application shutdown.
    -   Defines `handle_ai_prediction` as the async callback for `AIProcessor` to process/relay results.
-   **`src/app/api/routes.py` (or a new API route file):**
    -   Define a new API endpoint (e.g., WebSocket) for the Android client to receive AI analysis results.
-   **`src/app/core/config.py`:**
    -   Add configurations for Roboflow API Key (`ROBOFLOW_API_KEY`), Model ID (`ROBOFLOW_MODEL_ID`), inference confidence threshold (`ROBOFLOW_CONFIDENCE_THRESHOLD`), and target class name (`ROBOFLOW_TARGET_CLASS_NAME`).

## 5. Testing Strategy

-   **Unit Tests:**
    -   Test the parsing logic of the `_custom_on_prediction` function in `ai_processor.py` with mock `VideoFrame` data.
-   **Integration Tests:**
    -   Start the complete FastAPI application and the GStreamer RTSP server.
    -   Use a test client to push an RTSP stream to the server.
    -   Verify that `StreamClient` successfully connects to the RTSP stream and invokes `_custom_on_prediction`.
    -   Confirm that `_custom_on_prediction` correctly processes results and that data is made available (e.g., logged by `handle_ai_prediction`, eventually sent via an API endpoint).
-   **Performance Tests:** Evaluate end-to-end processing latency and resource consumption.

## 6. Points for Discussion/Decision

-   **Specific API Design for Result Transmission:** Decide on using HTTP Long Polling, Server-Sent Events, or WebSockets, and design the message format. (WebSocket is generally preferred for real-time bidirectional communication).
-   **Target Real-time Processing Frame Rate:** Determine the ideal AI processing frame rate, considering the `max_fps` setting and application requirements.
-   **Complexity of Pre/Post-processing:** Initially, post-processing logic in `_custom_on_prediction` (like NMS) can be simplified, iterating based on requirements later.
-   **Error Handling and Status Reporting:** How to manage and report errors from `StreamClient` (e.g., model loading failures, RTSP connection issues) and report status to clients or logs.
-   **Multi-stream Processing (Future Consideration):** `StreamClient` might support multiple video sources, but the current plan focuses on a single stream.