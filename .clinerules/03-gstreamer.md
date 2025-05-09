# GStreamer Development Guidelines for RTSP Video Streaming

This document outlines best practices and conventions for using GStreamer within this project, specifically focusing on RTSP video stream handling.

## 1. Initialization and Setup

- **Initialize GStreamer**: Always initialize GStreamer early in the application lifecycle using `Gst.init(None)` or `Gst.init(sys.argv)`.
  ```python
  import gi
  gi.require_version('Gst', '1.0')
  gi.require_version('GstRtspServer', '1.0')
  from gi.repository import Gst, GstRtspServer, GLib
  
  # Initialize GStreamer
  Gst.init(None) 
  ```
- **Version Checks**: While generally not needed for stable APIs, be aware of `Gst.version()` if specific feature versions are critical.
- **Main Loop**: A `GLib.MainLoop` is typically required for GStreamer applications, especially when dealing with asynchronous events like bus messages or RTSP server operations.
  ```python
  # main_loop = GLib.MainLoop()
  # try:
  #     main_loop.run()
  # except KeyboardInterrupt:
  #     pass
  ```

## 2. Pipeline Construction

- **Programmatic Construction**: Construct GStreamer pipelines programmatically in Python. Avoid using `gst_parse_launch` for production code due to reduced flexibility and error handling.
- **Element Creation**:
    - Use `Gst.ElementFactory.make("element-factory-name", "unique-element-instance-name")` to create elements.
    - Always check if the element creation was successful (i.e., the result is not `None`).
    ```python
    appsrc = Gst.ElementFactory.make("appsrc", "video_source_user123")
    if not appsrc:
        # Handle error: element could not be created
        pass
    ```
- **Element Naming**: Use descriptive and unique names for element instances (e.g., `appsrc_push_stream_X`, `h264parse_live_feed_Y`) to aid in debugging and log interpretation.
- **Pipeline/Bin Management**:
    - Create a `Gst.Pipeline` as the top-level container.
    - Add elements to the pipeline using `pipeline.add(element1, element2, ...)`.
- **Linking Elements**:
    - Link elements using `element1.link(element2)`.
    - Always check the return status of linking operations.
    - For video, ensure pad capabilities are compatible. Common RTSP video elements include:
        - `appsrc`: To feed video data from the application (e.g., received via HTTP POST) into the pipeline.
        - `rtph264depay` (or other codec-specific depayloader): If receiving RTP packets.
        - `h264parse` (or other codec-specific parser): To parse the video stream and ensure proper framing.
        - `rtph264pay` (or other codec-specific payloader): To packetize video for RTP streaming.
        - `udpsink` / `udpsrc`: For RTP transport (often managed by `gst-rtsp-server`).

## 3. `gst-rtsp-server` Usage

- **Server Instance**: Create a `GstRtspServer.Server` instance.
  ```python
  # server = GstRtspServer.Server()
  # server.set_service("8554") # Set RTSP port
  # server.attach(None) # Attach to default main context
  ```
- **Media Factory**:
    - Use `GstRtspServer.MediaFactory` to define how RTSP streams are created and served.
    - Subclass `GstRtspServer.MediaFactory` for custom stream creation logic.
    - In the `do_create_element` method of your custom factory, construct the GStreamer pipeline (the `launch` string or programmatic pipeline) that will generate the RTSP stream. This pipeline typically ends with an RTP payloader (e.g., `rtph264pay name=pay0 pt=96`).
    ```python
    # class MyMediaFactory(GstRtspServer.MediaFactory):
    #     def __init__(self):
    #         GstRtspServer.MediaFactory.__init__(self)
    #
    #     def do_create_element(self, url):
    #         # Example: "appsrc name=mysource ! videoconvert ! x264enc ! rtph264pay name=pay0 pt=96"
    #         pipeline_str = "( appsrc name=videosrc is-live=true format=GST_FORMAT_TIME caps=video/x-h264,stream-format=byte-stream,alignment=au ! rtph264pay name=pay0 pt=96 )"
    #         return Gst.parse_launch(pipeline_str)
    #
    # factory = MyMediaFactory()
    # factory.set_shared(True) # Share the same pipeline for multiple clients
    # server.get_mount_points().add_factory("/live", factory)
    ```
- **Feeding Data via `appsrc` (for `/push` endpoint)**:
    - The media factory for the `/push` endpoint will likely use an `appsrc` element.
    - The Flask route handler for `/push` will receive video data and needs a mechanism to pass this data to the `appsrc` element within the GStreamer pipeline associated with that specific push stream. This often involves a shared data structure or a callback mechanism.
    - Set appropriate caps on `appsrc`, e.g., `video/x-h264, stream-format=avc, alignment=au`.
    - Use `appsrc.emit("push-buffer", Gst.Buffer.new_wrapped(data))` to feed data.
    - Signal `appsrc.emit("end-of-stream")` when the push is complete.

## 4. Bus Message Handling

- **Importance**: The `Gst.Bus` is critical for receiving asynchronous messages (errors, EOS, warnings, state changes) from GStreamer elements and pipelines.
- **Setup**:
    - Get the bus from the pipeline: `bus = pipeline.get_bus()`.
    - Add a signal watch: `bus.add_signal_watch()`.
    - Connect to the `"message"` signal: `bus.connect("message::error", on_error_message_callback)`, `bus.connect("message::eos", on_eos_message_callback)`, etc.
- **Message Parsing**:
    - In callbacks, parse the message: `err, debug_info = msg.parse_error()`, etc.
    - **Error Messages**: Log detailed error information (`err`, `debug_info`). Take appropriate action (e.g., stop pipeline, notify client).
    - **EOS (End-Of-Stream)**: Handle gracefully, typically by setting the pipeline to `NULL` state and cleaning up.
    - **State Changes**: Useful for debugging; log old state, new state, and pending state.
- **Polling (Alternative)**: `message = bus.timed_pop_filtered(timeout, Gst.MessageType.ERROR | Gst.MessageType.EOS)` can be used but signal-based handling is often preferred for responsiveness.

## 5. Pad and Capabilities (Caps)

- **Pad Linking**: Ensure pads are linked correctly (`src` to `sink`).
- **Capabilities (Caps)**:
    - Define the type of data that flows between elements.
    - Use `Gst.Caps.from_string()` to create caps objects (e.g., `"video/x-h264,framerate=30/1,width=1280,height=720"`).
    - Ensure caps are compatible between linked pads. GStreamer usually handles this, but explicit checks or `capsfilter` elements can be useful.
    - For `appsrc`, setting the `caps` property is crucial for the downstream elements to understand the data format.

## 6. State Management

- **Pipeline States**: `NULL`, `READY`, `PAUSED`, `PLAYING`.
- **State Changes**:
    - Use `pipeline.set_state(Gst.State.PLAYING)` to start a pipeline.
    - Use `pipeline.set_state(Gst.State.NULL)` to stop and release resources.
    - State changes are asynchronous. Check the return value (`Gst.StateChangeReturn`) or listen for state change messages on the bus.
- **Error Handling during State Changes**: If `set_state` returns `Gst.StateChangeReturn.FAILURE`, an error occurred.

## 7. Resource Management

- **Unreferencing Objects**: GStreamer uses reference counting. Call `.unref()` on GStreamer objects (elements, pads, buffers, bus, pipeline, etc.) when they are no longer needed to prevent memory leaks.
    - This is especially important when pipelines are stopped or elements are removed.
    - `Gst.Pipeline.set_state(Gst.State.NULL)` helps release resources held by elements.
- **Python's Garbage Collector**: While Python's GC helps, explicit `unref` is good practice for GObject-based libraries like GStreamer, especially for objects managed outside the Python object graph's direct control.

## 8. Debugging

- **`GST_DEBUG` Environment Variable**: Set this to control GStreamer's logging verbosity (e.g., `GST_DEBUG=3`, `GST_DEBUG=appsrc:5`).
- **`gst-inspect-1.0`**: Command-line tool to inspect GStreamer elements and their properties.
- **`gst-launch-1.0`**: Command-line tool to quickly test GStreamer pipelines.
- **Logging**: Implement comprehensive logging within your Python application for GStreamer events, state changes, and errors.

## 9. Threading

- **GLib Main Context**: GStreamer is often integrated with GLib's main loop. Ensure GStreamer calls that interact with elements or pipelines are generally made from the thread running the GLib main context to which the pipeline is attached, or use `Gst.Object.dispatch_sync()` or `Gst.Object.dispatch_async()` if needed.
- **`gst-rtsp-server` Threading**: The RTSP server manages its own threads for client connections. Callbacks from the media factory or server signals might occur in these threads.
- **Python Threading**: If using Python threads to manage GStreamer pipelines or data flow (e.g., feeding `appsrc`), ensure thread safety. `GLib.idle_add()` can be used to schedule functions to run in the main GLib thread.
