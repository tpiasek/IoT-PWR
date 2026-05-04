HOST     = "0.0.0.0"      # Change to server's LAN IP when on real network
PORT     = 5000
DEVICE_ID = "pi-node-01"

USE_TLS  = False            # Set True when using real certs

CERT_DIR    = "./certs"
CA_CERT     = f"{CERT_DIR}/ca.crt"
SERVER_CERT = f"{CERT_DIR}/server.crt"
SERVER_KEY  = f"{CERT_DIR}/server.key"
CLIENT_CERT = f"{CERT_DIR}/client.crt"
CLIENT_KEY  = f"{CERT_DIR}/client.key"

HEARTBEAT_INTERVAL = 5      # seconds
USE_DOCKER_SANDBOX = False  # Set True on real Pi