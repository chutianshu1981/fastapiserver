# Windows 11 下开发环境搭建

虽然本项目核心依赖 GStreamer 和 PyGObject 在 Windows 上原生安装较为复杂，但通过结合使用 **Docker Desktop** 和 **WSL 2 (Windows Subsystem for Linux version 2)**，你完全可以在 Windows 11 系统上进行高效、一致的开发，而**无需**在 Windows 主机上直接安装这些复杂的依赖。

本指南将引导你完成在 Windows 11 上设置开发环境的步骤。

## 1. 系统与软件先决条件

在开始之前，请确保你的 Windows 11 系统满足以下条件并已安装相应软件：

*   **Windows 11 版本:** 64 位 Home、Pro、Education 或 Enterprise 版本，建议为 22H2 或更高版本。
*   **硬件虚拟化:** 在 BIOS/UEFI 设置中已启用硬件虚拟化（通常称为 VT-x, AMD-V 等）。
*   **WSL 2:**
    *   已安装并启用 WSL 2。
    *   已从 Microsoft Store 安装至少一个 Linux 发行版（推荐 **Ubuntu**）并确保其运行在 WSL 2 模式下。可以通过在 PowerShell 或 CMD 中运行 `wsl -l -v` 来检查版本。如果版本为 1，请使用 `wsl --set-version <DistroName> 2` 进行升级。
*   **Docker Desktop for Windows:**
    *   已安装最新版本。
    *   在 Docker Desktop 设置中，已启用 **WSL 2 based engine**。
    *   在 Docker Desktop 的 `Settings > Resources > WSL Integration` 中，已启用与你安装的 WSL 2 发行版（如 Ubuntu）的集成。
*   **Git:** 用于克隆项目代码库。Windows 主机上可以从 [git-scm.com](https://git-scm.com/) 下载安装，但开发将主要在 WSL 中进行，WSL 发行版通常已预装 Git。
*   **代码编辑器:** 推荐使用 **Visual Studio Code (VS Code)**，并安装以下扩展：
    *   **Remote - WSL:** 用于连接到 WSL 环境进行开发。
    *   **Docker:** 用于管理容器和镜像。
    *   **(可选) Python:** 提供 Python 语言支持。

## 2. 环境设置步骤

1.  **验证先决条件:** 确保上述所有软件已正确安装和配置。特别是 Docker Desktop 的 WSL 2 集成设置。
2.  **克隆项目代码库 (重要):**
    *   打开你的 WSL 2 发行版终端（例如，通过开始菜单启动 Ubuntu）。
    *   导航到你希望存放项目代码的位置。**强烈建议将代码存储在 WSL 2 的文件系统内**（例如 `/home/<your_username>/projects/`），而不是 Windows 的 C: 盘或其他盘符下，以获得最佳的 Docker 文件挂载性能。
    *   运行 `git clone <repository_url>` 克隆项目。
    *   使用 `cd <project_directory>` 进入项目根目录。
3.  **安装和配置系统 Python(在 WSL 2 环境中):**

    *   **安装系统 Python:** 确保使用系统级 Python：
        ```bash
        # 在 WSL 2 终端中执行
        sudo apt update
        sudo apt install -y python3 python3-pip python3-venv python3-dev
        
        # 验证安装
        python3 --version
        pip3 --version
        ```

    *   **配置 Python 别名 (可选):** 添加别名以便直接使用 `python` 命令：
        ```bash
        # 添加到 ~/.bashrc 或 ~/.zshrc
        echo 'alias python=python3' >> ~/.bashrc
        echo 'alias pip=pip3' >> ~/.bashrc
        source ~/.bashrc
        ```

    *   **使用 Deadsnakes PPA 安装特定版本的 Python (如果需要 Python 3.12):**
        如果你的系统未提供 Python 3.12，可以通过 Deadsnakes PPA 安装：
        ```bash
        # 添加 deadsnakes PPA 仓库
        sudo add-apt-repository ppa:deadsnakes/ppa
        sudo apt update
        
        # 安装 Python 3.12 及相关组件
        sudo apt install -y python3.12 python3.12-venv python3.12-distutils
        
        # 设置为系统默认 Python (可选)
        sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1
        sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
        
        # 验证安装
        python --version  # 应显示 Python 3.12.x
        python3 --version  # 应显示 Python 3.12.x
        ```

    *   **安装 pip 用于 Python 3.12 (如果使用 Deadsnakes PPA):**
        ```bash
        # 检查 Python 3.12 是否已有 pip
        python3.12 -m pip --version
        
        # 如果提示 "No module named pip"，则安装 pip
        curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12
        
        # 验证安装
        python3.12 -m pip --version
        
        # 如需为默认 python 命令配置 pip
        python -m pip --version
        # 如果不可用，则运行
        curl -sS https://bootstrap.pypa.io/get-pip.py | python
        ```

    *   **安装 pipx:** 使用系统 Python 安装 pipx 用于隔离环境安装 Python 应用：
        ```bash
        # 安装 pipx
        python -m pip install --user pipx
        python -m pipx ensurepath
        
        # 重新加载环境变量（或重启终端）
        source ~/.bashrc
        
        # 验证安装
        pipx --version
        ```
        
    *   **依赖管理选项:**
    
        **选项 1: PDM (Python Dependency Manager)** - 推荐用于复杂项目:
        ```bash
        # 使用 pipx 安装 PDM
        pipx install pdm
        
        # 验证安装
        pdm --version
        
        # 配置 PDM 使用 uv 作为安装器 (推荐，提升依赖安装速度)
        pdm config use_uv true
        
        # 验证 PDM 是否已配置使用 uv
        pdm config | grep use_uv
        
        # 进入项目目录并设置依赖
        cd 项目目录
        
        # 如果项目尚未初始化
        pdm init
        # 或导入现有的 requirements.txt
        # pdm import requirements.txt
        
        # 安装项目依赖
        pdm install
        
        # 激活 PDM 管理的虚拟环境
        eval $(pdm venv activate)
        ```

        **注意: GStreamer 和 PyGObject 依赖处理**
        对于 GStreamer 和 PyGObject 相关库，不应通过 PDM 安装和管理，而应通过系统包管理器安装:
        
        ```bash
        # 安装 GStreamer 和 PyGObject 相关系统库
        sudo apt install -y \
            gstreamer1.0-plugins-base \
            gstreamer1.0-plugins-good \
            gstreamer1.0-plugins-bad \
            gstreamer1.0-plugins-ugly \
            gstreamer1.0-tools \
            gstreamer1.0-rtsp \
            libgstrtspserver-1.0-dev \
            python3-gi \
            python3-gi-cairo \
            gir1.2-gstreamer-1.0 \
            gir1.2-gst-plugins-base-1.0 \
            libgirepository1.0-dev
        
        # 创建带系统站点包的虚拟环境以访问系统级 GStreamer 绑定
        python -m venv .venv --system-site-packages
        
        # 告知 PDM 使用此虚拟环境
        eval $(pdm venv activate)
        ```
        
        在 pyproject.toml 文件中，应将 GStreamer 相关依赖通过注释标记为系统依赖，而不是直接的 PDM 依赖:
        ```toml
        [project]
        dependencies = [
            # 其他依赖...
            # 以下库通过系统包管理器安装，不作为 PDM 依赖：
            # "PyGObject>=3.42.0",  # 通过 python3-gi 系统包提供
            # "pycairo>=1.20.0"     # 通过 python3-gi-cairo 系统包提供
        ]
        ```

        常用 PDM 命令:
        - 添加依赖：`pdm add package_name`
        - 移除依赖：`pdm remove package_name`
        - 更新依赖：`pdm update [package_name]`
    
    *   **VSCode Python 解释器配置:**
        在 VSCode 中，确保选择正确的 Python 解释器:
        1. 按 `Ctrl+Shift+P` 打开命令面板
        2. 输入 "Python: Select Interpreter"
        3. 选择你刚创建的虚拟环境中的 Python 解释器
           (通常位于项目目录下的 `.venv/bin/python` 或类似路径)

4.  **在 VS Code 中打开项目:**
    *   在 WSL 终端的项目根目录下，运行 `code .`。
    *   VS Code 将启动，并自动使用 Remote - WSL 扩展连接到你的 WSL 环境。你可以在 VS Code 的左下角看到 "WSL: Ubuntu" (或你的发行版名称) 的标识。


5.  **构建并运行 Docker 容器:**
    *   创建docker 镜像的配置文件 `docker/Dockerfile` 和 `docker/docker-compose.yml`
    *   运行 Docker Compose 命令来构建镜像并启动服务：
        ```bash
        docker compose up --build -d
        ```
        *   `--build` 确保 Docker 根据 `docker/Dockerfile` 构建或重新构建镜像，这会安装 Debian 包（包括 GStreamer 和 python3-gi）以及使用 PDM 安装 Python 依赖。
        *   `-d` 让容器在后台运行。
    *   你可以使用 `docker compose logs -f` 来查看容器的实时日志。

6.  **访问应用:**
    *   容器启动后，FastAPI 服务将在容器的 8000 端口运行。Docker Desktop 会自动将此端口映射到你的 Windows 主机。
    *   在你的 Windows 浏览器中访问 `http://localhost:58000/status` 或 `http://localhost:58000/health` 来检查服务是否正常运行。
    *   RTSP 流可以通过 `rtsp://localhost:554/live` (或其他配置的 IP 地址) 访问。

## 3. 开发工作流

*   **代码编辑:** 直接在 VS Code 中编辑位于 WSL 文件系统内的项目代码。
*   **依赖管理:**
    *   所有依赖管理操作都在 WSL 环境中进行。
    *   添加/更新依赖：在 VS Code 的 WSL 终端中使用 `pdm add <package_name>` 或 `pdm update <package_name>`。
    *   对于 GStreamer 相关依赖，应通过 `sudo apt install` 在系统级别安装。
    *   修改一般 Python 依赖后，需要重新构建 Docker 镜像以包含新的依赖：`docker compose up --build -d`。
    *   如在系统级安装了新的 GStreamer 组件，同样需要更新 Dockerfile 并重新构建容器。
*   **查看更改:** 对于 FastAPI 应用，Uvicorn 通常配置了热重载。修改 Python 代码后，服务会自动重启（在容器内）。你可以在 `docker compose logs -f` 中观察到。
*   **调试:** 可以配置 VS Code 的调试器以附加到在 Docker 容器内运行的 Python 进程。
*   **停止服务:** 在项目目录下的 WSL 终端中运行 `docker compose down`。

## 4. 关键注意事项

*   **文件存储位置:** 再次强调，将项目文件放在 WSL 2 文件系统内对于 Docker 的性能至关重要。
*   **开发环境与容器环境:** 
    *   WSL 2 中的 PDM 和 uv 是用于管理项目依赖的开发工具。
    *   实际的应用程序将在 Docker 容器中运行，这个容器有自己的 Python 环境（基于 Debian Bookworm）和 GStreamer 安装。
    *   容器中会使用项目根目录的 pyproject.toml 和 pdm.lock 文件来安装所需的依赖。
    *   GStreamer 相关库在容器中也是通过系统包管理器安装的，而不是通过 PDM 安装。
*   **Python 版本兼容性:** 
    *   确保本地开发环境和容器环境使用相同的 Python 版本（推荐 Python 3.12）。
    *   确保 pyproject.toml 中的 `requires-python` 设置为 `>=3.12,<3.13`。
*   **终端使用:** 所有开发相关的命令（如 `pdm`、`docker compose` 等）都应在 WSL 终端或 VS Code 的 WSL 集成终端中运行，而不是在 Windows 的 CMD 或 PowerShell 中运行。
*   **无需在 Windows 上原生安装:** 你不需要在 Windows 11 主机上安装 Python、GStreamer、PyGObject 或相关的 C 编译器和库。所有这些都由 WSL 2 和 Docker 容器环境处理。

通过遵循这些步骤，你可以利用 Docker 和 WSL 2 在 Windows 11 上创建一个与 Linux 部署环境高度一致且高效的开发环境。

``` sh

 eval $(pdm venv activate)    

 export GST_DEBUG=3,GstRtspServer:4,rtsp*:4,rtspsrc:4,udpsrc:4

 pdm run uvicorn app.main:app --reload --host 0.0.0.0 --port 58000   
```

https://inference.roboflow.com/using_inference/inference_pipeline/#migrate-to-changes-introduced-in-v0918


## 服务器端直接测试 websocket 连接

``` sh
npm install -g wscat   # 安装 wscat ，用来测试 websocket 连接的工具
wscat -c ws://localhost:58000/api/v1/ws # 在服务器上直接测试连接 websocket 端口

# 测试结果数据：
Connected (press CTRL+C to quit)
< {"type":"connection_status","status":"connected","message":"成功连接到AI分析服务器","timestamp":1747904370661,"client_id":"9792cead-718f-41de-ae04-c1ba1c25b617"}
< {"type":"ping","timestamp":1747904370661}
< {"type":"ai_detection","data":{"frame_id":323,"timestamp":1747904370722,"fps":0.0,"detections":[{"class_name":"go","confidence":0.18677446246147156,"x_center":0.775,"y_center":0.6645833333333333,"width":0.446875,"height":0.6666666666666666}]}}
< {"type":"ai_detection","data":{"frame_id":325,"timestamp":1747904370927,"fps":0.0,"detections":[{"class_name":"go","confidence":0.18040060997009277,"x_center":0.7796875,"y_center":0.5895833333333333,"width":0.4375,"height":0.8208333333333333}]}}
< {"type":"ai_detection","data":{"frame_id":326,"timestamp":1747904371028,"fps":0.0,"detections":[{"class_name":"go","confidence":0.6817727088928223,"x_center":0.05703125,"y_center":0.23125,"width":0.1140625,"height":0.4583333333333333},{"class_name":"go","confidence":0.22519731521606445,"x_center":0.78125,"y_center":0.6010416666666667,"width":0.434375,"height":0.7979166666666667}]}}
< {"type":"ai_detection","data":{"frame_id":328,"timestamp":1747904371220,"fps":0.0,"detections":[{"class_name":"go","confidence":0.6238487362861633,"x_center":0.05859375,"y_center":0.2375,"width":0.1171875,"height":0.4666666666666667},{"class_name":"go","confidence":0.12461790442466736,"x_center":0.78515625,"y_center":0.6,"width":0.4234375,"height":0.8}]}}
< {"type":"ai_detection","data":{"frame_id":330,"timestamp":1747904371416,"fps":0.0,"detections":[]}}
< {"type":"ai_detection","data":{"frame_id":332,"timestamp":1747904371609,"fps":0.0,"detections":[{"class_name":"go","confidence":0.12414422631263733,"x_center":0.6078125,"y_center":0.09270833333333334,"width":0.05625,"height":0.18541666666666667}]}}
< {"type":"ai_detection","data":{"frame_id":333,"timestamp":1747904371718,"fps":0.0,"detections":[{"class_name":"go","confidence":0.408886194229126,"x_center":0.6078125,"y_center":0.10104166666666667,"width":0.05625,"height":0.20208333333333334}]}}
< {"type":"ai_detection","data":{"frame_id":335,"timestamp":1747904371908,"fps":0.0,"detections":[{"class_name":"go","confidence":0.26044797897338867,"x_center":0.20859375,"y_center":0.46979166666666666,"width":0.4140625,"height":0.8770833333333333}]}}
< {"type":"ai_detection","data":{"frame_id":337,"timestamp":1747904372089,"fps":0.0,"detections":[]}}
< {"type":"ai_detection","data":{"frame_id":339,"timestamp":1747904372305,"fps":0.0,"detections":[{"class_name":"go","confidence":0.23472419381141663,"x_center":0.98125,"y_center":0.5291666666666667,"width":0.0375,"height":0.10833333333333334}]}}

```

nc: 5
names: ['2', '3', '4', 'go', 'stop']