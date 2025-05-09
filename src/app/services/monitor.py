"""
监控和诊断模块

提供性能指标收集、资源使用监控和故障检测功能。
"""

import asyncio
import logging
import os
import psutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    disk_usage_percent: float
    fps: float
    frame_latency: float
    error_count: int


class SystemMonitor:
    """系统监控器

    监控系统资源使用情况，收集性能指标，检测潜在问题。
    """

    def __init__(
        self,
        check_interval: int = 5,
        metrics_history_size: int = 1000,
        alert_cpu_threshold: float = 80.0,
        alert_memory_threshold: float = 80.0,
        alert_disk_threshold: float = 90.0
    ):
        """
        Args:
            check_interval: 检查间隔(秒)
            metrics_history_size: 保留的历史指标数量
            alert_cpu_threshold: CPU使用率告警阈值(%)
            alert_memory_threshold: 内存使用率告警阈值(%)
            alert_disk_threshold: 磁盘使用率告警阈值(%)
        """
        self.check_interval = check_interval
        self.metrics_history_size = metrics_history_size
        self.alert_thresholds = {
            'cpu': alert_cpu_threshold,
            'memory': alert_memory_threshold,
            'disk': alert_disk_threshold
        }

        # 性能指标存储
        self._metrics_history: List[PerformanceMetrics] = []
        self._processing_stats = {
            'total_frames': 0,
            'error_count': 0,
            'start_time': time.time(),
            'last_frame_time': 0.0
        }

        # 初始化第一个指标
        self._update_metrics(0.0)  # 使用0作为初始延迟

        # 监控任务
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

    def _update_metrics(self, latency: float) -> None:
        """更新性能指标

        Args:
            latency: 处理延迟(秒)
        """
        current_time = time.time()
        elapsed = current_time - self._processing_stats['start_time']
        fps = self._processing_stats['total_frames'] / max(elapsed, 0.001)

        metrics = PerformanceMetrics(
            timestamp=current_time,
            cpu_percent=psutil.cpu_percent(),
            memory_percent=psutil.virtual_memory().percent,
            disk_usage_percent=psutil.disk_usage('/').percent,
            fps=fps,
            frame_latency=latency,
            error_count=self._processing_stats['error_count']
        )

        self._metrics_history.append(metrics)
        if len(self._metrics_history) > self.metrics_history_size:
            self._metrics_history.pop(0)

    def record_frame_processed(self, latency: float) -> None:
        """记录帧处理完成

        Args:
            latency: 处理延迟(秒)
        """
        self._processing_stats['total_frames'] += 1
        self._processing_stats['last_frame_time'] = time.time()
        self._update_metrics(latency)

    def record_error(self) -> None:
        """记录处理错误"""
        self._processing_stats['error_count'] += 1
        logger.debug(f"错误计数增加至: {self._processing_stats['error_count']}")

        # 获取当前延迟，如果没有历史指标则使用0
        current_metrics = self.get_current_metrics()
        current_latency = 0.0
        if current_metrics:
            current_latency = current_metrics.frame_latency

        # 强制更新指标以反映新的错误计数
        self._update_metrics(current_latency)

    def get_current_metrics(self) -> Optional[PerformanceMetrics]:
        """获取当前性能指标

        Returns:
            Optional[PerformanceMetrics]: 当前性能指标，如果没有可用指标则返回None
        """
        return self._metrics_history[-1] if self._metrics_history else None

    def get_metrics_history(self) -> List[PerformanceMetrics]:
        """获取历史性能指标

        Returns:
            List[PerformanceMetrics]: 性能指标历史记录列表
        """
        return self._metrics_history.copy()

    async def _monitor_loop(self) -> None:
        """监控循环"""
        while self._running:
            try:
                # 检查系统资源使用情况
                current_metrics = self.get_current_metrics()
                if current_metrics:
                    # 检查是否需要告警
                    if current_metrics.cpu_percent > self.alert_thresholds['cpu']:
                        logger.warning(
                            f"CPU使用率过高: {current_metrics.cpu_percent}%")

                    if current_metrics.memory_percent > self.alert_thresholds['memory']:
                        logger.warning(
                            f"内存使用率过高: {current_metrics.memory_percent}%")

                    if current_metrics.disk_usage_percent > self.alert_thresholds['disk']:
                        logger.warning(
                            f"磁盘使用率过高: {current_metrics.disk_usage_percent}%")

                    # 记录处理性能
                    if self._processing_stats['total_frames'] > 0:
                        error_rate = (self._processing_stats['error_count'] /
                                      self._processing_stats['total_frames'] * 100)

                        logger.info(
                            f"处理性能指标 - 平均FPS: {current_metrics.fps:.2f}, "
                            f"错误率: {error_rate:.2f}%, "
                            f"总帧数: {self._processing_stats['total_frames']}"
                        )

            except Exception as e:
                logger.error(f"监控循环异常: {e}")

            await asyncio.sleep(self.check_interval)

    async def start(self) -> None:
        """启动监控"""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("系统监控已启动")

    async def stop(self) -> None:
        """停止监控"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("系统监控已停止")

    def get_health_status(self) -> Dict[str, Any]:
        """获取系统健康状态

        Returns:
            Dict[str, any]: 包含各组件状态的字典
        """
        current_metrics = self.get_current_metrics()

        if not current_metrics:
            return {'status': 'unknown', 'message': '无可用指标'}

        status = {
            'status': 'healthy',
            'metrics': {
                'cpu': f"{current_metrics.cpu_percent}%",
                'memory': f"{current_metrics.memory_percent}%",
                'disk': f"{current_metrics.disk_usage_percent}%",
                'fps': f"{current_metrics.fps:.2f}",
                'error_rate': f"{(self._processing_stats['error_count'] / max(1, self._processing_stats['total_frames']) * 100):.2f}%"
            }
        }

        # 检查是否存在告警条件
        warnings = []

        if current_metrics.cpu_percent > self.alert_thresholds['cpu']:
            warnings.append(f"CPU使用率过高({current_metrics.cpu_percent}%)")

        if current_metrics.memory_percent > self.alert_thresholds['memory']:
            warnings.append(f"内存使用率过高({current_metrics.memory_percent}%)")

        if current_metrics.disk_usage_percent > self.alert_thresholds['disk']:
            warnings.append(f"磁盘使用率过高({current_metrics.disk_usage_percent}%)")

        if warnings:
            status['status'] = 'warning'
            status['warnings'] = warnings

        return status
