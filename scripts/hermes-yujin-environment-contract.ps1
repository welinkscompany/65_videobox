function Get-HermesYujinEnvironmentScalarValues {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Environment
    )

    if ($null -eq $Environment) {
        throw "Resolved Compose environment must be a scalar map."
    }
    if ($Environment -is [System.Collections.IDictionary]) {
        $rawValues = @($Environment.Values)
    }
    elseif ($Environment -is [pscustomobject]) {
        $rawValues = @(
            $Environment.PSObject.Properties | ForEach-Object { $_.Value }
        )
    }
    else {
        throw "Resolved Compose environment must be a scalar map."
    }

    $values = New-Object System.Collections.Generic.List[string]
    foreach ($value in $rawValues) {
        if (
            $null -eq $value -or
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
