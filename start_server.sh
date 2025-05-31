#!/bin/bash

# 项目根目录 (现在假设是 src 目录)
PROJECT_ROOT=~/fastapiserver/src
# PDM 可执行文件路径 (如果 pdm 不在系统 PATH 中，或者您想指定特定的 pdm)
# 例如：PDM_EXECUTABLE=~/.local/bin/pdm
PDM_EXECUTABLE=pdm

# 进入项目根目录 (即 src 目录)
cd "${PROJECT_ROOT}" || { echo "错误：无法进入目录 ${PROJECT_ROOT}"; exit 1; }

echo "当前工作目录: $(pwd)" # 添加日志确认当前目录

# 查找虚拟环境的 uvicorn路径
# PDM 通常在项目根目录下的 .venv/bin/uvicorn 创建可执行文件
VENV_UVICORN_PATH="./.venv/bin/uvicorn" # 相对于当前目录 (即 src 目录)

if [ ! -f "$VENV_UVICORN_PATH" ]; then
    echo "错误: 虚拟环境中的 uvicorn 未找到于 ${PROJECT_ROOT}/.venv/bin/uvicorn"
    echo "请确保 PDM 虚拟环境已创建 (在 ${PROJECT_ROOT} 目录下运行 pdm install)"
    exit 1
fi

echo "正在使用虚拟环境中的 uvicorn 启动服务器..."

# 构建 uvicorn 命令
# 使用 nohup 在后台运行，并将所有输出重定向到 /dev/null (不保留日志文件)
# 如果您希望保留日志，可以将 /dev/null 替换为日志文件路径，例如 nohup.log
# uvicorn 的 app.main:app 路径是相对于当前工作目录（即 src）的
COMMAND_TO_RUN="nohup ${VENV_UVICORN_PATH} app.main:app --host 0.0.0.0 --port 58000 > /dev/null 2>&1 &"

echo "将要执行的命令: $COMMAND_TO_RUN"

# 执行命令
eval "$COMMAND_TO_RUN"

# 检查 uvicorn 是否成功启动 (这是一个简单的检查，可能不够鲁棒)
# sleep 2 # 等待一点时间让进程启动
# if pgrep -f "uvicorn app.main:app" > /dev/null; then
#     echo "服务器似乎已成功启动并在后台运行。"
#     echo "进程PID: $(pgrep -f "uvicorn app.main:app")"
# else
#     echo "错误：服务器可能未能成功启动。请检查 nohup.out (如果未重定向到/dev/null) 或手动检查进程。"
# fi

echo "启动脚本执行完毕。服务器应在后台运行。"
echo "您可以使用 'pgrep -f "uvicorn app.main:app"' 或 'ps aux | grep uvicorn' 来检查进程。"
echo "要停止服务器，请找到进程 PID 并使用 'kill <PID>'"
