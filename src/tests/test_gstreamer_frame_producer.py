import pytest
import queue
import time
import numpy as np
from datetime import datetime
from unittest.mock import MagicMock

from app.services.gstreamer_frame_producer import GStreamerFrameProducer
# VideoFrame 通常在 inference.core.interfaces.camera.entities 中
# 根据你的实际项目结构调整导入
from inference.core.interfaces.camera.entities import VideoFrame, SourceProperties

@pytest.fixture
def frame_queue():
    return queue.Queue()

@pytest.fixture
def producer(frame_queue):
    # 使用具体的fps, width, height值进行初始化
    p = GStreamerFrameProducer(frame_queue, fps=30.0, width=640, height=480, source_id=1)
    return p

def test_producer_initialization(producer: GStreamerFrameProducer, frame_queue: queue.Queue):
    assert producer.frame_queue == frame_queue
    assert producer.running is False
    assert producer._fps == 30.0
    assert producer._width == 640
    assert producer._height == 480
    assert producer._source_id == 1
    assert producer.frame_id_counter == 0

def test_start_producer(producer: GStreamerFrameProducer):
    producer.start()
    assert producer.running is True

def test_read_frame_success(producer: GStreamerFrameProducer, frame_queue: queue.Queue):
    producer.start()
    mock_frame_data = np.random.randint(0, 255, size=(480, 640, 3), dtype=np.uint8)
    # 模拟纳秒级时间戳
    mock_timestamp_ns = time.time_ns()
    frame_queue.put((mock_frame_data, mock_timestamp_ns))

    video_frame = producer.read_frame()

    assert video_frame is not None
    assert isinstance(video_frame, VideoFrame)
    np.testing.assert_array_equal(video_frame.image, mock_frame_data)
    assert video_frame.frame_id == 1
    # 比较 datetime 对象时，允许一定的误差，或者只比较到秒
    expected_dt = datetime.fromtimestamp(mock_timestamp_ns / 1_000_000_000)
    assert video_frame.frame_timestamp is not None
    assert abs((video_frame.frame_timestamp - expected_dt).total_seconds()) < 0.001 
    assert video_frame.source_id == 1
    assert producer.frame_id_counter == 1

def test_read_frame_empty_queue(producer: GStreamerFrameProducer):
    producer.start()
    video_frame = producer.read_frame() # Queue is empty, timeout after 1s
    assert video_frame is None

def test_read_frame_not_running(producer: GStreamerFrameProducer, frame_queue: queue.Queue):
    # producer.running is False by default
    mock_frame_data = np.zeros((100, 100, 3), dtype=np.uint8)
    frame_queue.put((mock_frame_data, time.time_ns()))
    video_frame = producer.read_frame()
    assert video_frame is None

def test_read_frame_timestamp_conversion_error(producer: GStreamerFrameProducer, frame_queue: queue.Queue, caplog):
    producer.start()
    mock_frame_data = np.random.randint(0, 255, size=(480, 640, 3), dtype=np.uint8)
    # 提供一个会导致转换错误的无效时间戳
    invalid_timestamp_ns = "not_a_timestamp"
    frame_queue.put((mock_frame_data, invalid_timestamp_ns))

    # 记录开始时间，用于比较回退的时间戳
    time_before_read = datetime.now()
    video_frame = producer.read_frame()
    time_after_read = datetime.now()

    assert video_frame is not None
    assert "Error converting timestamp_ns" in caplog.text
    assert "Falling back to current time" in caplog.text
    # 检查回退的时间戳是否在调用read_frame的合理范围内
    assert time_before_read <= video_frame.frame_timestamp <= time_after_read

def test_read_frame_none_timestamp(producer: GStreamerFrameProducer, frame_queue: queue.Queue, caplog):
    producer.start()
    mock_frame_data = np.random.randint(0, 255, size=(480, 640, 3), dtype=np.uint8)
    frame_queue.put((mock_frame_data, None)) # None timestamp

    time_before_read = datetime.now()
    video_frame = producer.read_frame()
    time_after_read = datetime.now()

    assert video_frame is not None
    assert "timestamp_ns is None" in caplog.text
    assert "Falling back to current time for VideoFrame" in caplog.text
    assert time_before_read <= video_frame.frame_timestamp <= time_after_read

def test_release_clears_queue(producer: GStreamerFrameProducer, frame_queue: queue.Queue):
    producer.start()
    frame_queue.put((np.zeros(1), time.time_ns()))
    frame_queue.put((np.zeros(1), time.time_ns()))
    assert frame_queue.qsize() == 2

    producer.release()
    # producer.running remains True as per implementation for persistent source
    assert producer.running is True 
    assert frame_queue.empty()

def test_get_fps(producer: GStreamerFrameProducer):
    assert producer.get_fps() == 30.0

def test_get_resolution(producer: GStreamerFrameProducer):
    assert producer.get_resolution() == (640, 480)

def test_is_opened(producer: GStreamerFrameProducer):
    assert producer.isOpened() is False
    producer.start()
    assert producer.isOpened() is True

def test_grab_and_retrieve(producer: GStreamerFrameProducer, frame_queue: queue.Queue):
    producer.start()
    mock_frame_data = np.random.randint(0, 255, size=(480, 640, 3), dtype=np.uint8)
    mock_timestamp_ns = time.time_ns()
    frame_queue.put((mock_frame_data, mock_timestamp_ns))

    assert producer.grab() is True
    assert producer._last_read_video_frame is not None # Internal check for state after grab
    
    retrieved, frame_array = producer.retrieve()
    assert retrieved is True
    assert frame_array is not None
    np.testing.assert_array_equal(frame_array, mock_frame_data)
    assert producer._last_read_video_frame is None # Should be cleared after retrieve

    # Check cached metadata
    expected_dt = datetime.fromtimestamp(mock_timestamp_ns / 1_000_000_000)
    assert producer.get_frame_id() == 1 # frame_id_counter was 1
    producer_frame_timestamp = producer.get_frame_timestamp()
    assert producer_frame_timestamp is not None
    assert abs((producer_frame_timestamp - expected_dt).total_seconds()) < 0.001

def test_grab_fail_empty_queue(producer: GStreamerFrameProducer):
    producer.start()
    assert producer.grab() is False
    assert producer._last_read_video_frame is None

def test_retrieve_fail_nothing_grabbed(producer: GStreamerFrameProducer):
    producer.start()
    retrieved, frame_array = producer.retrieve()
    assert retrieved is False
    assert frame_array is None

def test_grab_not_running(producer: GStreamerFrameProducer):
    assert producer.grab() is False

def test_discover_source_properties(producer: GStreamerFrameProducer):
    props = producer.discover_source_properties()
    assert isinstance(props, SourceProperties)
    assert props.width == 640
    assert props.height == 480
    assert props.fps == 30.0
    assert props.total_frames == 0 # As per implementation for live stream
    assert props.is_file is False 