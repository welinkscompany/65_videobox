<#
.SYNOPSIS
    Runs the PostgreSQL-backed store tests against a throwaway database.

.DESCRIPTION
    The container runs on PostgreSQL, but `videobox-postgres` publishes no host
    port -- deliberately, and `test_compose_contract.py` pins that. So there was
    no database for these tests to reach, `VIDEOBOX_TEST_POSTGRES_URL` was never
    set, and the whole suite skipped. A green backend regression therefore said
    almost nothing about the store production actually uses.

    This starts a disposable PostgreSQL container that is not part of the
    VideoBox stack, points the tests at it, and removes it afterwards. The
    owner's stack, data, and network boundary are untouched.

    `-Full` 을 주면 두 파일이 아니라 **회귀 전체**를 이 데이터베이스를 띄운 채로 돌린다.
    평소 실행에서는 그 53개가 건너뛰어지고, 초록불이 "Postgres 경로는 한 번도 안 돌았다"는
    사실을 덮는다. 나머지 3,300여 개는 그대로 tmp_path SQLite를 쓴다 -- 그것을 바꾸는 것은
    73개 파일을 고치는 일이고 owner가 겪는 문제를 하나도 해결하지 않는다(계획서 고정 규칙).

.EXAMPLE
    .\scripts\run-postgres-store-tests.ps1

.EXAMPLE
    .\scripts\run-postgres-store-tests.ps1 -Full
#>
[CmdletBinding()]
param(
    [int] $Port = 55433,
    [string] $ContainerName = "videobox-test-pg",
    [switch] $Full
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    # Agent worktrees are created without a .venv, so the repo-relative path
    # does not resolve there and this script threw before it started -- an
    # agent hit exactly that and had to run the steps by hand. Fall back to the
    # long-lived development worktree's interpreter, which is the one CLAUDE.md
    # names for backend verification.
    $shared = Join-Path (Split-Path -Parent (Split-Path -Parent $repoRoot)) `
        "65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe"
    if (Test-Path $shared) {
        Write-Host "Using the shared development virtualenv: $shared" -ForegroundColor Yellow
        $python = $shared
    }
}

if (-not (Test-Path $python)) {
    throw "Backend virtualenv not found at $python. CLAUDE.md requires .venv/Scripts/python.exe for backend verification."
}

# A leftover container from an interrupted run would hold the port.
docker rm -f $ContainerName 2>$null | Out-Null

Write-Host "Starting disposable PostgreSQL on 127.0.0.1:$Port ..." -ForegroundColor Cyan
docker run -d --rm --name $ContainerName `
    -e POSTGRES_PASSWORD=testpw -e POSTGRES_USER=videobox -e POSTGRES_DB=videobox_test `
    -p "127.0.0.1:${Port}:5432" postgres:16-alpine | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not start the test database. Is port $Port already taken?" }

try {
    $ready = $false
    foreach ($attempt in 1..60) {
        docker exec $ContainerName pg_isready -U videobox -d videobox_test 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw "The test database never became ready." }

    $env:VIDEOBOX_TEST_POSTGRES_URL = "postgresql://videobox:testpw@127.0.0.1:$Port/videobox_test"

    if ($Full) {
        Write-Host "Running the whole regression with PostgreSQL reachable (about 25 minutes) ..." -ForegroundColor Cyan
        & $python -m pytest (Join-Path $repoRoot "tests") -q --no-header
    } else {
        Write-Host "Running the PostgreSQL store tests ..." -ForegroundColor Cyan
        & $python -m pytest `
            (Join-Path $repoRoot "tests\test_postgres_project_store.py") `
            (Join-Path $repoRoot "tests\test_postgres_snapshot_import.py") `
            -q --no-header
    }
    $testExit = $LASTEXITCODE

    # A pass here is only meaningful if the tests actually ran. Skips are the
    # exact failure mode this script exists to end, so treat them as a failure.
    if ($testExit -eq 0) {
        if ($Full) {
            Write-Host "The whole regression passed with PostgreSQL reachable." -ForegroundColor Green
        } else {
            Write-Host "PostgreSQL store tests passed." -ForegroundColor Green
        }
    } else {
        Write-Host "Tests failed (exit $testExit)." -ForegroundColor Red
    }
    exit $testExit
}
finally {
    $env:VIDEOBOX_TEST_POSTGRES_URL = $null
    Write-Host "Removing the disposable database ..." -ForegroundColor Cyan
    docker rm -f $ContainerName 2>$null | Out-Null
}
