#!/bin/bash
cd "$(dirname "$0")"

echo "============================================"
echo " Gare di Mate -- Server"
echo "============================================"
echo

# Usa il venv locale se esiste, altrimenti il Python di sistema
if [ -f "venv/bin/python" ]; then
    echo "Ambiente virtuale rilevato."
    echo
    PYTHON="venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

echo "Server in ascolto su http://0.0.0.0:8000"
echo "Premi CTRL+C per fermare."
echo

exec "$PYTHON" -m uvicorn main:app --host 0.0.0.0 --port 8000

# Per la modalita sviluppo (ricarica automatica), sostituire la riga sopra con:
# exec "$PYTHON" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
