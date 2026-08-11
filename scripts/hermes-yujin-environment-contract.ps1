function Get-HermesYujinEnvironmentScalarValues {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Environment
    )

    if ($null -eq $Environment) {
        throw "Resolved Compose environment must be a scalar map."
    }
    # `[pscustomobject]`는 타입 리터럴로 쓰면 `[psobject]`로 풀린다. 파이프라인을 지난
    # 값은 무엇이든 psobject이므로 **문자열도 숫자도 배열도 전부 참**이었고, 이 가드는
    # 스칼라를 한 번도 막지 못했다. 실제 타입 이름으로 판정해야 진짜 맵만 통과한다.
    if (
        -not (
            $Environment -is [System.Collections.IDictionary] -or
            $Environment -is [System.Management.Automation.PSCustomObject]
        )
    ) {
        throw "Resolved Compose environment must be a scalar map."
    }

    $values = New-Object System.Collections.Generic.List[string]
    if ($Environment -is [System.Collections.IDictionary]) {
        $entries = @($Environment.Keys)
    }
    else {
        $entries = @($Environment.PSObject.Properties)
    }
    foreach ($entry in $entries) {
        if ($Environment -is [System.Collections.IDictionary]) {
            $value = $Environment[$entry]
        }
        else {
            $value = $entry.Value
        }
        if (
            $null -eq $value -or
            ($value -is [System.Collections.IEnumerable] -and
                -not ($value -is [string])) -or
            -not ($value -is [string] -or $value -is [ValueType])
        ) {
            throw "Resolved Compose environment must be a scalar map."
        }
        $values.Add([string]$value)
    }
    return $values.ToArray()
}

function Assert-NoHermesYujinCredentialValueAliases {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Environment,
        [Parameter(Mandatory = $true)]
        [string[]]$ExactCredentialValues,
        [Parameter(Mandatory = $true)]
        [string[]]$SecretSubstringValues,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    $environmentValues = @(
        Get-HermesYujinEnvironmentScalarValues -Environment $Environment
    )
    foreach ($comparisonValue in @(
        $ExactCredentialValues
        $SecretSubstringValues
    )) {
        if ([string]::IsNullOrEmpty($comparisonValue)) {
            throw "Credential comparison values must be nonempty."
        }
    }
    foreach ($environmentValue in $environmentValues) {
        foreach ($credentialValue in $ExactCredentialValues) {
            if (
                [string]::Equals(
                    $environmentValue,
                    $credentialValue,
                    [StringComparison]::Ordinal
                )
            ) {
                throw $FailureMessage
            }
        }
        foreach ($secretValue in $SecretSubstringValues) {
            if (
                $environmentValue.IndexOf(
                    $secretValue,
                    [StringComparison]::Ordinal
                ) -ge 0
            ) {
                throw $FailureMessage
            }
        }
    }
}
