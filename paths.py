import ctypes
import sys
import uuid
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

# Nel pacchetto PyInstaller i file dell'app sono estratti in sys._MEIPASS.
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
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


# Da sorgente il database resta nella cartella del progetto; installato va in Documenti.
DATA_DIR = _documents_dir() / "Gare di Mate" if FROZEN else BASE_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "gare.db"
