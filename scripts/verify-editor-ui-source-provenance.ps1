[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$mapPath = Join-Path $root 'docs/oss/editor-ui-source-map.json'
$lockPath = Join-Path $root 'docs/oss/shadcn-registry-lock.json'
$noticesPath = Join-Path $root 'THIRD_PARTY_NOTICES.md'
$shaPattern = '^[0-9a-f]{64}$'
$commitPattern = '^[0-9a-f]{40}$'
$expectedPins = @{
  'shadcn-admin' = 'e16c87f213a5ba5e45964e9b67c792105ec74d26'
  'shadcn-ui' = '4396d5b2a5ee4e2ad5705e9b2522f92112f811a0'
  'opencut-current' = 'bab8af831b354a0b5a98a4a6e818ab7d633b94df'
  'opencut-classic' = 'cf5e79e919144200294fb9fed22a222592a0aeea'
  'opencast-editor' = '1208afb64d9de0ab50b321f84f9dd2695780db87'
  'supabase' = '1c827c5cbb29cacc6e9052adff2e1659e3cb05fb'
  'pretendard' = '5c41199ea0024a9e0b2cb31735265056e5472d76'
}
$expectedPolicy = @{
  'shadcn-admin' = @('satnaing/shadcn-admin', 'partial-port', 'MIT', 'https://github.com/satnaing/shadcn-admin/blob/e16c87f213a5ba5e45964e9b67c792105ec74d26/LICENSE')
  'shadcn-ui' = @('shadcn-ui/ui', 'locked-source', 'MIT', 'https://github.com/shadcn-ui/ui/blob/4396d5b2a5ee4e2ad5705e9b2522f92112f811a0/LICENSE.md')
  'opencut-current' = @('OpenCut-app/OpenCut', 'rejected-runtime', 'AGPL-3.0-or-later', 'https://github.com/OpenCut-app/OpenCut/blob/bab8af831b354a0b5a98a4a6e818ab7d633b94df/LICENSE')
  'opencut-classic' = @('OpenCut-app/opencut-classic', 'partial-port', 'MIT', 'https://github.com/OpenCut-app/opencut-classic/blob/cf5e79e919144200294fb9fed22a222592a0aeea/LICENSE')
  'opencast-editor' = @('opencast/editor', 'partial-port', 'Apache-2.0', 'https://github.com/opencast/editor/blob/1208afb64d9de0ab50b321f84f9dd2695780db87/LICENSE')
  'supabase' = @('supabase/supabase', 'reference-only', 'Apache-2.0', 'https://github.com/supabase/supabase/blob/1c827c5cbb29cacc6e9052adff2e1659e3cb05fb/LICENSE')
  'pretendard' = @('orioncactus/pretendard', 'locked-binary', 'SIL OFL-1.1', 'https://github.com/orioncactus/pretendard/blob/5c41199ea0024a9e0b2cb31735265056e5472d76/LICENSE.txt')
}
$errors = [System.Collections.Generic.List[string]]::new()

function Add-Error([string]$message) { $script:errors.Add($message) }
function Get-Sha256([string]$path) {
  $stream = [IO.File]::OpenRead($path)
  try { return ([Security.Cryptography.SHA256]::Create().ComputeHash($stream) | ForEach-Object { $_.ToString('x2') }) -join '' }
  finally { $stream.Dispose() }
}
function Has-Property($object, [string]$name) { return $null -ne $object.PSObject.Properties[$name] }
function Is-RepoRelative([string]$path) {
  return $path -and -not [IO.Path]::IsPathRooted($path) -and ($path -notmatch '(^|[\\/])\.\.([\\/]|$)')
}
function Check-Artifact($entry, [string]$kind) {
  foreach ($field in @('source_pin', 'upstream_path', 'upstream_sha256', 'path', 'normalized_sha256', 'test_path')) {
    if (-not (Has-Property $entry $field) -or -not $entry.$field) { Add-Error "$kind missing $field" }
  }
  if ($entry.upstream_sha256 -notmatch $shaPattern -or $entry.normalized_sha256 -notmatch $shaPattern) { Add-Error "$kind has invalid hash" }
  if (-not (Is-RepoRelative $entry.path) -or -not (Is-RepoRelative $entry.test_path)) { Add-Error "$kind path must be repository-relative"; return }
  $file = Join-Path $root $entry.path
  if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { Add-Error "$kind materialized path is absent"; return }
  $testFile = Join-Path $root $entry.test_path
  if (-not (Test-Path -LiteralPath $testFile -PathType Leaf)) { Add-Error "$kind test path is absent" }
  $actual = Get-Sha256 $file
  if ($actual -ne $entry.normalized_sha256) { Add-Error "$kind normalized hash drift: $($entry.path)" }
}
function Check-LocalArtifact($entry, $pin) {
  foreach ($field in @('path', 'sha256', 'test_path')) { if (-not (Has-Property $entry $field) -or -not $entry.$field) { Add-Error "$($pin.name) local artifact missing $field" } }
  if ($entry.sha256 -notmatch $shaPattern -or -not (Is-RepoRelative $entry.path) -or -not (Is-RepoRelative $entry.test_path)) { Add-Error "$($pin.name) local artifact has invalid path or SHA"; return }
  $file = Join-Path $root $entry.path; $testFile = Join-Path $root $entry.test_path
  if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or -not (Test-Path -LiteralPath $testFile -PathType Leaf)) { Add-Error "$($pin.name) local artifact or test path is absent" }
  elseif ((Get-Sha256 $file) -ne $entry.sha256) { Add-Error "$($pin.name) local artifact hash drift" }
  if ($pin.decision -in @('reference-only', 'rejected-runtime')) { Add-Error "$($pin.name) local artifact is forbidden by source policy" }
  if ($pin.license -eq 'Apache-2.0') {
    $matches = @($map.apache_adaptations | Where-Object { $_.source_pin -eq $pin.name -and $_.path -eq $entry.path })
    if ($matches.Count -ne 1 -or $matches[0].license_url -ne $pin.license_url -or $matches[0].notice_url -ne $pin.notice_url -or -not $matches[0].change_summary -or -not $matches[0].attribution) { Add-Error "$($pin.name) local Apache artifact requires matching attribution" }
  }
}

if (-not (Test-Path -LiteralPath $mapPath) -or -not (Test-Path -LiteralPath $lockPath) -or -not (Test-Path -LiteralPath $noticesPath)) {
  throw 'Missing provenance map, registry lock, or third-party notices.'
}
$map = Get-Content -Raw -LiteralPath $mapPath | ConvertFrom-Json
$lock = Get-Content -Raw -LiteralPath $lockPath | ConvertFrom-Json
$notices = Get-Content -Raw -LiteralPath $noticesPath
$packageManifestPath = Join-Path $root 'apps/web/package.json'
$packageManifest = Get-Content -Raw -LiteralPath $packageManifestPath | ConvertFrom-Json
$packageLockPath = Join-Path $root 'apps/web/package-lock.json'
$packageLock = $null
if (Test-Path -LiteralPath $packageLockPath) {
  try {
    # npm lockfiles use an empty package-path key for the workspace root.
    # Windows PowerShell 5 cannot deserialize that key, so rename only the
    # parsed in-memory root key; dependency package paths are unchanged.
    $packageLockJson = (Get-Content -Raw -LiteralPath $packageLockPath) -replace '(?m)(^\s*)""\s*:', '$1"__workspace_root__":'
    $packageLock = $packageLockJson | ConvertFrom-Json
  }
  catch { Add-Error 'apps/web/package-lock.json is not valid JSON' }
} else { Add-Error 'apps/web/package-lock.json is absent' }

if (@($map.source_pins).Count -ne 7) { Add-Error 'source_pins must contain exactly seven immutable pins' }
$seen = @{}
$pinsByName = @{}
foreach ($pin in @($map.source_pins)) {
  $seen[$pin.name] = $true
  $pinsByName[$pin.name] = $pin
  foreach ($field in @('name', 'repository', 'commit', 'license', 'license_url', 'notice_url', 'decision')) {
    if (-not (Has-Property $pin $field) -or -not $pin.$field) { Add-Error "$($pin.name): missing $field" }
  }
  if ($pin.commit -notmatch $commitPattern) { Add-Error "$($pin.name): invalid immutable commit" }
  if ($expectedPins.ContainsKey($pin.name) -and $pin.commit -ne $expectedPins[$pin.name]) { Add-Error "$($pin.name): pin drift" }
  if ($expectedPolicy.ContainsKey($pin.name)) {
    $policy = $expectedPolicy[$pin.name]
    if ($pin.repository -ne $policy[0] -or $pin.decision -ne $policy[1] -or $pin.license -ne $policy[2] -or $pin.license_url -ne $policy[3]) { Add-Error "$($pin.name): immutable source policy drift" }
  }
  if ($pin.decision -in @('reference-only', 'rejected-runtime') -and @($pin.local_paths).Count -ne 0) { Add-Error "$($pin.name): $($pin.decision) cannot have local paths" }
  foreach ($local in @($pin.local_paths)) { Check-LocalArtifact $local $pin }
}
$actualPinSet = (@($seen.Keys | Sort-Object) -join ',')
$expectedPinSet = (@($expectedPins.Keys | Sort-Object) -join ',')
if ($actualPinSet -ne $expectedPinSet) { Add-Error 'immutable source pin set drift' }

$pretendard = @($map.source_pins | Where-Object { $_.name -eq 'pretendard' })[0]
if ($null -eq $pretendard -or $pretendard.release -ne 'v1.3.9' -or $pretendard.license -ne 'SIL OFL-1.1' -or $pretendard.materialized -ne $true -or @($pretendard.local_paths).Count -ne 1) { Add-Error 'Pretendard must be materialized with its pinned OFL contract' }
if (@($pretendard.upstream_paths).Count -ne 1 -or $pretendard.upstream_paths[0].path -ne 'packages/pretendard/dist/web/variable/woff2/PretendardVariable.woff2' -or $pretendard.upstream_paths[0].sha256 -ne '9599f12fd42fc0bce1cd50b47a0c022e108d7aa64dd0d1bb0ed44f3282d900b4') { Add-Error 'Pretendard binary pin drift' }
if ($pretendard.local_paths[0].path -ne 'apps/web/src/assets/fonts/PretendardVariable.woff2' -or $pretendard.local_paths[0].sha256 -ne '9599f12fd42fc0bce1cd50b47a0c022e108d7aa64dd0d1bb0ed44f3282d900b4' -or $pretendard.local_paths[0].test_path -ne 'apps/web/src/ui-system.test.tsx') { Add-Error 'Pretendard local materialization contract drift' }

function Check-ArtifactPolicy($entry, [string]$kind) {
  if (-not $pinsByName.ContainsKey($entry.source_pin)) { Add-Error "$kind has unknown source pin"; return }
  $pin = $pinsByName[$entry.source_pin]
  if ($pin.decision -in @('reference-only', 'rejected-runtime')) { Add-Error "$kind uses non-materializable source pin: $($entry.source_pin)" }
  if ($pin.license -eq 'Apache-2.0') {
    $matches = @($map.apache_adaptations | Where-Object { $_.source_pin -eq $entry.source_pin -and $_.path -eq $entry.path })
    if ($matches.Count -ne 1) { Add-Error "$kind requires exactly one Apache attribution linkage" }
    else {
      $adaptation = $matches[0]
      if ($adaptation.license_url -ne $pin.license_url -or $adaptation.notice_url -ne $pin.notice_url -or -not $adaptation.change_summary -or -not $adaptation.attribution) { Add-Error "$kind Apache attribution is incomplete or does not link direct upstream notices" }
    }
  }
}
foreach ($entry in @($map.materialized_files)) { Check-ArtifactPolicy $entry 'materialized file'; Check-Artifact $entry 'materialized file' }
foreach ($entry in @($map.generated_items)) { Check-ArtifactPolicy $entry 'generated item'; Check-Artifact $entry 'generated item' }
foreach ($adaptation in @($map.apache_adaptations)) {
  foreach ($field in @('source_pin', 'change_summary', 'license_url', 'notice_url', 'attribution')) {
    if (-not (Has-Property $adaptation $field) -or -not $adaptation.$field) { Add-Error "Apache adaptation missing $field" }
  }
}

if ($lock.repository -ne 'shadcn-ui/ui' -or $lock.commit -ne $expectedPins['shadcn-ui']) { Add-Error 'shadcn registry lock pin drift' }
if ($lock.live_npx_output_accepted -ne $false) { Add-Error 'live npx outputs are forbidden' }
if ($null -eq $lock.generated_items -or $null -eq $lock.dependency_mapping) { Add-Error 'registry lock shape missing generated_items or dependency_mapping' }
if (@($lock.generated_items).Count -ne 20) { Add-Error 'registry lock must contain 18 primitives plus utils and use-mobile helpers' }
foreach ($item in @($lock.generated_items)) {
  foreach ($field in @('name', 'upstream_path', 'upstream_sha256', 'generated_path', 'normalized_sha256', 'test_path', 'runtime_dependencies')) {
    if (-not (Has-Property $item $field) -or -not $item.$field) { Add-Error "generated registry item missing $field" }
  }
  if ($item.upstream_sha256 -notmatch $shaPattern -or $item.normalized_sha256 -notmatch $shaPattern) { Add-Error "generated registry item hash invalid" }
  if (Is-RepoRelative $item.generated_path) {
    $generated = Join-Path $root $item.generated_path
    if (-not (Test-Path -LiteralPath $generated -PathType Leaf)) { Add-Error "generated registry item path absent" }
    elseif ((Get-Sha256 $generated) -ne $item.normalized_sha256) { Add-Error "generated registry normalized hash drift" }
  } else { Add-Error 'generated registry path must be repository-relative' }
  foreach ($dependency in @($item.runtime_dependencies)) {
    $mapping = $lock.dependency_mapping.PSObject.Properties[$dependency].Value
    if ($null -eq $mapping -or -not $mapping.version -or -not $mapping.license -or -not $mapping.package_lock_entry) { Add-Error "runtime dependency lacks exact package-lock mapping: $dependency" }
    else {
      $resolved = if ($null -ne $packageLock -and $null -ne $packageLock.PSObject.Properties['packages']) { $packageLock.packages.PSObject.Properties[$mapping.package_lock_entry].Value } else { $null }
      if ($null -eq $resolved -or $null -eq $resolved.PSObject.Properties['version'] -or $resolved.version -ne $mapping.version) { Add-Error "runtime dependency package-lock drift: $dependency" }
      if ($mapping.package_lock_entry -ne "node_modules/$dependency") { Add-Error "runtime dependency package-lock entry does not match dependency: $dependency" }
    }
  }
}

foreach ($requiredNotice in @('No Apache-2.0 source is materialized', 'change summary', 'live npx')) {
  if (-not $notices.Contains($requiredNotice)) { Add-Error "notices missing: $requiredNotice" }
}

# Production-only scan: docs/tests and untracked pnpm files are deliberately not inputs.
$productionRoots = @((Join-Path $root 'apps/web/src'), (Join-Path $root 'apps/web/package.json'), (Join-Path $root 'apps/web/package-lock.json'))
$scanFiles = @()
foreach ($candidate in $productionRoots) {
  if (Test-Path -LiteralPath $candidate -PathType Container) { $scanFiles += Get-ChildItem -LiteralPath $candidate -Recurse -File | Where-Object { $_.Extension -in @('.ts', '.tsx', '.js', '.jsx', '.css') } }
  elseif (Test-Path -LiteralPath $candidate -PathType Leaf) { $scanFiles += Get-Item -LiteralPath $candidate }
}
foreach ($file in $scanFiles) {
  $content = Get-Content -Raw -LiteralPath $file.FullName
  if ($content -match '(?i)OpenCut-app/OpenCut|@opencut|(?:from\s*|import\s*(?:[^;]*?\s+from\s*)?|require\(\s*)["'']opencut(?:/|["''])|https?://[^"'']*opencut') { Add-Error "rejected OpenCut runtime reference: $($file.FullName)" }
  if ($content -match '(?i)@supabase/supabase-js|(?:from\s*|import\s*\(\s*|import\s*(?:[^;]*?\s+from\s*)?|require\(\s*)["'']supabase(?:/|["''])|https?://[^"'']*supabase') { Add-Error "reference-only Supabase runtime reference: $($file.FullName)" }
}
foreach ($dependencyField in @('dependencies', 'optionalDependencies', 'peerDependencies')) {
  $declared = $packageManifest.PSObject.Properties[$dependencyField].Value
  if ($null -ne $declared -and $null -ne $declared.PSObject.Properties['@supabase/supabase-js']) { Add-Error "reference-only Supabase declared dependency: $dependencyField" }
}
function Check-ReferenceOnlyDecision($decision) {
  foreach ($field in @('task', 'source_pin', 'reference', 'materialized_paths', 'local_paths', 'forbidden_import_terms')) {
    if (-not (Has-Property $decision $field)) { Add-Error "reference-only decision missing $field" }
    elseif ($field -notin @('materialized_paths', 'local_paths', 'forbidden_import_terms') -and -not $decision.$field) { Add-Error "reference-only decision missing $field" }
  }
  if (-not $decision.task) { return }
  if (-not $decision.source_pin -or -not $pinsByName.ContainsKey($decision.source_pin)) { Add-Error "$($decision.task) has an unknown source pin" }
  if (@($decision.materialized_paths).Count -ne 0) { Add-Error "$($decision.task) reference-only decision cannot materialize paths" }
  if (@($decision.local_paths).Count -eq 0) { Add-Error "$($decision.task) local path list missing" }
  foreach ($relative in @($decision.local_paths)) {
    if (-not (Is-RepoRelative $relative)) { Add-Error "$($decision.task) local path must be repository-relative"; continue }
    $path = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
      if ($decision.task -ne 'Task 14 timeline geometry') { Add-Error "$($decision.task) path absent: $relative" }
      continue
    }
    $content = Get-Content -Raw -LiteralPath $path
    if ($content -match 'Source-preservation header:') { Add-Error "$($decision.task) copied-source header forbidden: $relative" }
    foreach ($term in @($decision.forbidden_import_terms)) {
      if (-not $term) { Add-Error "$($decision.task) has an empty forbidden import term"; continue }
      if ($content -match ('(?i)' + [regex]::Escape($term))) { Add-Error "$($decision.task) forbidden runtime import term: $relative" }
    }
  }
  if (Has-Property $decision 'inspected_upstream_paths') {
    if (@($decision.inspected_upstream_paths).Count -eq 0) { Add-Error "$($decision.task) inspected upstream paths missing" }
    foreach ($upstream in @($decision.inspected_upstream_paths)) {
      if (-not (Has-Property $upstream 'path') -or -not (Has-Property $upstream 'sha256') -or -not (Is-RepoRelative $upstream.path) -or $upstream.sha256 -notmatch $shaPattern) {
        Add-Error "$($decision.task) inspected upstream path or SHA is invalid"
      }
    }
  }
}

$referenceOnlyDecisions = @($map.reference_only_decisions)
if ($referenceOnlyDecisions.Count -eq 0) { Add-Error 'reference-only provenance decisions missing' }

function Test-ExactStringList([object[]]$Actual, [object[]]$Expected) {
  if ($Actual.Count -ne $Expected.Count) { return $false }
  for ($index = 0; $index -lt $Expected.Count; $index++) {
    if ($Actual[$index] -ne $Expected[$index]) { return $false }
  }
  return $true
}
function Test-ExactUpstreamList([object[]]$Actual, [object[]]$Expected) {
  if ($Actual.Count -ne $Expected.Count) { return $false }
  for ($index = 0; $index -lt $Expected.Count; $index++) {
    $item = $Actual[$index]
    if ($null -eq $item -or -not (Test-ExactStringList -Actual @($item.PSObject.Properties.Name | Sort-Object) -Expected @('path', 'sha256'))) { return $false }
    if ($item.path -ne $Expected[$index].path -or $item.sha256 -ne $Expected[$index].sha256) { return $false }
  }
  return $true
}

$expectedTask11ForbiddenTerms = @('EditorCore', 'next/', 'database', 'renderer')
$task11 = @($referenceOnlyDecisions | Where-Object { $_.task -eq 'Task 11 editor workbench' })
if ($task11.Count -ne 1 -or
    $task11[0].source_pin -ne 'opencut-classic' -or
    @($task11[0].materialized_paths).Count -ne 0 -or
    -not (Test-ExactStringList -Actual @($task11[0].forbidden_import_terms) -Expected $expectedTask11ForbiddenTerms)) {
  Add-Error 'Task 11 reference-only provenance decision drift'
}

$expectedTask14Fields = @('task', 'source_pin', 'reference', 'materialized_paths', 'local_paths', 'inspected_upstream_paths', 'forbidden_import_terms')
$expectedTask14LocalPaths = @(
  'apps/web/src/features/editor/timeline/time-scale.ts',
  'apps/web/src/features/editor/timeline/timeline-geometry.ts',
  'apps/web/src/features/editor/timeline/snapping.ts',
  'apps/web/src/features/editor/timeline/hit-testing.ts'
)
$expectedTask14ForbiddenTerms = @('EditorCore', 'next/', 'database', 'renderer', 'IndexedDB', 'OPFS', 'browser-export', 'EditorCommandPort', 'document', 'window', 'canvas')
$expectedTask14UpstreamPaths = @(
  [pscustomobject]@{ path = 'apps/web/src/fps/utils.ts'; sha256 = 'b3d091725124abe21b348d34cb15643200fb8e650cbb2fab3ce16fb68c6dac28' },
  [pscustomobject]@{ path = 'apps/web/src/timeline/pixel-utils.ts'; sha256 = '373bcd4b0d9fd88da7cffb05bd3ea3368c8aabcb13f275147cfceb59e70eaef0' },
  [pscustomobject]@{ path = 'apps/web/src/timeline/snapping/build.ts'; sha256 = '7cf9b8dc203a691af38e99d16ceb401cb881055b93244f9f6afa65338ef46e1a' },
  [pscustomobject]@{ path = 'apps/web/src/timeline/snapping/resolve.ts'; sha256 = '73f7865940cd914b09070ca3daa03325b03a31bd33ebb6766dc0975736c6fc0d' },
  [pscustomobject]@{ path = 'apps/web/src/timeline/snapping/threshold.ts'; sha256 = '951ed0604bcd5960384a520a14cf66f554c2580f4e0098e0307939db73ced686' },
  [pscustomobject]@{ path = 'apps/web/src/timeline/zoom-utils.ts'; sha256 = '00d105f58146956d915b4614ee1796a73513ff786bed90dd07d1245ee2fb84b6' }
)
$task14 = @($referenceOnlyDecisions | Where-Object { $_.task -eq 'Task 14 timeline geometry' })
if ($task14.Count -ne 1) { Add-Error 'Task 14 reference-only provenance decision drift' }
else {
  $decision = $task14[0]
  if (-not (Test-ExactStringList -Actual @($decision.PSObject.Properties.Name | Sort-Object) -Expected @($expectedTask14Fields | Sort-Object)) -or
      $decision.source_pin -ne 'opencut-classic' -or
      $decision.reference -ne 'classic pure timeline math inspected; independent TypeScript implementation only' -or
      -not (Test-ExactStringList -Actual @($decision.materialized_paths) -Expected @()) -or
      -not (Test-ExactStringList -Actual @($decision.local_paths) -Expected $expectedTask14LocalPaths) -or
      -not (Test-ExactStringList -Actual @($decision.forbidden_import_terms) -Expected $expectedTask14ForbiddenTerms) -or
      -not (Test-ExactUpstreamList -Actual @($decision.inspected_upstream_paths) -Expected $expectedTask14UpstreamPaths)) {
    Add-Error 'Task 14 reference-only provenance decision drift'
  }
}

function Test-ForbiddenRuntimePatterns([string]$RelativePath, [string]$Boundary, [object[]]$Patterns, [bool]$AllowAbsent) {
  $path = Join-Path $root $RelativePath
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
    if (-not $AllowAbsent) { Add-Error "$Boundary path absent: $RelativePath" }
    return
  }
  $content = Get-Content -Raw -LiteralPath $path
  foreach ($entry in $Patterns) {
    if ($content -match $entry.pattern) { Add-Error "$Boundary forbidden runtime boundary: $RelativePath ($($entry.name))" }
  }
}

$task14PurePaths = @(
  'apps/web/src/features/editor/timeline/time-scale.ts',
  'apps/web/src/features/editor/timeline/timeline-geometry.ts',
  'apps/web/src/features/editor/timeline/snapping.ts',
  'apps/web/src/features/editor/timeline/hit-testing.ts'
)
$task14PurePatterns = @(
  [pscustomobject]@{ name = 'React import'; pattern = '(?i)(?:from\s*|import\s*(?:\(\s*)?|require\(\s*)["''](?:react|react-dom)(?:/|["''])' },
  [pscustomobject]@{ name = 'editor/API runtime'; pattern = '(?i)\b(?:EditorCommandPort|fetch\s*\(|axios\b)'} ,
  [pscustomobject]@{ name = 'DOM or canvas runtime'; pattern = '(?i)\b(?:document|window|HTMLElement|MouseEvent|KeyboardEvent|WheelEvent|canvas)\b' }
)
foreach ($relative in $task14PurePaths) { Test-ForbiddenRuntimePatterns -RelativePath $relative -Boundary 'Task 14 pure timeline math' -Patterns $task14PurePatterns -AllowAbsent $true }

$task16DockPatterns = @(
  [pscustomobject]@{ name = 'EditorCommandPort'; pattern = '(?i)\bEditorCommandPort\b' },
  [pscustomobject]@{ name = 'API request'; pattern = '(?i)\b(?:fetch\s*\(|axios\b)' },
  [pscustomobject]@{ name = 'API or command import'; pattern = '(?i)(?:from\s*|import\s*(?:\(\s*)?|require\(\s*)["''][^"'']*(?:api|command)[^"'']*["'']' },
  [pscustomobject]@{ name = 'direct mutation'; pattern = '(?i)\bmutate\s*\(' },
  [pscustomobject]@{ name = 'preview write'; pattern = '(?i)\b(?:write|set|update)(?:Preview|Session|Revision)\b' },
  [pscustomobject]@{ name = 'canvas'; pattern = '(?i)\bcanvas\b' }
)
Test-ForbiddenRuntimePatterns -RelativePath 'apps/web/src/features/editor/timeline/TimelineDock.tsx' -Boundary 'Task 16 local-draft timeline dock' -Patterns $task16DockPatterns -AllowAbsent $false

foreach ($decision in $referenceOnlyDecisions) { Check-ReferenceOnlyDecision $decision }
if ($null -ne $packageLock -and $null -ne $packageLock.PSObject.Properties['packages'] -and $null -ne $packageLock.packages.PSObject.Properties['node_modules/@supabase/supabase-js']) { Add-Error 'reference-only Supabase package-lock dependency' }

if ($errors.Count -gt 0) { throw ("Editor UI provenance verification failed:`n - " + ($errors -join "`n - ")) }
Write-Output 'Editor UI OSS provenance verification passed.'
