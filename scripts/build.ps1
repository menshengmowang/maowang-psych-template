$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller

$appName = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String("6a2U546L5b+D55CG5a2m5qih5p2/"))
$pyinstallerArgs = @(
    "--noconfirm"
    "--windowed"
    "--name"
    $appName
    "--paths"
    "src"
    "--collect-all"
    "pyJianYingDraft"
    "--hidden-import"
    "pyJianYingDraft"
    "--hidden-import"
    "mutagen"
    "--exclude-module"
    "pytest"
    "--exclude-module"
    "_pytest"
    "--exclude-module"
    "matplotlib"
    "--exclude-module"
    "IPython"
    "--exclude-module"
    "tkinter"
    "src\maowang_psych_template_starter.py"
)

& .\.venv\Scripts\pyinstaller.exe @pyinstallerArgs

Write-Host "Build finished: dist\$appName"
