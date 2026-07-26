function Get-HermesYujinEnvironmentScalarValues {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Environment
    )

    if ($null -eq $Environment) {
        throw "Resolved Compose environment must be a scalar map."
    }
    if (
        -not (
            $Environment -is [System.Collections.IDictionary] -or
            $Environment -is [pscustomobject]
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
