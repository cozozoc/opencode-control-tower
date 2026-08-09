#!/bin/bash
# install.sh — OpenCode Control Tower WSL2 한방 설치
# 실행: bash install.sh

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo ">>> OpenCode Control Tower 설치 (WSL2)"

# 0. 사전 확인
echo "[0/4] 사전 조건 확인"

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
echo "[1/4] pip install"
pip install -e "$ROOT" -q --break-system-packages 2>/dev/null || pip install -e "$ROOT" -q

# 2. tmux 다크 테마
echo "[2/4] tmux 다크 테마 설정"
if [ ! -f ~/.tmux.conf ] || ! grep -q "status-bg" ~/.tmux.conf 2>/dev/null; then
    cat >> ~/.tmux.conf << 'EOF'

# OpenCode Control Tower 다크 테마
set -g status-bg colour235
set -g status-fg white
set -g status-left "#[bg=colour24] #S "
EOF
fi

# 3. LLM 모델 사용 제한 시 자동 fallback (opencode-runtime-fallback 플러그인)
echo "[3/4] 모델 fallback 설정 (DeepSeek V4 Flash Free)"
mkdir -p ~/.config/opencode
if [ ! -f ~/.config/opencode/opencode.jsonc ]; then
    cat > ~/.config/opencode/opencode.jsonc << 'EOF'
{
  "plugin": ["opencode-runtime-fallback"]
}
EOF
elif ! grep -q "opencode-runtime-fallback" ~/.config/opencode/opencode.jsonc 2>/dev/null; then
    # 기존 config에 plugin 항목 병합 (python3 JSON 파싱)
    python3 - "$HOME/.config/opencode/opencode.jsonc" << 'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
try:
    data = json.loads(p.read_text(encoding="utf-8"))
except Exception as e:
    print(f"WARN: opencode.jsonc 파싱 실패 - {e}, plugin 수동 등록 필요")
    sys.exit(0)
plugins = data.get("plugin") or []
if isinstance(plugins, str):
    plugins = [plugins]
if "opencode-runtime-fallback" not in plugins:
    plugins.append("opencode-runtime-fallback")
data["plugin"] = plugins
p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("  opencode.jsonc에 fallback 플러그인 등록 완료")
PYEOF
fi

cat > ~/.config/opencode/opencode-fallback.jsonc << 'EOF'
{
  "fallback_models": ["opencode/deepseek-v4-flash-free"],
  "cooldown_seconds": 300,
  "notify_on_fallback": true
}
EOF

# 4. bashrc에 ctw 등록
echo "[4/4] bashrc에 ctw 명령어 등록"
if ! grep -q "function ctw" ~/.bashrc 2>/dev/null; then
    cat >> ~/.bashrc << 'EOF'

# OpenCode Control Tower
function ctw { python3 -m octower --fast --launch; }
EOF
fi

echo "설치 완료!"
echo ""
echo "사용법: source ~/.bashrc 후 ctw 입력"
