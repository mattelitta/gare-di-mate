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
        (str(ROOT / "templates"), "templates"),
        (str(ROOT / "static"), "static"),
        (ICON, "."),
        (str(ROOT / "VERSION"), "."),
    ] + collect_data_files("fpdf"),  # dati di fpdf2 (esportazione PDF)
    hiddenimports=collect_submodules("uvicorn") + ["esporta_pdf", "tls"],  # importati dentro una funzione
    excludes=["test_data", "test_live", "setup_test"],
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
