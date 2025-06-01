#!/bin/bash

# RTSP AI 服务器 Docker 构建脚本
set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 默认配置
IMAGE_NAME="rtsp-ai-server"
IMAGE_TAG="latest"
DOCKER_REGISTRY=""
PUSH=false
NO_CACHE=false

# 帮助信息
show_help() {
    echo "使用方法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -n, --name NAME        设置镜像名称 (默认: rtsp-ai-server)"
    echo "  -t, --tag TAG          设置镜像标签 (默认: latest)"
    echo "  -r, --registry URL     设置 Docker 注册表 URL"
    echo "  -p, --push             构建后推送到注册表"
    echo "  --no-cache             不使用构建缓存"
    echo "  -h, --help             显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0                                    # 基本构建"
    echo "  $0 -t v1.0.0 -p                     # 构建并推送 v1.0.0 版本"
    echo "  $0 -r myregistry.com -n myapp -p    # 构建并推送到自定义注册表"
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--name)
            IMAGE_NAME="$2"
            shift 2
            ;;
        -t|--tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -r|--registry)
            DOCKER_REGISTRY="$2"
            shift 2
            ;;
        -p|--push)
            PUSH=true
            shift
            ;;
        --no-cache)
            NO_CACHE=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}未知选项: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# 构建完整镜像名
if [[ -n "$DOCKER_REGISTRY" ]]; then
    FULL_IMAGE_NAME="${DOCKER_REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
else
    FULL_IMAGE_NAME="${IMAGE_NAME}:${IMAGE_TAG}"
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  RTSP AI 服务器 Docker 构建${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}镜像名称:${NC} $FULL_IMAGE_NAME"
echo -e "${GREEN}构建目录:${NC} $(pwd)"
echo -e "${GREEN}推送选项:${NC} $PUSH"
echo -e "${GREEN}无缓存构建:${NC} $NO_CACHE"
echo ""

# 检查必要文件
echo -e "${YELLOW}检查必要文件...${NC}"
for file in Dockerfile pyproject.toml pdm.lock; do
    if [[ ! -f "$file" ]]; then
        echo -e "${RED}错误: 缺少必要文件 $file${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} $file"
done

# 构建 Docker 镜像
echo -e "${YELLOW}开始构建 Docker 镜像...${NC}"
BUILD_ARGS="--tag $FULL_IMAGE_NAME"

if [[ "$NO_CACHE" == "true" ]]; then
    BUILD_ARGS="$BUILD_ARGS --no-cache"
fi

echo -e "${BLUE}执行命令:${NC} docker build $BUILD_ARGS ."
if docker build $BUILD_ARGS .; then
    echo -e "${GREEN}✓ Docker 镜像构建成功!${NC}"
else
    echo -e "${RED}✗ Docker 镜像构建失败!${NC}"
    exit 1
fi

# 显示镜像信息
echo -e "${YELLOW}镜像信息:${NC}"
docker images "$FULL_IMAGE_NAME" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

# 推送到注册表
if [[ "$PUSH" == "true" ]]; then
    echo -e "${YELLOW}推送镜像到注册表...${NC}"
    if docker push "$FULL_IMAGE_NAME"; then
        echo -e "${GREEN}✓ 镜像推送成功!${NC}"
    else
        echo -e "${RED}✗ 镜像推送失败!${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  构建完成!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}镜像:${NC} $FULL_IMAGE_NAME"
echo ""
echo -e "${YELLOW}运行镜像:${NC}"
echo "  docker run -d -p 58000:58000 -p 8554:8554 --name rtsp-ai-container $FULL_IMAGE_NAME"
echo ""
echo -e "${YELLOW}使用 Docker Compose:${NC}"
echo "  docker-compose up -d" 