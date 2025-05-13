## **IV. 使用 InferencePipeline 处理 RTSP 流**

### **A. InferencePipeline 概述**

InferencePipeline 是 Roboflow Inference 库中专为处理流式视频数据设计的核心组件。它采用异步方式消费视频源，能够处理来自本地设备（如网络摄像头）、RTSP 流、视频文件等多种输入 1。其设计旨在通过将视频解码、模型推理和结果分派等任务分配到不同线程来最大化处理效率 7。

### **B. 初始化 InferencePipeline**

初始化 InferencePipeline 是配置视频处理任务的关键步骤。主要参数包括：

* **model\_id (str)**: 指定要使用的 Roboflow 模型。在此项目中，为 "next-level-i0lpn/3" 3。  
* **video\_reference (Union\[str, int, List\[Union\[str, int\]\]\])**: 指定视频源。对于 RTSP 流，这是一个字符串形式的 URL 7。在此项目中，为 "rtsp://0.0.0.0:8554/push"。  
* **on\_prediction (Callable)**: 一个回调函数，在每次获得模型预测结果后被调用。此函数接收预测结果和对应的视频帧作为参数 3。这是实现自定义逻辑（如识别特定对象、记录数据、发送警报等）的核心。  
* **api\_key (Optional\[str\])**: Roboflow API 密钥。如果已设置为环境变量，则此处可以省略 7。  
* **confidence (Optional\[float\])**: (此参数在 InferencePipeline.init() 中不直接存在，但常用于模型加载或后续过滤，此处提及是基于 1 中 init 的一个例子，但该例子可能指代不同的 init 或旧版接口。实际的置信度过滤通常在 on\_prediction 回调中进行，或如果模型本身支持，则在模型加载时配置。) 对于目标检测，通常会在 on\_prediction 回调中根据返回的置信度分数进行过滤。  
* **max\_fps (Optional\[Union\[float, int\]\])**: 可选参数，用于限制每个视频源的最大处理帧率 7。如果 RTSP 源的帧率非常高或处理能力有限，设置此参数有助于控制资源消耗。

示例初始化代码片段：

Python

from inference import InferencePipeline  
\# from inference.core.interfaces.stream.sinks import render\_boxes \# 可选，用于默认渲染

\# 定义自定义的回调函数 (详见 V.C)  
def custom\_on\_prediction(predictions, video\_frame):  
    \# 在此处理预测结果  
    pass

pipeline \= InferencePipeline.init(  
    model\_id="next-level-i0lpn/3",  
    video\_reference="rtsp://0.0.0.0:8554/push", \# 确保此地址可访问  
    on\_prediction=custom\_on\_prediction,  
    \# api\_key="YOUR\_API\_KEY", \# 如果未设置环境变量，则在此提供  
    \# max\_fps=10 \# 可选，限制处理帧率  
)

### **C. 启动与控制 Pipeline**

初始化 InferencePipeline 后，使用以下方法控制其执行：

* **pipeline.start()**: 启动推理流程。这将开始从指定的 video\_reference（RTSP 流）抓取帧，进行模型推理，并在获得结果后调用 on\_prediction 回调函数 3。  
* **pipeline.join()**: 阻塞主线程，直到推理流程结束（例如，通过 Ctrl+C 中断程序）3。这确保了在主程序退出前，pipeline 能够持续运行。

## **V. 实现自定义预测结果处理**

### **A. on\_prediction 回调函数详解**

on\_prediction 回调函数是处理模型输出的核心。它在每次推理完成后被调用，并接收两个主要参数 3：

1. **predictions (dict)**: 一个包含模型预测结果的字典。其具体结构取决于所使用的模型类型。对于目标检测模型，通常包含检测到的对象的列表及其详细信息。  
2. **video\_frame (VideoFrame)**: 一个 VideoFrame 对象，包含当前处理的视频帧的元数据和像素数据。其主要属性包括 3：  
   * image: NumPy 数组格式的视频帧图像数据。  
   * frame\_id: 帧的唯一标识符（通常是序列号）。  
   * frame\_timestamp: 帧被抓取时的时间戳。  
   * source\_id: (当使用多视频源时) 视频源的索引。

### **B. 解析 predictions 对象 (针对盲道识别)**

对于目标检测模型（如本项目中用于盲道识别的模型），predictions 字典的结构通常如下 3：

JSON

{  
    "predictions": \[  
        {  
            "x": 123.4, // 中心点 x 坐标 \[3\]  
            "y": 567.8, // 中心点 y 坐标  
            "width": 50.0,  
            "height": 100.0,  
            "confidence": 0.95,  
            "class": "tactile\_paving", // 类别名称，需与模型训练时一致  
            "class\_id": 0,  
            //... 可能还有其他字段  
        },  
        //... 其他检测到的对象  
    \]  
    // 可能还有其他顶层键，如 "image": {"width": 640, "height": 480}  
}

然而，根据 3 中的信息，更标准的 Roboflow 目标检测输出结构，其边界框信息位于一个名为 box 的子字典中：

JSON

{  
    "predictions": \[  
        {  
            "box": {  
                "x": 100,  // 边界框左上角 x 坐标  
                "y": 150,  // 边界框左上角 y 坐标  
                "width": 200,  
                "height": 100  
            },  
            "class": "person", // 示例类别  
            "confidence": 0.95  
        }  
        //... more predictions  
    \]  
}

由于模型输出的具体结构可能因模型版本或类型而略有差异 9，**强烈建议在 custom\_on\_prediction 函数中首先打印 predictions 对象 (例如 print(predictions)) 或其键 (print(predictions.keys()))**，以确认其实际结构，特别是顶层键（是 "predictions" 还是其他）以及单个检测条目中边界框和类别信息的表示方式。这有助于确保后续的解析逻辑能够正确提取所需信息。

#### **1\. 单个目标检测条目的结构**

下表总结了一个典型目标检测条目中包含的关键信息，参考了 3 提供的结构：

| 键 | 数据类型 | 描述 | 示例 |
| :---- | :---- | :---- | :---- |
| class | string | 检测到的对象的类别名称 | "person" |
| confidence | float | 模型对该检测结果的置信度得分（通常0-1） | 0.95 |
| box | dict | 包含边界框坐标和尺寸的字典 |  |
| ↳ x | number (int or float) | 边界框左上角的 x 坐标 | 100 |
| ↳ y | number (int or float) | 边界框左上角的 y 坐标 | 150 |
| ↳ width | number (int or float) | 边界框的宽度 | 200 |
| ↳ height | number (int or float) | 边界框的高度 | 100 |

### **C. 实现自定义回调逻辑**

以下是一个 custom\_on\_prediction 函数的示例，用于处理盲道识别任务。它会遍历所有检测结果，筛选出类别为“盲道”（或模型实际使用的类别名，如 "tactile\_paving"）且置信度高于特定阈值的检测：

Python

from inference.core.interfaces.camera.entities import VideoFrame \# 用于类型提示

TARGET\_CLASS\_NAME \= "tactile\_paving" \# 或者模型实际输出的盲道类别名，例如 "盲道"  
CONFIDENCE\_THRESHOLD \= 0.7 \# 可调置信度阈值

def custom\_on\_prediction(predictions: dict, video\_frame: VideoFrame) \-\> None:  
    """  
    自定义回调函数，用于处理模型预测结果。  
    在此函数中，我们将筛选出盲道检测结果并打印信息。  
    """  
    \# 打印一次以确认 'predictions' 对象的实际结构  
    \# print("Raw predictions:", predictions)  
    \# print("Video frame object:", video\_frame)

    \# 访问帧图像 (NumPy array)  
    \# frame\_image \= video\_frame.image  
    \# 访问帧 ID  
    \# current\_frame\_id \= video\_frame.frame\_id  
    \# print(f"Processing frame ID: {current\_frame\_id} at {video\_frame.frame\_timestamp}")

    \# 根据实际模型输出调整键名，例如可能是 'detections' 或其他  
    \# 最好先打印 predictions.keys() 进行确认  
    primary\_predictions\_key \= "predictions" \# 假设顶层键是 'predictions'

    if primary\_predictions\_key in predictions:  
        for detection in predictions\[primary\_predictions\_key\]:  
            class\_name \= detection.get("class")  
            confidence \= detection.get("confidence")  
              
            \# 获取边界框信息，假设其结构如 \[3\] 所示  
            box\_data \= detection.get("box", {})  
            x \= box\_data.get("x")  
            y \= box\_data.get("y")  
            width \= box\_data.get("width")  
            height \= box\_data.get("height")

            if class\_name \== TARGET\_CLASS\_NAME and confidence is not None and confidence \> CONFIDENCE\_THRESHOLD:  
                print(f"盲道 ({TARGET\_CLASS\_NAME}) 检测到\! 置信度: {confidence:.2f}, "  
                      f"位置: \[x={x}, y={y}, width={width}, height={height}\]")  
                  
                \# 在此添加自定义逻辑:  
                \# 1\. 在 frame\_image 上绘制边界框和标签 (使用 OpenCV 和 Supervision)  
                \#    例如:  
                \#    import cv2  
                \#    import supervision as sv  
                \#    annotated\_image \= frame\_image.copy()  
                \#    detections\_sv \= sv.Detections(  
                \#        xyxy=sv.mask\_to\_xyxy(masks=None), \# 需要转换 box 格式为 xyxy  
                \#        confidence=np.array(\[confidence\]),  
                \#        class\_id=np.array(), \# 示例 class\_id  
                \#    ) \# 此处简化，实际转换更复杂  
                \#    box\_annotator \= sv.BoxAnnotator()  
                \#    annotated\_image \= box\_annotator.annotate(scene=annotated\_image, detections=detections\_sv)  
                \#    cv2.imshow("Annotated Frame", annotated\_image)  
                \#    cv2.waitKey(1)

                \# 2\. 将检测结果发送到其他系统 (如安卓应用、数据库、消息队列)  
                \# 3\. 触发警报或通知  
    \# else:  
    \#     print(f"警告: 在预测结果中未找到键 '{primary\_predictions\_key}'. 可用键: {list(predictions.keys())}")

在上述代码中，TARGET\_CLASS\_NAME 应替换为模型实际输出的盲道类别名称。用户可以通过检查 Roboflow Universe 上模型页面的类别信息或在初次运行时打印 detection 对象来确认。