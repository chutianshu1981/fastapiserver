# SafePath RTSP 服务器项目概述

## 项目简介

SafePath RTSP 服务器是一个基于 FastAPI 和 GStreamer 的现代化服务器应用，专门设计用于接收和处理 SafePath Android 应用推送的 RTSP 视频流。服务器采用异步处理模式，支持高性能视频流接收、处理和存储功能。

## 项目目标

1. 为 SafePath Android 客户端提供可靠的视频流接收端点
2. 实现高性能、低延迟的视频处理
3. 提供简单易用的 API 接口，支持状态监控和视频帧访问
4. 确保系统稳定性和可扩展性

## 技术栈

- **Python 版本**: Python 3.12 (兼顾性能、稳定性和Debian 12系统兼容性)
- **后端框架**: FastAPI (Python 异步 Web 框架)
- **视频处理**: GStreamer 1.22.0 (Debian Bookworm 系统自带版本)
- **图像处理**: OpenCV (通过 pip 安装)
- **数据验证**: Pydantic V2 (高性能数据验证与序列化)
- **依赖管理**: PDM (配合 uv 加速) 使用 pyproject.toml 和 pdm.lock
- **部署**: Docker 和 Docker Compose

## 核心功能

1. **RTSP 流接收**
   - 端口 554，路径 `/live`
   - 支持 H.264 编码格式
   - 多客户端并发连接

2. **视频处理和存储**
   - 视频帧提取与保存
   - 视频片段录制
   - 自动清理过期文件

3. **API 接口**
   - `/status` - 服务器状态信息
   - `/snapshot` - 获取当前视频帧
   - `/videos` - 获取录制的视频列表
   - `/video/{filename}` - 访问特定视频文件
   - `/health` - 健康状态检查

## 项目架构原则

本项目遵循以下架构设计原则：

1. **模块化与单一职责**
   - 每个模块专注于单一功能
   - 文件代码量控制在300行以内，绝不超过500行
   - 通过清晰的接口进行模块间通信

2. **分层架构**
   - API层：处理HTTP请求和响应 (FastAPI, Pydantic V2)
   - 服务层：实现业务逻辑
   - 基础设施层：RTSP服务器(GStreamer系统包)、视频处理(OpenCV)等底层功能
   - 工具层：提供通用辅助功能

3. **高内聚低耦合**
   - 最小化模块间的依赖关系
   - 使用依赖注入降低组件耦合度 (FastAPI内建支持)
   - 避免全局状态和可变共享数据

## 与 Android 客户端集成

本项目专门为 SafePath Android 客户端设计，确保与其 RTSP 推流功能完美兼容。服务器配置与 Android 端的 `RTSP_SERVER_URL` 设置匹配，简化了客户端配置过程。

## 开发重点

- 高性能异步处理
- 资源使用优化
- 可靠的错误处理
- 完善的日志记录
- 容器化部署支持
- 代码模块化和可测试性

## 项目目录结构

```
src/
├── app/                      # 应用程序主目录
│   ├── __init__.py
│   ├── main.py               # 主应用入口 (FastAPI app)
│   ├── api/                  # API层
│   │   ├── __init__.py
│   │   ├── routes.py         # API路由定义
│   │   └── models.py         # Pydantic V2 API数据模型
│   ├── core/                 # 核心配置
│   │   ├── __init__.py
│   │   ├── config.py         # 应用配置 (Pydantic Settings)
│   │   └── logger.py         # 日志配置
│   ├── rtsp/                 # RTSP相关模块
│   │   ├── __init__.py
│   │   └── server.py         # RTSP服务器核心 (使用系统GStreamer)
│   ├── services/             # 服务层
│   │   ├── __init__.py
│   │   └── video_service.py  # 视频处理服务
│   └── utils/                # 工具函数
│       ├── __init__.py
│       └── helpers.py        # 辅助函数
├── videos/                   # 视频存储目录
├── tests/                    # 测试代码
├── docker/                   # Docker相关
├── .github/                  # GitHub相关配置
├── pyproject.toml            # PDM 配置文件
├── pdm.lock                  # PDM 锁文件
└── README.md                 # 项目说明
```