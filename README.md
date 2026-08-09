# OpenCode Control Tower

OpenCode 백그라운드 에이전트 자동 감시 & 복구 시스템.
에이전트가 멈추면(stall) 자동으로 abort → 동일 세션 resume.

## 요구사항

- Windows 11
- Python 3.11+
- [OpenCode](https://github.com/NiclasHaderer/opencode-ai) 설치됨
- Windows Terminal (자동 탭 열기용, 선택)

## 설치

```powershell
cd opencode-auto-rerun\opencode-control-tower
powershell -ExecutionPolicy Bypass -File install.ps1
```

## 사용법

PowerShell 아무 폴더에서:

```powershell
ctw
```

실행되는 것:
1. OpenCode 서버 자동 시작 (현재 폴더 기준)
2. 건강 확인 → Windows Terminal 새 탭으로 attach
3. 15초 idle 감지 시 `Continue your work.` 자동 전송
4. 열심히 일하는 중이면 타이머 리셋
5. 작업 완료된 세션은 복구 안 함
6. 서버 다운 → 자동 재시작
7. `Ctrl+C` 안전 종료

## 제거

```powershell
pip uninstall opencode-control-tower
notepad $PROFILE   # ctw 줄 삭제
```
