# OpenCode Control Tower (octower)

OpenCode 백그라운드 에이전트 자동 감시 & 복구 시스템.
에이전트가 멈추면(stall) 자동으로 abort → 동일 세션 resume하고, 완료된 작업은 건드리지 않습니다.

## 주요 기능

- **자동 감시** — 실행 중인 OpenCode 세션을 폴링하며 idle 시간 추적
- **자동 복구** — FAST MODE 기준 5s slow / 10s suspect / 15s stall → `Continue your work.` 자동 전송
- **완료 감지** — 작업이 끝난 세션은 stall로 오인하지 않고 복구 대상에서 제외
- **서버 자가 치유** — OpenCode 서버가 죽으면 자동 재시작 후 세션 복원
- **WSL2 + tmux 통합** — 백그라운드 tmux 세션에서 실행, Windows Terminal 탭 자동 오픈
- **모델 fallback** — LLM 사용 제한(rate limit) 발생 시 무료 모델로 자동 전환
- **다크 테마** — tmux 상태 표시줄 기본 다크 테마 적용

## 요구사항

- Windows 11 + WSL2 (Ubuntu)
- Python 3.11+
- tmux (`bash install.sh`가 자동 설치)
- OpenCode CLI (`npm install -g opencode-ai` — install.sh가 자동 설치)
- Windows Terminal (자동 탭 열기용, 선택)

## 설치

WSL2 터미널에서:

```bash
git clone git@github.com:cozozoc/opencode-control-tower.git
cd opencode-control-tower
bash install.sh
source ~/.bashrc
```

`install.sh`가 하는 일:

1. Python 3.11+ / tmux / opencode 확인 (없으면 설치)
2. `pip install -e .`
3. `~/.tmux.conf`에 다크 테마 추가
4. OpenCode config에 fallback 플러그인 + 무료 모델 등록 (rate limit 대비)
5. `~/.bashrc`에 `ctw` 명령어 등록

## 사용법

WSL2 터미널에서:

```bash
ctw
```

실행되는 것:

1. OpenCode 서버 자동 시작 (`opencode serve`, 로컬 포트 자동 할당)
2. tmux 세션 `octower-XXXXXX` 백그라운드 생성
3. 건강 확인 → Windows Terminal 새 탭에서 tmux attach
4. 세션 폴링: 5초 slow / 10초 suspect / 15초 stall 감지 시 `Continue your work.` 자동 전송
5. 열심히 일하는 중이면 타이머 리셋
6. 작업 완료된 세션은 복구 안 함
7. 서버 다운 → 자동 재시작 + 세션 복원
8. `Ctrl+C` 안전 종료

다른 터미널에서 수동 attach:

```bash
tmux attach -t octower-XXXXXX   # 세션명은 ctw 로그에서 확인
```

## 설정

### tmux 다크 테마

`~/.tmux.conf`를 편집하고 `tmux source-file ~/.tmux.conf`로 즉시 적용:

```bash
set -g status-bg colour235      # 하단 바 배경 (초록 → 회색)
set -g status-fg white          # 글자색
set -g status-left "#[bg=colour24] #S "   # 좌측 세션명 배경
```

> 실행 중인 기존 tmux 세션은 `tmux source-file ~/.tmux.conf`를 실행해야 반영됩니다
> (tmux는 세션 생성 시점의 설정을 사용합니다).

### LLM 모델 사용 제한 시 자동 fallback

`~/.config/opencode/opencode-fallback.jsonc`:

```json
{
  "fallback_models": ["opencode/deepseek-v4-flash-free"],
  "cooldown_seconds": 300,
  "notify_on_fallback": true
}
```

기본 모델이 rate limit(429/quota)에 걸리면 자동으로 `opencode/deepseek-v4-flash-free`로 전환되고,
5분 쿨다운 후 원래 모델로 복귀합니다.

## 제거

```bash
rm -rf ~/opencode-control-tower
sed -i '/function ctw/d' ~/.bashrc
pip uninstall opencode-control-tower
```