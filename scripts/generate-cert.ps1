# Windows equivalent of generate-cert.sh — see that file for why this cert
# is shared and persisted instead of using per-process ephemeral certs.
$ErrorActionPreference = "Stop"

$CertDir = Join-Path $PSScriptRoot "..\certs"
New-Item -ItemType Directory -Force -Path $CertDir | Out-Null
$Cert = Join-Path $CertDir "cert.pem"
$Key = Join-Path $CertDir "key.pem"

if ((Test-Path $Cert) -and (Test-Path $Key) -and ($env:FORCE_REGEN -ne "1")) {
    Write-Host "TLS certificate already exists at $CertDir (set `$env:FORCE_REGEN='1' to regenerate)."
    exit 0
}

$SanList = @("DNS:localhost", "IP:127.0.0.1")
$LocalIps = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object -ExpandProperty IPAddress
foreach ($ip in $LocalIps) { $SanList += "IP:$ip" }

if ($env:EXTRA_SAN) {
    foreach ($entry in $env:EXTRA_SAN -split ",") { $SanList += "IP:$entry" }
}

$San = $SanList -join ","
Write-Host "Generating self-signed cert with SAN: $San"

$OpenSsl = Get-Command openssl -ErrorAction SilentlyContinue
if ($OpenSsl) {
    $OpenSslPath = $OpenSsl.Source
} else {
    $Fallbacks = @(
        "$env:ProgramFiles\Git\usr\bin\openssl.exe",
        "$env:ProgramFiles\Git\mingw64\bin\openssl.exe"
    )
    $OpenSslPath = $Fallbacks | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $OpenSslPath) {
        throw "openssl not found on PATH and no bundled Git openssl.exe was located. Install OpenSSL or Git for Windows."
    }
}

& $OpenSslPath req -x509 -newkey rsa:2048 -nodes `
    -keyout $Key -out $Cert `
    -days 825 `
    -subj "/CN=digital-arrest-scam-shield" `
    -addext "subjectAltName=$San"

Write-Host "Certificate written to $CertDir"
