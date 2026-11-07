param(
    [Parameter(Mandatory)] [string] $VmHost,
    [Parameter(Mandatory)] [string] $VmUser,
    [string] $KeyPath = "$env:USERPROFILE\.ssh\uptime_deploy",
    [ValidateSet("deploy", "bootstrap", "release")] [string] $Action = "deploy"
)

$RemoteDir = "/opt/uptime-monitor"
$Target = "$VmUser@$VmHost"
$SourceItems = "app", "monitor", "db", "migrations", "grafana", "deploy", "alembic.ini", "pyproject.toml", "README.md"
$Archive = Join-Path $env:TEMP "uptime-monitor.tgz"

Set-Location (Join-Path $PSScriptRoot "..")

function Invoke-Native([string] $Executable, [string[]] $Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed with exit code $LASTEXITCODE" }
}

function Invoke-Remote([string] $Command) {
    Invoke-Native ssh @("-i", $KeyPath, $Target, $Command)
}

function Send-Source {
    Invoke-Native tar (@("-czf", $Archive) + $SourceItems)
    Invoke-Native scp @("-i", $KeyPath, $Archive, "${Target}:/tmp/uptime-monitor.tgz")
    Invoke-Remote "cd $RemoteDir && rm -rf app db monitor migrations grafana deploy && tar -xzf /tmp/uptime-monitor.tgz && find deploy -type f -exec sed -i 's/\r//g' {} +"
}

switch ($Action) {
    "bootstrap" { Send-Source; Invoke-Remote "bash $RemoteDir/deploy/bootstrap.sh $VmHost" }
    "release"   { Invoke-Remote "bash $RemoteDir/deploy/release.sh" }
    "deploy"    { Send-Source; Invoke-Remote "bash $RemoteDir/deploy/release.sh" }
}