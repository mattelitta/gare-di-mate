import ctypes
import sys
import uuid
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

# Nel pacchetto PyInstaller i file dell'app sono estratti in sys._MEIPASS (template e file statici,
# VERSION e icona tutti lì). Da sorgente: template e statici nel pacchetto gdm/, VERSION nella radice
# del progetto (ROOT_DIR).
_MEIPASS = getattr(sys, "_MEIPASS", None)
BASE_DIR = Path(_MEIPASS) if _MEIPASS else Path(__file__).resolve().parent
ROOT_DIR = Path(_MEIPASS) if _MEIPASS else BASE_DIR.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def _documents_dir() -> Path:
    """Cartella Documenti reale (anche se reindirizzata, es. su OneDrive)."""
    try:
        folder_id = uuid.UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")
        guid = (ctypes.c_byte * 16).from_buffer_copy(folder_id.bytes_le)
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(guid, 0, None, ctypes.byref(out)) == 0:
            path = Path(out.value)
            ctypes.windll.ole32.CoTaskMemFree(out)
            return path
    except Exception:
        pass
    return Path.home() / "Documents"


# Installato i dati (database, backup, certificato, log) vanno in Documenti\Gare di Mate; da sorgente
# nella cartella dati/ del progetto (ignorata da git).
DATA_DIR = _documents_dir() / "Gare di Mate" if FROZEN else ROOT_DIR / "dati"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "gare.db"
