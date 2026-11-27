# -*- mode: python ; coding: utf-8 -*-
# Build: py -m PyInstaller --noconfirm --clean packaging\GareDiMate.spec  (oppure build_installer.bat)
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
ICON = str(ROOT / "packaging" / "icon.ico")

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(ROOT / "gdm" / "templates"), "templates"),
        (str(ROOT / "gdm" / "static"), "static"),
        (ICON, "."),
        (str(ROOT / "VERSION"), "."),
    ] + collect_data_files("fpdf"),  # dati di fpdf2 (esportazione PDF)
    # tutto il pacchetto gdm (alcuni moduli si importano dentro una funzione, es. esporta_pdf e tls)
    hiddenimports=collect_submodules("uvicorn") + collect_submodules("gdm"),
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GareDiMate",
    console=False,
    icon=ICON,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="GareDiMate", upx=False)
