[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$web = Join-Path $root 'apps/web'
$errors = [Collections.Generic.List[string]]::new()
$production = Get-ChildItem (Join-Path $web 'src') -Recurse -File | Where-Object { $_.Extension -in @('.ts', '.tsx', '.js', '.jsx', '.css') -and $_.Name -notmatch '\.test\.' }
foreach ($file in $production) {
  $content = Get-Content -Raw $file.FullName
  if ($content -match '(?i)(?:@import|url\(|(?:href|src)\s*=)\s*["'']?(?:https?:)?//') { $errors.Add("remote runtime asset: $($file.FullName)") }
}
$uiCss = Join-Path $web 'src/ui-system.css'
if (-not (Test-Path $uiCss)) { $errors.Add('ui-system.css is absent') }
else {
  $css = Get-Content -Raw $uiCss
  # These pin the palette the owner approved most recently
  # (docs/decisions/2026-08-05-dashboard-white-orange-direction.ko.md), which
  # superseded the warm-white/indigo direction. This list still named the old
  # #FAFAF9/#4F46E5 values, so the verifier failed on correct code -- and a
  # check that cries wolf is a check nobody runs. contrast.test.ts locks the
  # same hexes from the JS side; both must move together, and only with a new
  # approval record (CLAUDE.md §6).
  foreach ($token in @('--vb-canvas: #FAFAFA', '--vb-accent: #C2410C', '--vb-preview: #18181B', 'PretendardVariable.woff2')) { if (-not $css.Contains($token)) { $errors.Add("missing UI token: $token") } }
  # 편집 화면만 어둡다 (docs/decisions/2026-08-20-editor-dark-surface.ko.md).
  # 어두운 값이 여기 없으면 세 곳 중 두 곳에만 남아 다음에 조용히 갈라진다.
  # 실측으로 고른 값이다: 흰 배경용 #C2410C는 어두운 패널에서 3.28로 글자
  # 기준에 못 미쳐서, 글자용은 #E8613A(5.02)를 쓰고 채운 단추만 #C2410C로 둔다.
  foreach ($token in @('--vb-canvas: #141416', '--vb-panel: #1C1C1F', '--vb-accent: #E8613A')) { if (-not $css.Contains($token)) { $errors.Add("missing dark editor token: $token") } }
  if (-not $css.Contains('.vb-editor-workbench {')) { $errors.Add('dark tokens must stay scoped to the editor surface') }
  if ($css -match '@import\s+["'']tailwindcss["'']') { $errors.Add('Tailwind preflight import is forbidden') }
}
$indexHtml = Join-Path $web 'index.html'
if (-not (Test-Path $indexHtml) -or -not ((Get-Content -Raw $indexHtml) -match "Content-Security-Policy")) { $errors.Add('runtime Content-Security-Policy is absent') }
$mainEntry = Join-Path $web 'src/main.tsx'
if (-not (Test-Path $mainEntry) -or -not ((Get-Content -Raw $mainEntry) -match 'installNetworkGuard\(\)')) { $errors.Add('browser runtime network guard is absent') }
$dist = Join-Path $web 'dist'
if (Test-Path $dist) {
  foreach ($file in (Get-ChildItem $dist -Recurse -File | Where-Object { $_.Extension -in @('.js', '.css', '.html') })) {
    if ((Get-Content -Raw $file.FullName) -match '(?i)(?:https?:)?//(?:fonts\.googleapis\.com|fonts\.gstatic\.com)') { $errors.Add("remote asset in build: $($file.FullName)") }
  }
}
if ($errors.Count) { throw ("Editor UI system verification failed:`n - " + ($errors -join "`n - ")) }
Write-Output 'Editor UI system verification passed.'
