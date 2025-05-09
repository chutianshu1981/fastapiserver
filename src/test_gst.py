import gi
from gi.repository import Gst
gi.require_version('Gst', '1.0')
Gst.init(None)
print(f"GStreamer 版本: {Gst.version_string()}")
print("GStreamer 初始化成功")
