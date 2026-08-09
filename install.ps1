# install.ps1 — OpenCode Control Tower 한방 설치
# 실행: powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ">>> OpenCode Control Tower 설치" -ForegroundColor Cyan

# 0. 사전 확인
Write-Host "[0/3] 사전 조건 확인"

$pythonOk = $false
try { $v = python --version 2>&1; if ($v -match "3\.(\d+)") { if ([int]$matches[1] -ge 11) { $pythonOk = $true } } } catch {}
if (-not $pythonOk) {
    Write-Host "ERROR: Python 3.11+ 필요" -ForegroundColor Red
    exit 1
}
Write-Host "  Python OK"

$opencodeOk = $false
try { $null = Get-Command opencode -ErrorAction Stop; $opencodeOk = $true } catch {}
if (-not $opencodeOk) {
    Write-Host "WARNING: opencode 명령어가 PATH에 없습니다. npm install -g opencode-ai 필요" -ForegroundColor Yellow
}
Write-Host "  OpenCode OK"

# 1. Python 패키지 설치
Write-Host "[1/3] pip install -e $ROOT"
pip install -e $ROOT --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install 실패" -ForegroundColor Red
    exit 1
}

# 2. PowerShell 프로필에 ctw 함수 등록
Write-Host "[2/3] PowerShell 프로필에 ctw 명령어 등록"
$profileDir = Split-Path -Parent $PROFILE
if (-not (Test-Path $profileDir)) { New-Item -Path $profileDir -ItemType Directory -Force | Out-Null }
if (-not (Test-Path $PROFILE)) { New-Item -Path $PROFILE -ItemType File -Force | Out-Null }

$func = 'function ctw { python -m octower --fast --launch }'
if ((Get-Content $PROFILE -Raw) -notmatch 'function ctw') {
    Add-Content $PROFILE "`n$func"
}

# 3. 완료
Write-Host "[3/3] 설치 완료!" -ForegroundColor Green
Write-Host ""
Write-Host "사용법: PowerShell 새로 열고 ctw 입력"
