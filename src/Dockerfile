# ---- Stage 1: Builder Stage ----
# 此阶段用于安装 pdm 并构建项目的 Python 依赖环境
FROM python:3.12-slim AS builder

# 配置 APT 使用阿里云镜像
RUN echo "deb https://mirrors.aliyun.com/debian/ bookworm main contrib non-free non-free-firmware" > /etc/apt/sources.list.d/aliyun.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list.d/aliyun.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm-backports main contrib non-free non-free-firmware" >> /etc/apt/sources.list.d/aliyun.list && \
    echo "deb https://mirrors.aliyun.com/debian-security/ bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list.d/aliyun.list

# 安装构建 PyGObject 和其他依赖所需的系统库
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    pkg-config \
    # PyGObject, pycairo build dependencies
    libgirepository1.0-dev \
    libcairo2-dev \
    python3-dev \
    gir1.2-gtk-3.0 \
    # GStreamer core and plugins base for GIR data needed by PyGObject at build/validation time
    gstreamer1.0-plugins-base \
    gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0 \
    # Build tools that PyGObject might need
    meson \
    ninja-build \
    # GStreamer dev libraries (may not be strictly needed if PyGObject finds system GStreamer at runtime via gir)
    # libgstreamer1.0-dev \
    # libgstreamer-plugins-base1.0-dev \
    && echo "Cache buster $(date)" \
    && rm -rf /var/lib/apt/lists/*

# Verify installation of libgirepository1.0-dev
RUN echo "--- Dockerfile: Listing files installed by libgirepository1.0-dev (dpkg -L) ---" && \
    dpkg -L libgirepository1.0-dev > /tmp/dpkg_l_girepo.txt && \
    echo "--- Dockerfile: Finished listing files for libgirepository1.0-dev ---"

# Locate the .pc file and show dpkg output
RUN echo "--- Dockerfile: Searching for girepository-*.pc and gobject-introspection-*.pc in /usr (using find) ---" && \
    (find /usr -name 'girepository-*.pc' -print > /tmp/find_girepo_pc.txt || echo "Dockerfile: girepository-*.pc was NOT found by find under /usr" > /tmp/find_girepo_pc.txt) && \
    (find /usr -name 'gobject-introspection-*.pc' -print >> /tmp/find_girepo_pc.txt || echo "Dockerfile: gobject-introspection-*.pc was NOT found by find under /usr" >> /tmp/find_girepo_pc.txt) && \
    echo "--- Dockerfile: Finished searching for .pc file ---" && \
    echo "--- Contents of /tmp/dpkg_l_girepo.txt (libgirepository1.0-dev files) ---" && cat /tmp/dpkg_l_girepo.txt && \
    echo "--- Contents of /tmp/find_girepo_pc.txt (found .pc files) ---" && cat /tmp/find_girepo_pc.txt && \
    rm -f /tmp/dpkg_l_girepo.txt /tmp/find_girepo_pc.txt

# 安装 PDM
RUN curl -sSL https://pdm-project.org/install-pdm.py | python3 -
ENV PATH="/root/.local/bin:${PATH}"

# 安装 uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /app_build
COPY pyproject.toml ./

# 配置 PDM 使用阿里云 PyPI 镜像
RUN pdm config pypi.url https://mirrors.aliyun.com/pypi/simple/

# 配置 PDM (不再需要 system_site_packages)
RUN pdm config python.use_venv true && \
    pdm config venv.with_pip true && \
    pdm config check_update false

# 设置 PKG_CONFIG_PATH 确保能找到 .pc 文件
# Meson (used by PyGObject) should automatically pick up .pc files from standard locations
# like /usr/lib/x86_64-linux-gnu/pkgconfig and /usr/share/pkgconfig.
ENV PKG_CONFIG_PATH="/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig"

# 安装依赖 (这将创建 venv, 在 Docker 环境中生成新的 pdm.lock, 并同步依赖)
RUN pdm install --prod --no-editable --no-self

# 验证 PyGObject 和 GStreamer 在 builder 阶段的虚拟环境中是否可用
RUN . .venv/bin/activate && \
    python -c "import gi; print('[Builder] PyGObject available')" && \
    python -c "import gi; gi.require_version('Gst', '1.0'); from gi.repository import Gst; print('[Builder] GStreamer via PyGObject available')"

# ---- Stage 2: Runtime Stage ----
FROM python:3.12-slim

# 配置 APT 使用阿里云镜像 (与 builder 阶段一致)
RUN echo "deb https://mirrors.aliyun.com/debian/ bookworm main contrib non-free non-free-firmware" > /etc/apt/sources.list.d/aliyun.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list.d/aliyun.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm-backports main contrib non-free non-free-firmware" >> /etc/apt/sources.list.d/aliyun.list && \
    echo "deb https://mirrors.aliyun.com/debian-security/ bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list.d/aliyun.list

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOME=/app \
    PYTHONPATH="/app" \
    GST_DEBUG="2" \
    GST_PLUGIN_SYSTEM_PATH="/usr/lib/x86_64-linux-gnu/gstreamer-1.0" \
    MPLBACKEND="Agg" \
    MPLCONFIGDIR="/tmp/matplotlib" \
    FONTCONFIG_PATH="/etc/fonts"

WORKDIR $APP_HOME

# 安装 GStreamer 核心、插件和 GObject Introspection data (运行时需要)
# 注意：不再安装 python3-gi, python3-gi-cairo 等 python 包，它们由 venv 提供
RUN apt-get update && apt-get install -y --no-install-recommends \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-rtsp \
    gstreamer1.0-libav \
    # GObject Introspection data for GStreamer and GLib (runtime dependency for PyGObject)
    gir1.2-glib-2.0 \
    gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0 \
    gir1.2-gst-rtsp-server-1.0 \
    # 其他系统工具
    libgl1-mesa-glx \
    libglib2.0-0 \
    iproute2 \
    procps \
    curl \
    fontconfig \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser && \
    mkdir -p /home/appuser/.config/matplotlib /tmp/matplotlib && \
    chown -R appuser:appuser /home/appuser /tmp/matplotlib

COPY --from=builder /app_build/.venv $APP_HOME/.venv
COPY --from=builder /app_build/pdm.lock $APP_HOME/pdm.lock
COPY --from=builder /app_build/pyproject.toml $APP_HOME/pyproject.toml

COPY app/ $APP_HOME/app/

RUN mkdir -p $APP_HOME/logs $APP_HOME/data && \
    chown -R appuser:appuser $APP_HOME

USER appuser

ENV PATH="$APP_HOME/.venv/bin:$PATH"
# PYTHONPATH 已在顶部设置为 /app

# Diagnostic: List contents of site-packages and gi directory
RUN ls -l $APP_HOME/.venv/lib/python3.12/site-packages/ && \
    ls -l $APP_HOME/.venv/lib/python3.12/site-packages/gi

# 运行时验证 (可选，主要验证已在 builder stage)
RUN $APP_HOME/.venv/bin/python -c "import sys; print('Python sys.path:', sys.path); import gi; print('[Runtime VENV PYTHON] PyGObject available')" && \
    $APP_HOME/.venv/bin/python -c "import gi; gi.require_version('Gst', '1.0'); from gi.repository import Gst; print('[Runtime VENV PYTHON] GStreamer via PyGObject available')" && \
    $APP_HOME/.venv/bin/python -m uvicorn --version

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:58000/ || exit 1

EXPOSE 58000 8554
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "58000", "--workers", "1"] 