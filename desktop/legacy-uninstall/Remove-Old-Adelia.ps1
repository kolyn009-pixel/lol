# Uses the registered interactive uninstaller. Does not delete folders or profiles.
[CmdletBinding(SupportsShouldProcess=$true)]
param([switch]$ListOnly)
$ErrorActionPreference = 'Stop'
$keys = @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*')
$found = @(foreach ($key in $keys) {
    Get-ItemProperty $key -ErrorAction SilentlyContinue | Where-Object {
        $_.DisplayName -match '^(Аделия|Adelia)( Desktop)?$' -and $_.UninstallString
    } | ForEach-Object {
        # Only known old versions, never the new release or an unknown version.
        if ($_.DisplayVersion -match '^0\.(1|2)\.' -or $_.DisplayVersion -match '^0\.3\.0(?:-beta\.[12])?$') {
            [pscustomobject]@{Name=$_.DisplayName;Version=$_.DisplayVersion;Location=$_.InstallLocation;Command=$_.UninstallString;Key=$_.PSPath;Date=$_.InstallDate}
        }
    }
})
$found = @($found | Sort-Object Key -Unique | Sort-Object Date,Version)
if (!$found.Count) {
    Write-Host 'No registered old Adelia installation was found. Nothing was removed.'
    Write-Host 'Open Settings > Apps > Installed apps to inspect portable or differently named versions.'
    if (!$ListOnly) { Start-Process 'ms-settings:appsfeatures' }
    return
}
Write-Host 'Old Adelia installations found (the earliest known installation is listed first):'
for ($i=0; $i -lt $found.Count; $i++) { $x=$found[$i]; Write-Host "[$($i+1)] $($x.Name) $($x.Version)  $($x.Location)  Installed: $($x.Date)" }
if ($ListOnly) { return }
Write-Host 'The new release 0.3.0-beta.3 is excluded. Server data and chats are not touched by this helper.'
$choice=Read-Host 'Enter the number of the OLD installation to uninstall, or press Enter to cancel'
if (!$choice) { return }
$number=0
if (![int]::TryParse($choice,[ref]$number) -or $number -lt 1 -or $number -gt $found.Count) { throw 'Invalid selection. Nothing was removed.' }
$item=$found[$number-1]
$command=[Environment]::ExpandEnvironmentVariables($item.Command)
# Do not evaluate registry commands as PowerShell or invoke arbitrary shell flags.
$exe=$null
if ($command -match '^"([^"\r\n]+\.exe)"\s*$') { $exe=$matches[1] }
elseif ($command -match '^([^"\r\n]+\.exe)\s*$') { $exe=$matches[1].Trim() }
else { throw 'The registered uninstaller needs manual review. Use Windows Settings > Apps. Nothing was removed.' }
if (!(Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Registered uninstaller is missing. Nothing was removed.' }
if ([IO.Path]::GetFileName($exe) -notmatch '^(Uninstall (Adelia|Аделия)|unins\d*)\.exe$') { throw 'Unrecognized uninstaller name. Nothing was removed.' }
if ($PSCmdlet.ShouldProcess("$($item.Name) $($item.Version) at $($item.Location)", 'Run the registered interactive uninstaller')) {
    $result=Start-Process -FilePath $exe -PassThru -Wait
    Write-Host "Uninstaller exited with code $($result.ExitCode)."
}
