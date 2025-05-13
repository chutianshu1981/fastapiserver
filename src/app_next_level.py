# import a utility function for loading Roboflow models
from inference import get_model
# import supervision to visualize our results
import supervision as sv
# import cv2 to help load and process our image
import cv2
import numpy as np
import json

# $env:ROBOFLOW_API_KEY="vQBqeX1kgPouPr8aWDd5"

# 添加调试信息输出函数
def debug_predictions(predictions, msg=""):
    print(f"===== {msg} =====")
    # 提取唯一的类别ID
    class_ids = set()
    for pred in predictions["predictions"]:
        if "class" in pred:
            class_ids.add(pred["class"])
        elif "class_id" in pred:
            class_ids.add(pred["class_id"])
    
    print("检测到的类别ID:", sorted(list(class_ids)))
    
    # 打印出每个预测的详细信息
    print(f"总共有 {len(predictions['predictions'])} 个检测结果")
    print("\n前2个检测结果的详细信息:")
    for i, pred in enumerate(predictions["predictions"][:2]):
        print(f"检测 #{i+1}:", json.dumps(pred, indent=2))

# 定义非常低的置信度阈值来捕获更多可能的盲道
CONFIDENCE_THRESHOLD = 0.2  # 降低到0.1以捕获更多可能的盲道

# 添加缺失的类别映射字典
# 创建类别ID到名称的映射，根据YAML文件中的定义
# nc: 5
# names: ['2', '3', '4', 'go', 'stop']
CLASS_NAMES = {
    0: "两通",    # 盲道类型2
    1: "三通",    # 盲道类型3
    2: "四通",    # 盲道类型4
    3: "go",   # 通行信号
    4: "stop", # 停止信号
}

# 图像预处理函数 - 增强版
def preprocess_image(image, enhancement_type="all"):
    results = []
    
    if enhancement_type in ["brightness", "all"]:
        # 亮度增强
        bright = cv2.convertScaleAbs(image, alpha=1.3, beta=30)
        results.append(bright)
        
    if enhancement_type in ["contrast", "all"]:
        # 对比度增强
        contrast = cv2.convertScaleAbs(image, alpha=1.5, beta=0)
        results.append(contrast)
        
    if enhancement_type in ["sharpen", "all"]:
        # 锐化
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpen = cv2.filter2D(image, -1, kernel)
        results.append(sharpen)
        
    if enhancement_type in ["edges", "all"]:
        # 边缘增强
        edges = cv2.Canny(image, 100, 200)
        edges_3channel = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        results.append(edges_3channel)
    
    if enhancement_type == "all":
        return results
    else:
        return results[0] if results else image

# 简单的IoU计算函数
def calculate_iou(box1, box2):
    """计算两个边界框的IoU (Intersection over Union)"""
    # 解析边界框坐标
    x1_min, y1_min, x1_max, y1_max = box1
    x2_min, y2_min, x2_max, y2_max = box2
    
    # 计算交集矩形的坐标
    x_min = max(x1_min, x2_min)
    y_min = max(y1_min, y2_min)
    x_max = min(x1_max, x2_max)
    y_max = min(y1_max, y2_max)
    
    # 计算交集面积
    if x_max < x_min or y_max < y_min:
        return 0.0  # 没有交集
    
    intersection = (x_max - x_min) * (y_max - y_min)
    
    # 计算两个边界框的面积
    area1 = (x1_max - x1_min) * (y1_max - y1_min)
    area2 = (x2_max - x2_min) * (y2_max - y2_min)
    
    # 计算并集面积
    union = area1 + area2 - intersection
    
    # 返回IoU
    return intersection / union if union > 0 else 0.0

# 非极大值抑制函数
def non_max_suppression(boxes, confidences, class_ids, iou_threshold=0.5):
    """
    实现非极大值抑制
    Args:
        boxes: 边界框坐标 [N, 4]
        confidences: 置信度值 [N]
        class_ids: 类别ID [N]
        iou_threshold: IoU阈值
    Returns:
        保留的框的索引列表
    """
    # 如果没有框，返回空列表
    if len(boxes) == 0:
        return []
    
    # 初始化要保留的索引列表
    keep = []
    
    # 按照置信度排序索引
    sorted_indices = np.argsort(confidences)[::-1]
    
    # 循环处理所有框
    while len(sorted_indices) > 0:
        # 取置信度最高的框
        current_index = sorted_indices[0]
        keep.append(current_index)
        
        # 如果只剩一个框，退出循环
        if len(sorted_indices) == 1:
            break
        
        # 删除当前处理的框
        sorted_indices = sorted_indices[1:]
        
        # 计算其余框与当前框的IoU
        current_box = boxes[current_index]
        overlapping_indices = []
        
        for i, idx in enumerate(sorted_indices):
            if calculate_iou(current_box, boxes[idx]) > iou_threshold:
                overlapping_indices.append(i)
        
        # 删除与当前框重叠的框
        sorted_indices = np.delete(sorted_indices, overlapping_indices)
    
    return keep

# 读取图像
image_file = "2.jpg"
image = cv2.imread(image_file)
if image is None:
    print(f"错误：无法加载图像文件 {image_file}")
    exit()

# 加载模型
model = get_model(model_id="next-level-i0lpn/3")

# 对原始图像进行推理并打印调试信息
print("\n===== 模型信息 =====")
print("模型ID: next-level-i0lpn/3")
print("模型类型:", type(model))

results = model.infer(image)
result_dict = results[0].model_dump(by_alias=True, exclude_none=True)
debug_predictions(result_dict, "原始图像检测结果")

# 应用多种图像预处理，获取不同增强效果的图像
processed_images = preprocess_image(image, enhancement_type="all")
# 添加原图到处理列表中
processed_images.append(image)

# 创建一个空的检测结果列表
all_detections = []

# 对每个预处理的图像进行多尺度检测
for idx, img in enumerate(processed_images):
    print(f"处理图像变体 {idx+1}/{len(processed_images)}")
    
    # 原始尺寸检测
    result = model.infer(img, confidence=CONFIDENCE_THRESHOLD)
    detection = sv.Detections.from_inference(result[0].model_dump(by_alias=True, exclude_none=True))
    all_detections.append(detection)
    
    # 尺度变换检测 - 放大图像
    h, w = img.shape[:2]
    img_scaled_larger = cv2.resize(img, (int(w*1.5), int(h*1.5)))
    result_larger = model.infer(img_scaled_larger, confidence=CONFIDENCE_THRESHOLD)
    detection_larger = sv.Detections.from_inference(result_larger[0].model_dump(by_alias=True, exclude_none=True))
    # 需要调整边界框坐标以匹配原图尺寸
    if len(detection_larger.xyxy) > 0:
        detection_larger.xyxy = detection_larger.xyxy * np.array([w/(w*1.5), h/(h*1.5), w/(w*1.5), h/(h*1.5)])
        all_detections.append(detection_larger)

# 合并所有检测结果
if len(all_detections) > 0:
    # 使用简单的方式合并所有边界框
    all_boxes = []
    all_confidences = []
    all_class_ids = []
    
    for detection in all_detections:
        if len(detection.xyxy) > 0:
            all_boxes.append(detection.xyxy)
            all_confidences.append(detection.confidence)
            all_class_ids.append(detection.class_id)
    
    if all_boxes:
        # 将所有列表连接起来
        all_boxes = np.vstack(all_boxes)
        all_confidences = np.concatenate(all_confidences)
        all_class_ids = np.concatenate(all_class_ids)
        
        # 打印类别ID的统计信息
        unique_class_ids = np.unique(all_class_ids)
        print("\n===== 合并后检测到的类别ID =====")
        print("唯一类别ID:", unique_class_ids)
        for class_id in unique_class_ids:
            count = np.sum(all_class_ids == class_id)
            print(f"类别ID {class_id} 的检测数量: {count}")
        
        # 创建合并后的检测结果
        merged_detections = sv.Detections(
            xyxy=all_boxes,
            confidence=all_confidences,
            class_id=all_class_ids
        )
        
        # 应用自定义的非极大值抑制
        iou_threshold = 0.5
        keep_indices = non_max_suppression(
            merged_detections.xyxy, 
            merged_detections.confidence, 
            merged_detections.class_id, 
            iou_threshold
        )
        
        # 保留未重叠或重叠中置信度最高的检测结果
        merged_detections = sv.Detections(
            xyxy=merged_detections.xyxy[keep_indices],
            confidence=merged_detections.confidence[keep_indices],
            class_id=merged_detections.class_id[keep_indices]
        )
    else:
        print("所有处理图像均未检测到盲道")
        merged_detections = sv.Detections.empty()
else:
    print("没有检测到任何盲道区域")
    merged_detections = sv.Detections.empty()

# 重写类别ID为自定义名称
custom_labels = []
for i, class_id in enumerate(merged_detections.class_id):
    class_id_int = int(class_id)
    class_name = CLASS_NAMES.get(class_id_int, f"未知类别{class_id_int}")
    confidence = merged_detections.confidence[i]
    custom_labels.append(f"{class_name}: {confidence:.2f}")

# 创建标注器
bounding_box_annotator = sv.BoxAnnotator(
    thickness=2,
    color=sv.Color.RED
)

label_annotator = sv.LabelAnnotator()

# 标注图像
annotated_image = bounding_box_annotator.annotate(
    scene=image, 
    detections=merged_detections
)
# 使用自定义标签显示类别名称而不是ID
annotated_image = label_annotator.annotate(
    scene=annotated_image, 
    detections=merged_detections,
    labels=custom_labels  # 传递自定义标签列表
)

# 显示检测到的盲道数量
print(f"检测到 {len(merged_detections)} 个盲道区域")

# 显示图像
sv.plot_image(annotated_image)

# 保存结果图像
cv2.imwrite("detected_result.jpg", cv2.cvtColor(annotated_image, cv2.COLOR_RGB2BGR))