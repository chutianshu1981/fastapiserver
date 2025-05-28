#!/bin/bash

# Docker 网络问题修复脚本
set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Docker 网络问题诊断和修复${NC}"
echo -e "${BLUE}========================================${NC}"

# 1. 检查 Docker 代理配置
echo -e "${YELLOW}1. 检查 Docker 代理配置...${NC}"

# 检查 Docker daemon 配置
DOCKER_CONFIG_DIR="/etc/docker"
DOCKER_DAEMON_CONFIG="$DOCKER_CONFIG_DIR/daemon.json"

if [ -f "$DOCKER_DAEMON_CONFIG" ]; then
    echo -e "${GREEN}找到 Docker daemon 配置文件:${NC} $DOCKER_DAEMON_CONFIG"
    echo "当前配置:"
    cat "$DOCKER_DAEMON_CONFIG"
else
    echo -e "${YELLOW}未找到 Docker daemon 配置文件${NC}"
fi

# 检查环境变量中的代理设置
echo -e "${YELLOW}2. 检查环境变量代理设置...${NC}"
env | grep -i proxy || echo "未找到代理环境变量"

# 3. 测试网络连接
echo -e "${YELLOW}3. 测试网络连接...${NC}"

# 测试直接连接 Docker Hub
echo "测试连接到 Docker Hub..."
if curl -s --connect-timeout 10 https://registry-1.docker.io/v2/ > /dev/null; then
    echo -e "${GREEN}✓ 可以直接连接到 Docker Hub${NC}"
    DIRECT_CONNECTION=true
else
    echo -e "${RED}✗ 无法直接连接到 Docker Hub${NC}"
    DIRECT_CONNECTION=false
fi

# 4. 提供解决方案
echo -e "${YELLOW}4. 解决方案建议...${NC}"

if [ "$DIRECT_CONNECTION" = true ]; then
    echo -e "${GREEN}建议: 清除 Docker 代理配置${NC}"
    
    # 创建或更新 Docker daemon 配置
    echo "创建/更新 Docker daemon 配置以禁用代理..."
    
    # 备份现有配置
    if [ -f "$DOCKER_DAEMON_CONFIG" ]; then
        sudo cp "$DOCKER_DAEMON_CONFIG" "$DOCKER_DAEMON_CONFIG.backup.$(date +%Y%m%d_%H%M%S)"
        echo "已备份现有配置"
    fi
    
    # 创建新的配置（移除代理设置）
    sudo mkdir -p "$DOCKER_CONFIG_DIR"
    cat << 'EOF' | sudo tee "$DOCKER_DAEMON_CONFIG" > /dev/null
{
  "registry-mirrors": [],
  "insecure-registries": [],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
    
    echo -e "${GREEN}已更新 Docker daemon 配置${NC}"
    echo -e "${YELLOW}请重启 Docker 服务:${NC}"
    echo "  sudo systemctl restart docker"
    
else
    echo -e "${YELLOW}建议: 配置正确的代理设置或使用国内镜像${NC}"
    
    # 提供国内镜像配置
    echo "选项1: 使用国内 Docker 镜像加速器"
    cat << 'EOF'
    
创建/更新 /etc/docker/daemon.json:
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com",
    "https://mirror.baidubce.com"
  ]
}
EOF
    
    echo ""
    echo "选项2: 配置代理（如果您有可用的代理）"
    echo "在 /etc/docker/daemon.json 中添加:"
    cat << 'EOF'
{
  "proxies": {
    "http-proxy": "http://proxy.example.com:10809",
    "https-proxy": "http://proxy.example.com:10809",
    "no-proxy": "localhost,127.0.0.1"
  }
}
EOF
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  自动修复选项${NC}"
echo -e "${BLUE}========================================${NC}"

read -p "是否自动应用推荐的修复方案? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ "$DIRECT_CONNECTION" = true ]; then
        echo "重启 Docker 服务..."
        sudo systemctl restart docker
        echo -e "${GREEN}✓ Docker 服务已重启${NC}"
        
        # 测试 Docker 是否正常工作
        echo "测试 Docker 功能..."
        if docker version > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Docker 服务正常${NC}"
        else
            echo -e "${RED}✗ Docker 服务异常，请检查日志${NC}"
            echo "查看日志: sudo journalctl -u docker.service"
        fi
    else
        echo "请手动配置代理或镜像加速器后重启 Docker 服务"
    fi
else
    echo "跳过自动修复"
fi

echo ""
echo -e "${GREEN}修复完成！现在可以尝试重新构建 Docker 镜像。${NC}" 