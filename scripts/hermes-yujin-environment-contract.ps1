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
        [string[]]$CredentialValues,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    $environmentValues = @(
        Get-HermesYujinEnvironmentScalarValues -Environment $Environment
    )
    foreach ($environmentValue in $environmentValues) {
        foreach ($credentialValue in $CredentialValues) {
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
    }
}
