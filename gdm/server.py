"""Avvio del server: due porte, la stessa applicazione.

- HTTP_PORT (8000): per il computer server (127.0.0.1, il traffico non esce dal computer).
  Gli altri dispositivi che la usano vengono solo rimandati all'indirizzo HTTPS.
- HTTPS_PORT (8443): cifrata, per tablet e display della rete locale.

Uso da riga di comando, dalla radice del progetto (sviluppo e test):
    py -m gdm.server [--http-port 8000] [--https-port 8443]
"""
import argparse
import asyncio

import uvicorn

from gdm import tls

HTTP_PORT = 8000
HTTPS_PORT = 8443


def create_servers(app, http_port: int = HTTP_PORT, https_port: int = HTTPS_PORT,
                   log_config=uvicorn.config.LOGGING_CONFIG) -> list[uvicorn.Server]:
    """I due server uvicorn. Il ciclo di vita dell'app (avvio, battito) gira una volta sola: sul primo."""
    cert, key = tls.ensure_certificate()
    app.state.https_port = https_port
    http = uvicorn.Config(app, host="0.0.0.0", port=http_port, log_config=log_config)
    https = uvicorn.Config(app, host="0.0.0.0", port=https_port, log_config=log_config, lifespan="off",
                           ssl_certfile=str(cert), ssl_keyfile=str(key))
    return [uvicorn.Server(http), uvicorn.Server(https)]


def run(servers: list[uvicorn.Server]):
    """Esegue i server finché non viene chiesto di fermarli (should_exit) o finché uno si ferma."""
    async def main():
        tasks = [asyncio.create_task(s.serve()) for s in servers]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for s in servers:  # se uno si ferma (es. porta occupata) si ferma anche l'altro
            s.should_exit = True
        await asyncio.gather(*tasks, return_exceptions=True)
    asyncio.run(main())


def started(servers: list[uvicorn.Server]) -> bool:
    return all(s.started for s in servers)


def stop(servers: list[uvicorn.Server]):
    for s in servers:
        s.should_exit = True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gare di Mate: server")
    parser.add_argument("--http-port", type=int, default=HTTP_PORT)
    parser.add_argument("--https-port", type=int, default=HTTPS_PORT)
    args = parser.parse_args()
    from gdm.main import app
    run(create_servers(app, args.http_port, args.https_port))
