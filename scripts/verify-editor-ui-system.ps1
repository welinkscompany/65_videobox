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
  foreach ($token in @('--vb-canvas: #FAFAF9', '--vb-accent: #4F46E5', '--vb-preview: #18181B', 'PretendardVariable.woff2')) { if (-not $css.Contains($token)) { $errors.Add("missing UI token: $token") } }
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
