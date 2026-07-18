Describe "verify_container_stack" {
    It "rejects an extra snapshot file absent from the manifest" {
        $scriptPath = Join-Path $PSScriptRoot "..\scripts\verify_container_stack.ps1"
        $dataRoot = Join-Path $TestDrive "container-data"
        $snapshotRoot = Join-Path $dataRoot "snapshot"
        $runtimeRoot = Join-Path $dataRoot "runtime"
        $trackedFile = Join-Path $snapshotRoot "projects\demo\asset.bin"
        $extraFile = Join-Path $snapshotRoot "projects\demo\untracked.bin"
        New-Item -ItemType Directory -Force -Path (Split-Path $trackedFile), $runtimeRoot | Out-Null
        [IO.File]::WriteAllBytes($trackedFile, [byte[]](1, 2, 3))
        [IO.File]::WriteAllBytes($extraFile, [byte[]](4, 5, 6))
        $manifest = [ordered]@{
            layout_version = 1
            snapshot_root = "snapshot"
            source_preserved = $true
            file_hashes = [ordered]@{
                "projects/demo/asset.bin" = (Get-FileHash -Algorithm SHA256 -LiteralPath $trackedFile).Hash.ToLowerInvariant()
            }
        }
        $manifest | ConvertTo-Json -Depth 4 | Set-Content -NoNewline -Encoding utf8 (Join-Path $snapshotRoot "container-migration-manifest.json")

        { & $scriptPath -DataRoot $dataRoot } | Should -Throw "*unmanifested*"
    }
}
