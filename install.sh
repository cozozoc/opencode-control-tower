#!/bin/bash
# install.sh — OpenCode Control Tower WSL2 한방 설치
# 실행: bash install.sh

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo ">>> OpenCode Control Tower 설치 (WSL2)"

# 0. 사전 확인
echo "[0/3] 사전 조건 확인"

if ! command -v python3 &>/dev/null || ! python3 --version | grep -q "3\.1[1-9]\|3\.[2-9]"; then
    echo "ERROR: Python 3.11+ 필요"
    exit 1
fi
echo "  Python OK"

if ! command -v tmux &>/dev/null; then
    echo "  tmux 설치 중..."
    sudo apt-get update -qq && sudo apt-get install -y -qq tmux
fi
echo "  tmux OK"

if ! command -v opencode &>/dev/null; then
    echo "  opencode 설치 중..."
    npm install -g opencode-ai -q 2>/dev/null
    if ! command -v opencode &>/dev/null; then
        echo "ERROR: opencode 설치 실패"
        exit 1
    fi
fi
echo "  OpenCode OK"

# 1. Python 패키지 설치
echo "[1/3] pip install"
pip install -e "$ROOT" -q --break-system-packages 2>/dev/null || pip install -e "$ROOT" -q

# 2. bashrc에 ctw 등록
echo "[2/3] bashrc에 ctw 명령어 등록"
if ! grep -q "function ctw" ~/.bashrc 2>/dev/null; then
    cat >> ~/.bashrc << 'EOF'

# OpenCode Control Tower
function ctw { python3 -m octower --fast --launch; }
EOF
fi

echo "[3/3] 설치 완료!"
echo ""
echo "사용법: source ~/.bashrc 후 ctw 입력"
