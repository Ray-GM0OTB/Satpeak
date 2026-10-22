# Builds SatPeak.exe (PyInstaller) and the SatPeak-Setup-x.y.z.exe installer (Inno Setup 6).
# Needs: Python 3.10+, the libiio Windows installer (DLLs in System32), Inno Setup 6.
# Optional: put a built SatPeak.apk in this folder to include the Android app in the installer.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$here = $PSScriptRoot
$server = Resolve-Path "$here\..\server"
$log = Join-Path $here "build_exe_log.txt"; "" | Set-Content $log
function L($m){ $s="[{0}] {1}" -f (Get-Date -Format HH:mm:ss),$m; Write-Host $s; Add-Content $log $s }
function RunCmd($exe,$a){ L ("> $exe " + ($a -join " ")); $o = & $exe @a 2>&1 | Out-String; Add-Content $log $o; Write-Host $o; return $LASTEXITCODE }

# Python
$py = $null
foreach ($c in @(@("py", @("-3")), @("python", @()))) {
    if (Get-Command $c[0] -ErrorAction SilentlyContinue) {
        $exe = & $c[0] @($c[1]) -c "import sys;print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) { $py = $exe.Trim(); break }
    }
}
if (-not $py) { L "FAIL: Python 3 not found"; exit 1 }
L "Python: $py"

RunCmd $py @("-m","pip","install","--disable-pip-version-check","-q","-r","$server\requirements.txt","pyinstaller","pefile") | Out-Null
$rc = RunCmd $py @("$server\selftest.py"); L "selftest rc=$rc"
if ($rc -ne 0) { L "FAIL: selftest"; exit 1 }

$dlls = @("libiio.dll","libusb-1.0.dll","libxml2.dll","libserialport-0.dll")
foreach ($d in $dlls) { if (-not (Test-Path "C:\Windows\System32\$d")) { L "FAIL: $d not in System32 - install libiio for Windows first"; exit 1 } }
$bins = $dlls | ForEach-Object { "--add-binary=C:\Windows\System32\$_;." }
$pa = @("-m","PyInstaller","--noconfirm","--clean","--console","--name","SatPeak",
  "--icon=$here\satpeak.ico","--contents-directory=.","--distpath=$here\dist","--workpath=$here\work","--specpath=$here\work",
  "--add-data=$server\index.html;.","--hidden-import=iio","--collect-submodules=adi") + $bins + @("$server\qo100_peaker.py")
$rc = RunCmd $py $pa; L "pyinstaller rc=$rc"
if (-not (Test-Path "$here\dist\SatPeak\SatPeak.exe")) { L "FAIL: no exe"; exit 1 }

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe","$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { L "FAIL: Inno Setup 6 not found"; exit 1 }
$rc = RunCmd $iscc @("/Q","$here\satpeak.iss"); L "iscc rc=$rc"
Get-ChildItem "$here\output\*.exe" | ForEach-Object { L ("installer: {0} {1:N1} MB" -f $_.FullName, ($_.Length/1MB)) }
L "BUILD DONE"
