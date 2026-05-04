"""
Simple message protocol over a TCP/TLS stream.
Each message is a JSON object terminated by a newline character.
"""

import json

ENCODING = "utf-8"

def send_msg(sock, msg: dict):
    """Serialize dict to JSON and send over socket."""
    data = json.dumps(msg) + "\n"
    sock.sendall(data.encode(ENCODING))

def recv_msg(sock) -> dict | None:
    """
    Read one newline-terminated JSON message from socket.
    Returns None if connection closed.
    """
    buf = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            return None         # Connection closed
        buf += chunk
        if b"\n" in buf:
            line, _ = buf.split(b"\n", 1)
            return json.loads(line.decode(ENCODING))