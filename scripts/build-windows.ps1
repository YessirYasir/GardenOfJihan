$ErrorActionPreference = "Stop"
python -m pip install -e ".[windows,ai]"
pyinstaller --noconfirm --clean --name GardenOfJihan --collect-all garden_jihan --add-data "src/garden_jihan/ui;garden_jihan/ui" src/garden_jihan/launcher.py
Write-Host "Build created under dist/GardenOfJihan"
