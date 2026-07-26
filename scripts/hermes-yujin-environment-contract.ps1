function Get-HermesYujinEnvironmentScalarValues {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Environment
    )

    $values = New-Object System.Collections.Generic.List[string]
    foreach ($property in @($Environment.PSObject.Properties)) {
        $value = $property.Value
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
