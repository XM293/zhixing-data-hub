param(
    [Parameter(Mandatory = $true)]
    [string]$CredentialPath,
    [string]$Model = "gpt-5.4-mini",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$resolvedCredentialPath = (Resolve-Path -LiteralPath $CredentialPath).Path
$credentialValues = @{}

foreach ($line in Get-Content -LiteralPath $resolvedCredentialPath) {
    if ($line -match '^\s*([A-Z][A-Z0-9_]+)\s*=\s*(.+?)\s*$') {
        $credentialValues[$matches[1]] = $matches[2].Trim().Trim('"').Trim("'")
    }
}

if (-not $credentialValues.ContainsKey("API_KEY") -or
    -not $credentialValues.ContainsKey("API_BASE_URL")) {
    throw "Credential file must contain API_KEY and API_BASE_URL."
}

$env:AI_ENABLED = "true"
$env:AI_API_KEY = $credentialValues["API_KEY"]
$env:AI_BASE_URL = $credentialValues["API_BASE_URL"]
$env:AI_MODEL = $Model
$env:AI_TIMEOUT_SECONDS = "90"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$apiDirectory = Join-Path $repositoryRoot "services/api"
$uvicorn = Join-Path $repositoryRoot ".venv/Scripts/uvicorn.exe"

Set-Location -LiteralPath $apiDirectory
& $uvicorn zhixing_api.main:app --app-dir src --host 127.0.0.1 --port $Port
