<#
  Sets up the Python environment for cs2-skin-ai on Windows.

  Why this dance: this machine ships Python 3.14 (no PyTorch wheels yet) and has Smart App Control
  ON, which blocks unsigned helper exes like uv.exe. So we use the *signed* official Python 3.12
  (via winget) + the stdlib venv, and always invoke tools as `python -m ...` to avoid the unsigned
  console-script shims SAC would block. The GPU is Blackwell (RTX 50xx) -> needs the CUDA 12.8 torch.
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $root ".venv\Scripts\python.exe"

# 1. Ensure Python 3.12 (signed, leaves system 3.14 alone)
$p312 = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $p312)) {
    Write-Host "Installing Python 3.12 via winget..." -ForegroundColor Cyan
    winget install --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
}

# 2. Create venv
if (-not (Test-Path $venvPy)) {
    Write-Host "Creating .venv (Python 3.12)..." -ForegroundColor Cyan
    & $p312 -m venv (Join-Path $root ".venv")
}
& $venvPy -m pip install --upgrade pip setuptools wheel

# 3. PyTorch with CUDA 12.8 (Blackwell). MUST come from the cu128 index.
Write-Host "Installing PyTorch (CUDA 12.8)..." -ForegroundColor Cyan
& $venvPy -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128

# 4. Everything else (from PyPI)
Write-Host "Installing project dependencies..." -ForegroundColor Cyan
& $venvPy -m pip install -e $root

# 4b. pyrender hard-pins PyOpenGL==3.1.0, which is broken on Python 3.12 (glGenTextures ctypes
#     error during texture upload). Force a newer PyOpenGL; pyrender works fine with it.
Write-Host "Patching PyOpenGL for Python 3.12..." -ForegroundColor Cyan
& $venvPy -m pip install --no-deps "PyOpenGL==3.1.7"

# 5. Sanity check
& $venvPy -c "import torch; print('torch', torch.__version__, '| cuda', torch.cuda.is_available(), '|', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO CUDA')"
Write-Host "Done. Run:  .\.venv\Scripts\python.exe -m cs2skin.cli --help" -ForegroundColor Green
