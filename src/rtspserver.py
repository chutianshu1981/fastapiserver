#!/usr/bin/env python3
from gi.repository import Gst, GstRtspServer, GLib, GObject
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')


# 自定义媒体工厂，用于处理客户端推流


class PushedStreamFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self):
        GstRtspServer.RTSPMediaFactory.__init__(self)
        print("PushedStreamFactory initialized.")

    # 这个方法在客户端通过 ANNOUNCE 请求新的媒体会话时被调用
    # url 参数包含了客户端请求的路径信息
    def do_create_element(self, url):
        # 这是 GStreamer pipeline 的描述字符串。
        # 当 Android 应用推流 (H.264) 过来时，这个 pipeline 会被创建来处理接收到的 RTP 包。
        # gst-rtsp-server 框架会自动处理 RTP/UDP 的监听和接收。
        # 我们定义的 pipeline 从 rtph264depay 开始，它负责从 RTP 包中提取 H.264 数据。
        #
        # 选项1: 解码并显示视频 (如果服务器有桌面环境)
        # pipeline_str = "( rtph264depay name=depay ! h264parse ! avdec_h264 name=decode ! videoconvert ! autovideosink sync=false )"
        #
        # 选项2: 仅解析 H.264 流并丢弃，用于测试连通性和基本的数据流 (更轻量)
        pipeline_str = "( rtph264depay name=depay ! h264parse ! fakesink name=sink async=false enable-last-sample=false )"
        #
        # 选项3: 如果你想在服务器端录制成文件
        # pipeline_str = "( rtph264depay name=depay ! h264parse ! mp4mux ! filesink location=received_stream.mp4 )"

        print(f"Client announced to URL: {url.get_request_uri()}")
        print(f"Creating server-side processing pipeline: {pipeline_str}")

        # 解析 pipeline 字符串并创建 GStreamer pipeline 实例
        # GError 会在解析失败时被抛出
        try:
            pipeline = Gst.parse_launch(pipeline_str)
            print("Pipeline parsed successfully.")

            # 你可以在这里连接到 pipeline 中元素的信号，例如 'eos' 或 'error'
            # bus = pipeline.get_bus()
            # bus.add_signal_watch()
            # bus.connect("message::error", self.on_error)
            # bus.connect("message::eos", self.on_eos)

            return pipeline
        except GLib.Error as e:
            print(f"Failed to parse launch pipeline: {e}")
            return None

    # def on_error(self, bus, message):
    #     err, debug = message.parse_error()
    #     print(f"Error received from element {message.src.get_name()}: {err.message}")
    #     print(f"Debugging information: {debug if debug else 'none'}")

    # def on_eos(self, bus, message):
    #     print(f"EOS reached for stream from {message.src.get_name()}")


def main():

    # 初始化 GStreamer
    Gst.init(None)
    # GLib 主循环
    loop = GLib.MainLoop()

    # 创建 RTSP 服务器实例
    server = GstRtspServer.RTSPServer()
    server.set_service("8554")  # 设置 RTSP 服务监听的端口

    # 获取服务器的挂载点对象
    mounts = server.get_mount_points()

    # 创建我们的自定义媒体工厂
    factory = PushedStreamFactory()
    # 设置为共享，这样一个工厂实例可以服务于多个客户端会话
    # 对于推流，通常每个客户端推自己的流，但共享工厂是标准做法
    factory.set_shared(True)
    # 当客户端使用 ANNOUNCE 方法推流到这个路径时，工厂的 do_create_element 将被调用
    factory.set_transport_mode(GstRtspServer.RTSPTransportMode.RECORD)
    mount_point = "/push"
    mounts.add_factory(mount_point, factory)

    # 将服务器附加到主上下文中，这会启动服务器的socket监听
    server.attach(None)

    server_ip = "0.0.0.0"  # 监听所有网络接口
    # 你可能需要找到你的实际局域网 IP 地址告诉 Android 客户端
    # 在 Linux 上可以用 `ip addr` 或 `hostname -I`
    # 在 macOS 上可以用 `ipconfig getifaddr en0` (或其他接口)
    print(
        f"RTSP server listening for PUSH streams on rtsp://<your-server-ip>:8554{mount_point}")
    print(f"Android app should be configured to ANNOUNCE and RECORD to this URL.")
    print("Using processing pipeline: ( rtph264depay name=depay ! h264parse ! fakesink name=sink async=false enable-last-sample=false )")
    print("Press Ctrl+C to stop the server.")

    try:
        loop.run()
    except KeyboardInterrupt:
        print("Stopping server...")
    finally:
        # 清理资源 (虽然在简单脚本中可能不严格需要，但良好实践)
        # GstRtspServer.RTSPMountPoints.remove_factory() 可能需要如果动态管理
        # server.detach() # server.attach(None) 的逆操作似乎不直接存在或这样调用
        print("Server stopped.")


if __name__ == '__main__':
    main()
