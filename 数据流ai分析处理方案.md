# **方案详解：通过 GStreamer appsink 和 Roboflow VideoFrameProducer 处理原始帧**

> 测试用模型：https://universe.roboflow.com/microsoft/coco-dataset-vdnr1/model/23
>  model_id="coco-dataset-vdnr1/23"

## **I. 方案概述**

此方案的核心思想是，GStreamer 服务器在接收到 Android 应用的 RTSP 推流后，在服务器内部对视频流进行解复用和解码，然后通过特定机制将原始视频帧（raw frames）提取出来。这些原始帧将通过一个自定义的 VideoFrameProducer 提供给 Roboflow InferencePipeline 进行 AI 分析处理。这种方法旨在直接利用服务器上已接收的帧数据，为 AI 分析提供输入，同时使用标准的 Roboflow 模型进行推理。

## **II. 核心机制**

### **A. 从 GStreamer 服务器提取帧**

GStreamer 服务器接收来自 Android 应用的 RTSP 推流。可以在该服务器的 GStreamer 处理管道中添加一个 appsink 元件。appsink 作为一个特殊的“汇”元件，允许应用程序代码从 GStreamer 管道中拉取数据缓冲（GstBuffer）1。通常，appsink 会被放置在解码器之后，以便获取解码后的原始视频帧。可以通过连接到 appsink 的 new-sample 信号，在每一帧数据准备好时得到通知，并在回调函数中提取帧数据。

这些从 appsink 获取的 GstBuffer 可以被转换为 NumPy 数组 2。NumPy 数组是 Roboflow VideoFrame 对象所期望的图像数据格式（VideoFrame 对象的 image 属性）4。用户的表述“使其直接处理推送到服务器的原始帧数据”，也暗示了 GStreamer 服务器应负责从 RTSP 流中解复用/解码，然后 appsink 从这些解码后的原始帧中提取数据。这是一个标准的 GStreamer 应用模式。

### **B. 将帧喂给 Roboflow InferencePipeline**

将从 GStreamer appsink 提取的 NumPy 帧数据喂给 InferencePipeline，主要通过实现自定义的 VideoFrameProducer：

* **自定义 VideoFrameProducer**  
  * InferencePipeline.init() 方法的 video\_reference 参数接受 Union\] 类型。其中 VideoSourceIdentifier 可以是 Callable\[, VideoFrameProducer\] 5。这为用户提供了一种注入自定义帧来源的机制。  
  * VideoFrameProducer 是一个需要用户实现的抽象基类（通常定义在 inference.core.interfaces.camera.entities 或类似路径，如 inference.core.interfaces.camera.video\_source 中与 VideoSource 相关的部分）。它定义了帧是如何生成或获取，并提供给 InferencePipeline 的。  
  * InferencePipeline 内部通过 prepare\_video\_sources 函数将 video\_reference（如果是 Callable\[, VideoFrameProducer\]）转换为 VideoSource 对象。这个 VideoSource 对象会管理 VideoFrameProducer 的生命周期并从中读取帧。  
  * **实现思路概要:**  
    1. 在 GStreamer 服务器的推流处理管道中加入 appsink。  
    2. 为 appsink 实现 Python 回调函数，用于检索 Gst.Buffer 并将其转换为 NumPy 数组及提取相关元数据（如时间戳）。  
    3. 实现一个自定义的 MyGStreamerFrameProducer 类，该类应继承自 VideoFrameProducer（其确切的抽象方法需要参考 inference 库的定义，通常包括 start(), read\_frame() \-\> Optional\[VideoFrame\], release(), get\_fps() \-\> Optional\[float\], get\_resolution() \-\> Optional\]）。  
       * \_\_init\_\_ 方法：接收一个由 appsink 回调函数填充的线程安全队列作为帧源，以及视频的固有属性（如预期的 FPS、分辨率）。  
       * start(): 初始化生产者，例如启动任何内部线程或资源。  
       * read\_frame(): 从帧队列中拉取 NumPy 数组，构造并返回一个 VideoFrame 对象。如果队列为空或流结束，则返回 None。VideoFrame 对象应包含 image, frame\_id, frame\_timestamp, source\_id, 以及可选的 fps, measured\_fps, comes\_from\_video\_file 等属性，依据 inference.core.interfaces.camera.entities.VideoFrame 的定义 4。  
       * release(): 清理生产者使用的资源。  
       * get\_fps(): 返回视频流的声明帧率。  
       * get\_resolution(): 返回视频流的声明分辨率。  
    4. 初始化 InferencePipeline：使用 InferencePipeline.init(...) 方法（而非 init\_with\_custom\_logic，因为我们希望使用标准的 Roboflow 模型处理流程），并将 video\_reference 参数设置为一个 lambda 函数，该函数返回 MyGStreamerFrameProducer 的实例。例如: pipeline \= InferencePipeline.init(video\_reference=lambda: MyGStreamerFrameProducer(...), model\_id="...", on\_prediction=...) 5。

## **III. 性能考量**

通过 Python appsink 回调函数提取帧涉及到数据拷贝（例如 buf.extract\_dup() 2）以及 Python 代码的执行开销。对于高分辨率或高帧率的视频流，从 GStreamer appsink 到 Python 回调，再到 NumPy 转换，然后创建 VideoFrame 对象，经由 VideoFrameProducer 产出，最终被 InferencePipeline 消费的整个过程，可能会引入延迟。

这个位于 GStreamer appsink 和 VideoFrameProducer 之间的 Python 桥接部分，由于 Python 全局解释器锁（GIL）的存在以及 Python 中多步数据处理的开销，可能会成为性能瓶颈 6。特别是与 InferencePipeline 可能使用优化的 C/C++ 绑定直接消费标准 RTSP 流相比，这种瓶颈更为显著。如果 Android 应用以 30 FPS 推流，那么这个 Python 桥接必须在约 33 毫秒内持续稳定地完成每一帧的处理。这是本方案需要重点关注的性能问题。

## **IV. 优缺点分析**

* **优点:**  
  * 基本保持了 GStreamer RTSP 服务器当前推流专用配置（从 Android 应用视角看）的不变，仅需增加一个 appsink。  
  * 为用户提供了在帧数据进入 InferencePipeline 之前，在 Python 环境中进行预处理的高度控制能力。  
  * 直接满足了用户“处理推送到服务器的原始帧数据”的需求。  
  * 与 InferencePipeline 的设计兼容，通过 VideoFrameProducer 提供自定义视频源是受支持的集成方式 7。  
* **缺点:**  
  * Roboflow InferencePipeline 的集成需要用户实现 VideoFrameProducer 接口。  
  * 基于 Python 的 GStreamer 到 Roboflow 帧数据桥接部分存在潜在的性能开销 3。  
  * 未能利用 InferencePipeline 内建的针对标准视频源（如 RTSP URL 或文件）的优化解码和流管理能力。

## **V. 高层实现指南**

### **A. GStreamer 服务器修改 (Python)**

1. **定位现有管道：** 确定当前 GStreamer 服务器中处理来自 Android 应用的 RTSP 推流的管道。  
2. **添加 appsink：** 在此管道的解码器之后添加一个 appsink 元件，以获取原始视频帧。  
   * 例如: ...\! rtph264depay\! avdec\_h264\! videoconvert\! video/x-raw,format=BGR\! appsink name=ai\_framesink emit-signals=true caps="video/x-raw,format=BGR"  
   * 确保 appsink 的 caps 与期望输出给 VideoFrameProducer 的格式一致。  
   * 可参考 appsink 示例代码 2。  
3. **实现 appsink 回调：** 为 appsink 的 new-sample 信号实现一个回调函数 2。  
   * 在回调函数内部：  
     * 通过 sample \= sink.emit("pull-sample") 获取 GStreamer 样本。  
     * 通过 buf \= sample.get\_buffer() 获取数据缓冲区。  
     * 通过 caps \= sample.get\_caps() 获取帧的宽度、高度、格式等元数据。  
     * 如果可能，从 buf.pts 或 sample 获取纳秒级时间戳。  
     * 将 buf 转换为 NumPy 数组 2，确保正确的形状 (shape) 和数据类型 (dtype)。  
     * 将此 NumPy 数组以及相关的元数据（如时间戳）放入一个线程安全的队列，供 VideoFrameProducer 消费。

### **B. Roboflow VideoFrameProducer 实现 (Python)**

Python

from abc import ABC, abstractmethod  
from typing import Optional, Tuple, Generator  
import numpy as np  
import datetime  
import queue \# For passing frames from GStreamer callback to producer

\# Assuming VideoFrame is defined in inference.core.interfaces.camera.entities  
from inference.core.interfaces.camera.entities import VideoFrame \# \[4\]

\# Placeholder for the actual VideoFrameProducer abstract base class  
\# from inference.core.interfaces.camera.video\_source import VideoFrameProducer \# Path might vary  
\# For now, we define an ABC based on expected methods.  
class AbstractVideoFrameProducer(ABC):  
    @abstractmethod  
    def start(self) \-\> None:  
        pass

    @abstractmethod  
    def read\_frame(self) \-\> Optional\[VideoFrame\]:  
        pass

    @abstractmethod  
    def release(self) \-\> None:  
        pass

    @abstractmethod  
    def get\_fps(self) \-\> Optional\[float\]:  
        pass

    @abstractmethod  
    def get\_resolution(self) \-\> Optional\]:  
        pass

class MyGStreamerFrameProducer(AbstractVideoFrameProducer): \# Replace AbstractVideoFrameProducer with actual base class  
    def \_\_init\_\_(self, frame\_queue: queue.Queue, fps: float, width: int, height: int, source\_id: int \= 0):  
        self.frame\_queue \= frame\_queue  
        self.running \= False  
        self.\_fps \= fps  
        self.\_width \= width  
        self.\_height \= height  
        self.\_source\_id \= source\_id  
        self.frame\_id\_counter \= 0

    def start(self) \-\> None:  
        self.running \= True  
        \# Any initialization logic for the producer  
        print("MyGStreamerFrameProducer started.")

    def read\_frame(self) \-\> Optional\[VideoFrame\]:  
        if not self.running:  
            return None  
        try:  
            \# Assuming queue stores (numpy\_array, gst\_timestamp\_ns)  
            numpy\_frame, gst\_timestamp\_ns \= self.frame\_queue.get(timeout=0.1) \# Short timeout  
              
            self.frame\_id\_counter \+= 1  
              
            current\_timestamp \= datetime.datetime.now()  
            if gst\_timestamp\_ns is not None:  
                \# Example: Convert GStreamer ns timestamp to datetime  
                \# This might need adjustment based on GStreamer's timestamp epoch  
                try:  
                    current\_timestamp \= datetime.datetime(1970, 1, 1) \+ datetime.timedelta(microseconds=gst\_timestamp\_ns / 1000)  
                except OverflowError: \# Handle potential overflow if timestamp is too large or small  
                    current\_timestamp \= datetime.datetime.now()

            video\_frame \= VideoFrame(  
                image=numpy\_frame,  
                frame\_id=self.frame\_id\_counter,  
                frame\_timestamp=current\_timestamp,  
                source\_id=self.\_source\_id,  
                fps=self.\_fps, \# Declared FPS  
                measured\_fps=None, \# Can be calculated if needed  
                comes\_from\_video\_file=False \# Assuming live stream  
            )  
            return video\_frame  
        except queue.Empty:  
            return None \# No frame available currently  
        except Exception as e:  
            print(f"Error in MyGStreamerFrameProducer.read\_frame: {e}")  
            return None

    def release(self) \-\> None:  
        self.running \= False  
        \# Clear the queue or other cleanup  
        while not self.frame\_queue.empty():  
            try:  
                self.frame\_queue.get\_nowait()  
            except queue.Empty:  
                break  
        print("MyGStreamerFrameProducer released.")

    def get\_fps(self) \-\> Optional\[float\]:  
        return self.\_fps

    def get\_resolution(self) \-\> Optional\]:  
        return (self.\_width, self.\_height)

### **C. Roboflow InferencePipeline 初始化 (Python)**

Python

from inference import InferencePipeline  
\# VideoFrame and VideoFrameProducer imports from previous section  
\# from inference.core.interfaces.camera.entities import VideoFrame, VideoFrameProducer \# Adjust import path as needed

\# import datetime \# Already imported in producer  
\# import queue    \# Already imported in producer  
\# import numpy as np \# Already imported in producer  
\# from typing import Optional, Tuple, Union, List \# For type hints in sink

\# Assume MyGStreamerFrameProducer class is defined as above

\# This queue will be populated by the GStreamer appsink callback  
gstreamer\_frame\_queue \= queue.Queue(maxsize=10) \# Set a reasonable maxsize

\# \--- GStreamer Appsink Callback (Conceptual) \---  
\# def gst\_appsink\_new\_sample\_callback(sink, user\_data\_queue):  
\#     sample \= sink.emit("pull-sample")  
\#     if sample:  
\#         buf \= sample.get\_buffer()  
\#         caps \= sample.get\_caps()  
\#         \#... (extract width, height, format)...  
\#         \#... (convert buffer to numpy\_array)...  
\#         \#... (extract gst\_timestamp\_ns from buffer if available)...  
\#         numpy\_array \=... \# Placeholder  
\#         gst\_timestamp\_ns \=... \# Placeholder (e.g., buf.pts if Gst.Format.TIME)  
\#         try:  
\#             user\_data\_queue.put\_nowait((numpy\_array, gst\_timestamp\_ns))  
\#         except queue.Full:  
\#             print("Frame producer queue is full, dropping frame.")  
\#     return Gst.FlowReturn.OK  
\# \--- End GStreamer Appsink Callback \---

\# Instantiate the producer  
\# These values (fps, width, height) should ideally come from the GStreamer stream's capabilities  
video\_fps \= 30.0  
video\_width \= 640  
video\_height \= 480  
source\_identifier \= 0 \# If only one custom source

frame\_producer\_instance \= MyGStreamerFrameProducer(  
    frame\_queue=gstreamer\_frame\_queue,  
    fps=video\_fps,  
    width=video\_width,  
    height=video\_height,  
    source\_id=source\_identifier  
)

\# Define your sink function for predictions  
def my\_custom\_prediction\_sink(predictions, video\_frame):  
    \# For a single video source with ADAPTIVE or SEQUENTIAL sink\_mode,  
    \# predictions will be AnyPrediction (dict) and video\_frame will be VideoFrame.  
    \# If sink\_mode is BATCH, or ADAPTIVE with multiple sources, they will be lists.  
    \# This example assumes single item processing for simplicity with default sink\_mode.  
      
    if isinstance(video\_frame, list): \# Handling batch mode just in case  
        if not video\_frame or video\_frame is None: return  
        current\_frame\_id \= video\_frame.frame\_id  
        current\_preds \= predictions if predictions and predictions is not None else "No predictions"  
    elif video\_frame is not None: \# Handling sequential mode  
        current\_frame\_id \= video\_frame.frame\_id  
        current\_preds \= predictions if predictions is not None else "No predictions"  
    else:  
        return

    print(f"Sink \- Frame ID: {current\_frame\_id}, Predictions: {current\_preds}")  
    \# Here, you would implement your FastAPI WebSocket push logic  
    \# e.g., await websocket.send\_json({"frame\_id": current\_frame\_id, "predictions": current\_preds})

\# Initialize InferencePipeline using.init()  
\# The \`video\_reference\` takes a callable that returns the producer instance.  
pipeline \= InferencePipeline.init(  
    model\_id="your\_roboflow\_model\_id/version", \# Replace with your model  
    video\_reference=lambda: frame\_producer\_instance,  
    on\_prediction=my\_custom\_prediction\_sink,  
    api\_key="YOUR\_ROBOFLOW\_API\_KEY", \# Replace with your API key  
    max\_fps=video\_fps, \# Optional: can help pipeline manage processing rate  
    \# source\_buffer\_filling\_strategy, source\_buffer\_consumption\_strategy might be relevant if VideoSource uses them  
    \# sink\_mode can be SinkMode.SEQUENTIAL, SinkMode.BATCH, or SinkMode.ADAPTIVE (default)  
)

\# Start the pipeline  
\# This will internally call frame\_producer\_instance.start() via the VideoSource  
pipeline.start(use\_main\_thread=False) \# Run dispatching in a separate thread

\# \--- Your GStreamer pipeline and appsink callback should be running here, \---  
\# \--- populating the gstreamer\_frame\_queue.                            \---

\# To gracefully stop:  
\# pipeline.terminate()  
\# pipeline.join()  
\# frame\_producer\_instance.release() \# Ensure producer resources are also released if not handled by VideoSource termination

### **D. FastAPI WebSocket Sink**

The on\_prediction callback function provided to InferencePipeline (e.g., my\_custom\_prediction\_sink in the example) will receive the model's prediction results and the corresponding VideoFrame object(s).5 This function is the ideal place to format the data and push it to the Android application via your FastAPI WebSocket connection. The exact signature and structure of predictions and video\_frame passed to the sink depend on the sink\_mode and the number of video sources. For a single custom producer, with the default SinkMode.ADAPTIVE, the sink will likely receive a single prediction object and a single VideoFrame object per call.

## **VI. 结论与建议**

此方案，即在 GStreamer 服务器接收推流的现有管道中使用 appsink 提取帧，并通过一个自定义的 VideoFrameProducer 将这些帧喂给 Roboflow InferencePipeline（使用 InferencePipeline.init() 方法），被认为是满足用户需求的优选方法。

主要理由包括：

1. **符合用户意图：** 直接处理已推送到 GStreamer 服务器的帧数据，与用户的核心需求“直接处理推送到服务器的原始帧数据”高度吻合。  
2. **最小化服务器改动：** 对现有 GStreamer RTSP 服务器的主要推流接收功能改动较小，主要是增加 appsink。  
3. **控制与灵活性：** 提供了在帧数据进入 Roboflow 推理前进行预处理的更大控制权和灵活性。  
4. **Roboflow 接口支持：** InferencePipeline.init() 的 video\_reference 参数支持 Callable\[, VideoFrameProducer\]，使得通过自定义生产者提供视频源成为一种清晰且受支持的集成路径 5。

尽管此方案中 GStreamer appsink 到 VideoFrameProducer 的 Python 桥接部分需要关注其性能表现 3，但这通常可以通过高效的编程实践和适当的资源配置来管理。对项目的成功而言，仔细实现 Python 桥接逻辑，确保帧数据的及时、高效传递，以及对 VideoFrame 对象中时间戳和帧ID的正确管理，将是至关重要的。

#### **引用的著作**

1. Fetch RTSP Stream using GStreamer in Python and get image in Numpy \- GitHub, 访问时间为 五月 16, 2025， [https://github.com/sahilparekh/GStreamer-Python](https://github.com/sahilparekh/GStreamer-Python)  
2. gst-appsink-opencv.py · GitHub, 访问时间为 五月 16, 2025， [https://gist.github.com/cbenhagen/76b24573fa63e7492fb6](https://gist.github.com/cbenhagen/76b24573fa63e7492fb6)  
3. How to use Gstreamer AppSink in Python \- LifeStyleTransfer, 访问时间为 五月 16, 2025， [https://lifestyletransfer.com/how-to-use-gstreamer-appsink-in-python/](https://lifestyletransfer.com/how-to-use-gstreamer-appsink-in-python/)  
4. inference/inference/core/interfaces/camera/entities.py at main · roboflow/inference \- GitHub, 访问时间为 五月 16, 2025， [https://github.com/roboflow/inference/blob/main/inference/core/interfaces/camera/entities.py](https://github.com/roboflow/inference/blob/main/inference/core/interfaces/camera/entities.py)  
5. Inference pipeline, 访问时间为 五月 16, 2025， [https://inference.roboflow.com/reference/inference/core/interfaces/stream/inference\_pipeline](https://inference.roboflow.com/reference/inference/core/interfaces/stream/inference_pipeline)  
6. Run Computer Vision Models on a RTSP Stream on a NVIDIA Jetson Orin Nano, 访问时间为 五月 16, 2025， [https://blog.roboflow.com/run-inference/](https://blog.roboflow.com/run-inference/)  
7. How to pass frames (numpy arrays) as video\_reference into Roboflow Inference Pipeline, 访问时间为 五月 16, 2025， [https://stackoverflow.com/questions/78155915/how-to-pass-frames-numpy-arrays-as-video-reference-into-roboflow-inference-pip](https://stackoverflow.com/questions/78155915/how-to-pass-frames-numpy-arrays-as-video-reference-into-roboflow-inference-pip)  
8. Predict on a Video, Webcam or RTSP Stream \- Roboflow Inference, 访问时间为 五月 16, 2025， [https://inference.roboflow.com/quickstart/run\_model\_on\_rtsp\_webcam/](https://inference.roboflow.com/quickstart/run_model_on_rtsp_webcam/)