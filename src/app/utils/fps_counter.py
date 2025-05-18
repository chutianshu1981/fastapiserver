"""
FPS计数器实用工具

该模块提供FPS计数器，用于计算处理帧率。
"""
import time
from typing import List


class FPSCounter:
    """
    基于时间窗口的FPS计数器

    计算滑动窗口内的平均帧率
    """

    def __init__(self, window_size: int = 30):
        """
        初始化FPS计数器

        Args:
            window_size: 滑动窗口大小(秒)
        """
        self.window_size = window_size
        self.timestamps: List[float] = []

    def tick(self) -> None:
        """
        记录一帧的时间戳
        """
        current_time = time.time()
        self.timestamps.append(current_time)

        # 移除窗口外的时间戳
        while self.timestamps and self.timestamps[0] < current_time - self.window_size:
            self.timestamps.pop(0)

    def get_fps(self) -> float:
        """
        计算当前FPS

        Returns:
            当前帧率
        """
        if len(self.timestamps) < 2:
            return 0.0

        time_diff = self.timestamps[-1] - self.timestamps[0]
        if time_diff == 0:
            return 0.0

        return (len(self.timestamps) - 1) / time_diff
