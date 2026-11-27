"""Certificato HTTPS autofirmato per gli altri dispositivi della rete locale.

Senza internet non si può avere un certificato pubblico: il programma ne crea uno da sé, valido
per tutti gli indirizzi di rete di questo computer. I browser mostrano un avviso da accettare una
volta (per ogni certificato); da lì il traffico è cifrato e nessuno sulla rete può leggerlo.
Il certificato viene rifatto quando cambia l'indirizzo del computer o quando sta per scadere;
la chiave privata resta la stessa e non lascia mai questo computer.
"""
import datetime
import ipaddress
import logging
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from gdm.paths import DATA_DIR

log = logging.getLogger(__name__)

CERT_DIR = DATA_DIR / "certificato"
KEY_PATH = CERT_DIR / "chiave.pem"
CERT_PATH = CERT_DIR / "certificato.pem"
VALIDITY_DAYS = 820          # sotto i limiti che alcuni sistemi applicano ai certificati
RENEW_BEFORE_DAYS = 30


def local_ips() -> list[str]:
    """Tutti gli indirizzi IPv4 di questo computer (più 127.0.0.1)."""
    ips = {"127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:  # l'indirizzo della rete principale, anche se il nome del computer non lo risolve
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # nessun pacchetto inviato: serve solo a scegliere l'interfaccia
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ips, key=lambda ip: tuple(int(p) for p in ip.split(".")))


def _load_or_create_key() -> ec.EllipticCurvePrivateKey:
    if KEY_PATH.exists():
        key = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
        if isinstance(key, ec.EllipticCurvePrivateKey):
            return key
    key = ec.generate_private_key(ec.SECP256R1())
    KEY_PATH.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return key


def _needs_new_cert(ips: list[str]) -> bool:
    if not CERT_PATH.exists() or not KEY_PATH.exists():
        return True
    try:
        cert = x509.load_pem_x509_certificate(CERT_PATH.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        covered = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
    except Exception:
        return True
    expires = cert.not_valid_after_utc
    soon = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=RENEW_BEFORE_DAYS)
    return expires < soon or not set(ips) <= covered


def ensure_certificate() -> tuple[Path, Path]:
    """Certificato e chiave pronti per gli indirizzi attuali. Ritorna (certificato, chiave)."""
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    ips = local_ips()
    if _needs_new_cert(ips):
        key = _load_or_create_key()
        now = datetime.datetime.now(datetime.timezone.utc)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Gare di Mate"),
                          x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Gare di Mate (rete locale)")])
        hostname = socket.gethostname()
        alt = [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ips]
        alt += [x509.DNSName("localhost"), x509.DNSName(hostname), x509.DNSName(f"{hostname}.local")]
        cert = (
            x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=VALIDITY_DAYS))
            .add_extension(x509.SubjectAlternativeName(alt), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False, content_commitment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .sign(key, hashes.SHA256())
        )
        CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        log.info("Nuovo certificato HTTPS per %s", ", ".join(ips))
    return CERT_PATH, KEY_PATH


def fingerprint() -> str:
    """Impronta SHA-256 del certificato (quella mostrata dai browser), a coppie di cifre."""
    try:
        cert = x509.load_pem_x509_certificate(CERT_PATH.read_bytes())
    except Exception:
        return ""
    return ":".join(f"{b:02X}" for b in cert.fingerprint(hashes.SHA256()))
