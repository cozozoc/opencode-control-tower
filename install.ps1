# install.ps1 — OpenCode Control Tower 한방 설치
# 실행: powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ">>> OpenCode Control Tower 설치 중..." -ForegroundColor Cyan

# 1. Python 패키지 설치
Write-Host "[1/2] pip install -e $ROOT"
pip install -e $ROOT --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install 실패" -ForegroundColor Red
    exit 1
}

# 2. PowerShell 프로필에 ctw 함수 등록
Write-Host "[2/2] PowerShell 프로필에 ctw 명령어 등록"
$profileDir = Split-Path -Parent $PROFILE
if (-not (Test-Path $profileDir)) { New-Item -Path $profileDir -ItemType Directory -Force | Out-Null }
if (-not (Test-Path $PROFILE)) { New-Item -Path $PROFILE -ItemType File -Force | Out-Null }

$func = '
function ctw { python -m octower --fast --launch }
'
if ((Get-Content $PROFILE -Raw) -notmatch 'function ctw') {
    Add-Content $PROFILE "`n$func"
}

Write-Host ">>> 설치 완료!" -ForegroundColor Green
Write-Host ""
Write-Host "사용법: PowerShell 새로 열고 ctw 입력"
Write-Host "또는 지금 바로: .$PROFILE  후  ctw"
