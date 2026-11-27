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

echo "Questo computer:     http://localhost:8000"
echo "Altri dispositivi:   https://IP-DEL-COMPUTER:8443  (avviso del certificato da accettare)"
echo "Premi CTRL+C per fermare."
echo

exec "$PYTHON" server.py
