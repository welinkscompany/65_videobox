param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [ValidateRange(600, 600)]
    [int]$DurationSec = 600,
    [string]$FfmpegBinary = "ffmpeg",
    [string]$FfprobeBinary = "ffprobe"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

function Get-WaveDurationSec {
    param([Parameter(Mandatory = $true)][string]$Path)

    $raw = & $FfprobeBinary -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 $Path
    if ($LASTEXITCODE -ne 0) {
        throw "ffprobe could not inspect raw narration '$Path'."
    }
    return [double]::Parse($raw.Trim(), [Globalization.CultureInfo]::InvariantCulture)
}

function Get-SHA256Hex {
    param([Parameter(Mandatory = $true)][string]$Path)

    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}

$output = [IO.Path]::GetFullPath($OutputPath)
$outputDirectory = Split-Path -Parent $output
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $heami = $voice.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Name -eq "Microsoft Heami Desktop" } | Select-Object -First 1
    if ($null -eq $heami) {
        throw "Required Korean SAPI voice 'Microsoft Heami Desktop' is not installed."
    }
    $voice.SelectVoice("Microsoft Heami Desktop")
    $voice.Rate = 8

    # This is intentionally a numbered, varied corpus. It is neither a short phrase
    # repeat nor silence padding: every utterance includes a unique ordinal, topic,
    # example, and editing instruction.
    # Windows PowerShell 5.1 requires a BOM for source files with literal Hangul.
    # Keep this script ASCII-only so it runs reliably from a UTF-8 checkout.
    $topics = @(
        "\uC544\uCE68 \uC2DC\uC7A5\uC758 \uBCC0\uD654", "\uC791\uC740 \uD68C\uC0AC\uC758 \uC5C5\uBB34 \uBC29\uC2DD",
        "\uB3C4\uC2DC \uACF5\uC6D0\uC758 \uACC4\uC808", "\uC8FC\uBC29\uC758 \uC548\uC804 \uC218\uCE59",
        "\uC628\uB77C\uC778 \uAC15\uC758\uC758 \uC9D1\uC911 \uBC29\uBC95", "\uC5EC\uD589 \uC608\uC0B0\uC758 \uAE30\uB85D",
        "\uC9C0\uC5ED \uB3C4\uC11C\uAD00\uC758 \uC5ED\uD560", "\uC7AC\uD65C\uC6A9\uC758 \uC2E4\uC81C \uACFC\uC815",
        "\uC6B4\uB3D9\uC744 \uC2DC\uC791\uD558\uB294 \uBC29\uBC95", "\uC601\uC0C1 \uD3B8\uC9D1\uC758 \uAE30\uBCF8 \uC6D0\uCE59",
        "\uACE0\uAC1D \uC778\uD130\uBDF0\uC758 \uC9C8\uBB38\uBC95", "\uC2DD\uBB3C \uAD00\uB9AC\uC758 \uAD00\uCC30"
    ) | ForEach-Object { [regex]::Unescape($_) }
    $examples = @(
        "\uD604\uC7A5\uC758 \uC18C\uB9AC\uC640 \uC22B\uC790\uB97C \uD568\uAED8 \uD655\uC778\uD569\uB2C8\uB2E4",
        "\uD55C \uAC00\uC9C0 \uC120\uD0DD\uC758 \uC774\uC720\uB97C \uC9E7\uAC8C \uC124\uBA85\uD569\uB2C8\uB2E4",
        "\uC2E4\uD328\uD55C \uC2DC\uB3C4\uB3C4 \uB2E4\uC74C \uD310\uB2E8\uC744 \uB3D5\uB294 \uC790\uB8CC\uAC00 \uB429\uB2C8\uB2E4",
        "\uD654\uBA74 \uC804\uD658\uC740 \uC774\uC57C\uAE30\uC758 \uD638\uD761\uC5D0 \uB9DE\uCDA5\uB2C8\uB2E4",
        "\uC2DC\uCCAD\uC790\uAC00 \uBC14\uB85C \uB530\uB77C \uD560 \uC218 \uC788\uB294 \uC21C\uC11C\uB97C \uB0A8\uAE41\uB2C8\uB2E4",
        "\uC11C\uB85C \uB2E4\uB978 \uC758\uACAC\uC744 \uBE44\uAD50\uD574 \uACB0\uB860\uC744 \uB9CC\uB4ED\uB2C8\uB2E4"
    ) | ForEach-Object { [regex]::Unescape($_) }
    $sentenceTemplate = [regex]::Unescape("{0}\uBC88\uC9F8 \uAE30\uB85D\uC785\uB2C8\uB2E4. \uC624\uB298\uC740 {1}\uC744 \uC0B4\uD3B4\uBD05\uB2C8\uB2E4. {2}. \uC774 \uC0AC\uB840\uC5D0\uC11C\uB294 \uC2DC\uC791\uACFC \uBCC0\uD654, \uADF8\uB9AC\uACE0 \uD655\uC778\uD574\uC57C \uD560 \uACB0\uACFC\uB97C \uC21C\uC11C\uB300\uB85C \uC815\uB9AC\uD569\uB2C8\uB2E4. \uB2E4\uC74C \uC7A5\uBA74\uC5D0\uC11C\uB294 {0}\uBC88 \uD56D\uBAA9\uC758 \uD575\uC2EC \uBB38\uC7A5\uC744 \uC790\uB9C9\uC73C\uB85C \uB2E4\uC2DC \uD655\uC778\uD558\uACA0\uC2B5\uB2C8\uB2E4.")
    $rawPath = Join-Path $outputDirectory ([IO.Path]::GetFileNameWithoutExtension($output) + ".raw.wav")
    if (Test-Path -LiteralPath $rawPath) { Remove-Item -LiteralPath $rawPath -Force }
    $voice.SetOutputToWaveFile($rawPath)
    for ($index = 1; $index -le 120; $index++) {
        $topic = $topics[($index - 1) % $topics.Count]
        $example = $examples[($index - 1) % $examples.Count]
        $voice.Speak(($sentenceTemplate -f $index, $topic, $example))
    }
    $voice.SetOutputToNull()

    $rawDuration = Get-WaveDurationSec -Path $rawPath
    if ($rawDuration -lt $DurationSec) {
        throw "Raw narration is only $rawDuration seconds. Refusing to use repeated speech or silence padding to reach $DurationSec seconds."
    }

    & $FfmpegBinary -y -i $rawPath -t $DurationSec -ar 48000 -ac 2 -c:a pcm_s16le $output
    if ($LASTEXITCODE -ne 0) {
        throw "ffmpeg could not trim the Korean raw narration to $DurationSec seconds."
    }
    $duration = Get-WaveDurationSec -Path $output
    if ([Math]::Abs($duration - $DurationSec) -gt 0.1) {
        throw "Generated narration duration $duration is outside $DurationSec +/- 0.1 seconds."
    }

    $hash = Get-SHA256Hex -Path $output
    Remove-Item -LiteralPath $rawPath -Force
    [pscustomobject]@{
        output_path = $output
        duration_sec = $duration
        sha256 = $hash
        raw_duration_sec = $rawDuration
        repeat_or_silence_padding_used = $false
    } | ConvertTo-Json -Depth 3
}
finally {
    $voice.Dispose()
}
