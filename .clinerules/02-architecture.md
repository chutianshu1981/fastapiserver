# Architecture Guidelines

## 1. Architecture Decision Records (ADRs)

- **Purpose**: Document significant architectural decisions, their context, and consequences. This helps new team members understand the rationale behind the current design and provides a historical record for future architectural evolution.
- **When to Create an ADR**:
    - Introducing a new technology, library, or framework.
    - Changing a core component's design or responsibility.
    - Modifying significant data flows or storage mechanisms.
    - Decisions that have a wide-ranging impact on the codebase or development practices.
    - When there are multiple viable options and a clear rationale for the chosen one is needed.
- **Format**: Use a simple Markdown template for each ADR. Store individual ADRs in a dedicated project directory like `docs/adr/` (e.g., `docs/adr/001-use-flask-for-api.md`). Each ADR should include:
    - **Title**: A short, descriptive title (e.g., "ADR-001: Use Flask for API Layer").
    - **Status**: Proposed, Accepted, Rejected, Deprecated, Superseded by ADR-XXX.
    - **Date**: Date the decision was made or last updated.
    - **Context**: What is the problem or situation being addressed? What are the constraints, requirements, and forces at play?
    - **Decision Drivers**: Key criteria or goals influencing the decision (e.g., performance, scalability, development speed, team familiarity, maintainability).
    - **Considered Options**: List the different solutions/approaches that were considered. Briefly describe each.
    - **Decision**: Clearly state the chosen solution and the detailed reasoning behind why it was selected over other options.
    - **Consequences**:
        - **Positive**: Benefits of this decision.
        - **Negative**: Drawbacks, risks, or limitations.
        - **Neutral**: Other impacts or considerations.
        - **Trade-offs**: What was sacrificed to achieve the benefits?
    - **Pros & Cons of Considered Options (Optional but Recommended)**: A brief summary for each option.
    - **Further Considerations (Optional)**: Any open issues, future work, or related decisions.
- **Review Process**: ADRs should ideally be reviewed by the team or relevant stakeholders before being marked as "Accepted."
- **Accessibility**: Ensure ADRs are easily discoverable by the team.

## 2. System Architecture Overview

- **High-Level Diagram**: Maintain a high-level diagram (e.g., using Mermaid, draw.io, or similar tools) in `docs/architecture/system-overview.md` or embedded in the main project README. This diagram should illustrate:
    - Main components (e.g., Android App, FastAPI Server, Gstreamer RTSP Module, AI Recognition Module, WebSocket Service).
    - Key interactions and data flows between these components (e.g., RTSP stream from App to `/push`, client requests to `/live`, AI detection results via WebSocket).
    - External services or dependencies (e.g., Roboflow API).
- **Component Responsibilities**: Briefly describe the primary responsibility of each major component.
    - **FastAPI Server (`src/app/`)**: Handles HTTP requests, authentication (if any), request validation, and orchestrates responses. Manages RTSP stream publishing (`/push`) and playback (`/live`) endpoints. Provides WebSocket endpoints for transmitting AI detection results.
    - **Gstreamer RTSP Module (`src/app/rtsp/server.py`)**: Manages the underlying Gstreamer pipelines for receiving, processing (if any), and re-streaming RTSP feeds. Handles the lifecycle of RTSP server instances and media pipelines.
    - **AI Recognition Module (`src/app/services/ai_processor.py`)**: Integrates with the Roboflow `InferencePipeline` to process video frames from the RTSP stream, perform AI inference for blind tactile paving detection, and deliver structured detection results.
    - **WebSocket Service (`src/app/services/websocket_service.py`)**: Manages WebSocket connections and broadcasts AI detection results to connected Android clients.
    - **Android App (External)**: Acts as the RTSP client (pushing the video stream to the server) and WebSocket client (receiving AI detection results from the server).
- **Technology Stack**: List the key technologies used (Python, FastAPI, Gstreamer, Roboflow, WebSockets, specific Gstreamer plugins, etc.) and briefly justify their choice if not covered by an ADR.

## 3. Modularity and Decoupling

- **FastAPI Routers**: Utilize FastAPI Routers (`src/app/api/`) to organize routes and related logic into distinct modules.
- **Service Layer (`src/app/services/`)**: Encapsulate business logic and interactions with external systems (like Gstreamer and Roboflow) within a service layer. API routes should delegate to these services.
    - **AI Service**: Encapsulates the Roboflow `InferencePipeline` initialization, configuration, and lifecycle management.
    - **WebSocket Service**: Manages client connections, broadcasts, and message formatting.
- **Gstreamer Abstraction**: The Gstreamer-specific code in `src/app/rtsp/server.py` should provide a clear API for the rest of the application to interact with, abstracting away Gstreamer complexities as much as possible.
- **Configuration Management (`src/app/core/config.py`)**: Centralize application configuration. Avoid hardcoding configuration values within components. Include AI-specific configurations (model IDs, API keys, inference thresholds).

## 4. Scalability and Performance Considerations (Future Growth)

- **Statelessness**: Design API endpoints to be as stateless as possible to facilitate horizontal scaling.
- **Gstreamer Performance**:
    - Optimize Gstreamer pipelines for efficiency (e.g., choosing appropriate plugins, hardware acceleration if available and necessary).
    - Monitor resource usage (CPU, memory, network bandwidth) of Gstreamer processes.
- **Connection Handling**: Consider limits on concurrent RTSP streams, HTTP connections, and WebSocket connections.
- **Asynchronous Operations**: For long-running tasks or I/O-bound operations not directly related to Gstreamer's real-time nature, consider asynchronous patterns (e.g., Celery, asyncio) if FastAPI's default asynchronous model becomes a bottleneck. (Note: Gstreamer itself has its own threading model).
- **AI Inference Performance**:
    - Use the `max_fps` parameter in Roboflow's `InferencePipeline` to manage processing load.
    - Monitor CPU/GPU usage during inference operations.
    - Consider performance tradeoffs between inference accuracy and processing speed.
- **WebSocket Scaling**:
    - Implement a mechanism to handle multiple concurrent WebSocket connections.
    - Consider broadcast patterns to efficiently distribute messages to multiple clients.

## 5. Security Considerations

- **Input Validation**: Rigorously validate all inputs to API endpoints (parameters, request bodies, WebSocket messages).
- **RTSP Authentication/Authorization (If Needed)**: If streams are sensitive, consider mechanisms for securing RTSP publishing and playback.
- **WebSocket Security**: Implement appropriate authentication and authorization for WebSocket connections.
- **Dependency Security**: Regularly update dependencies to patch known vulnerabilities. Use tools like `pdm audit` or Snyk.
- **Error Handling**: Avoid leaking sensitive information in error messages.
- **API Key Management**: Securely store and manage the Roboflow API key and other sensitive credentials.

## 6. Data Flow & Communication Protocols

- **Video Streaming**: H.264 encoded RTSP stream (640x480 resolution, no audio) from Android client to server.
- **AI Processing Pipeline**:
    - RTSP stream → Gstreamer processing → Roboflow InferencePipeline → Detection results
    - Target processing rate: 2-10 FPS for inference operations
- **Detection Results Format**: Standardized JSON structure for WebSocket transmission:
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
- **Client-Server Communication**:
    - **RTSP**: For video streaming from Android to server
    - **WebSocket**: For real-time AI detection results from server to Android
    - **HTTP/REST**: For configuration, status checks, and non-real-time operations

## 7. Testing & Quality Assurance

- **Unit Testing**: Test individual components (AI processor, WebSocket broadcaster, etc.) with mock inputs/outputs.
- **Integration Testing**: Verify correct data flow between components (e.g., from RTSP stream to AI processor to WebSocket service).
- **End-to-End Testing**: Test the complete pipeline from Android video capture through server processing to detection results display.
- **Performance Testing**: Validate system meets the 2-10 FPS processing target under expected load conditions.
- **Error Handling**: Test system resilience to common failure scenarios (network interruptions, malformed inputs, etc.).
