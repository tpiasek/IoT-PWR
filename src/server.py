#!/usr/bin/env python3
"""
IoT Server — listens for one client (the Pi), sends tasks, receives results.
Usage: python3 server.py
Commands:
  send <code>   — send a Python one-liner
  file <path>   — send a .py file
  status        — show last known Pi state
  quit
"""

import socket, ssl, threading, time, uuid
from protocol import send_msg, recv_msg
from config import *

pi_status  = {"state": "unknown"}
connection = None     # The active client socket
conn_lock  = threading.Lock()

# ── Receive loop (runs in background thread) ──────────────────────────────────

def receive_loop(sock):
    global pi_status
    print("[SERVER] Receive loop started")

    while True:
        try:
            msg = recv_msg(sock)
            if msg is None:
                print("\n[SERVER] Client disconnected.")
                break

            kind = msg.get("kind")

            if kind == "status":
                pi_status = msg
                print(f"\r[PI] state={msg.get('state')} | "
                      f"cpu={msg.get('cpu')}% | "
                      f"mem={msg.get('mem')}%        ",
                      end="", flush=True)

            elif kind == "result":
                print(f"\n\n{'='*50}")
                print(f"[RESULT] task_id : {msg.get('task_id')}")
                print(f"         exit    : {msg.get('exit_code')}")
                print(f"         stdout  :\n{msg.get('stdout', '').strip()}")
                if msg.get("stderr"):
                    print(f"         stderr  :\n{msg.get('stderr').strip()}")
                print(f"{'='*50}\n> ", end="", flush=True)

        except (ConnectionResetError, BrokenPipeError, OSError):
            print("\n[SERVER] Connection lost.")
            break

# ── TLS / plain socket setup ──────────────────────────────────────────────────

def make_server_socket() -> socket.socket:
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    raw.bind(("0.0.0.0", PORT))
    raw.listen(1)

    if USE_TLS:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(SERVER_CERT, SERVER_KEY)
        ctx.load_verify_locations(CA_CERT)
        ctx.verify_mode = ssl.CERT_REQUIRED   # Mutual TLS — client must present cert
        return ctx.wrap_socket(raw, server_side=True)

    return raw

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global connection

    server_sock = make_server_socket()
    tls_label   = "TLS" if USE_TLS else "plain TCP (dev mode)"
    print(f"[SERVER] Listening on {HOST}:{PORT} ({tls_label})")
    print(f"[SERVER] Waiting for Pi to connect...\n")

    # Accept one client, then enter prompt
    # For multi-client, wrap this in a loop and track connections in a dict
    conn, addr = server_sock.accept()
    connection = conn
    print(f"[SERVER] Pi connected from {addr}\n")

    threading.Thread(target=receive_loop, args=(conn,), daemon=True).start()

    # Interactive prompt
    print("Commands: send <code> | file <path> | status | quit\n")
    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not raw:
            continue

        if raw.startswith("send "):
            code = raw[5:]
        elif raw.startswith("file "):
            try:
                with open(raw[5:].strip()) as f:
                    code = f.read()
            except FileNotFoundError:
                print("[ERROR] File not found")
                continue
        elif raw == "status":
            print(f"\n[STATUS] {pi_status}")
            continue
        elif raw == "quit":
            break
        else:
            print("Unknown command.")
            continue

        task = {"kind": "task", "task_id": str(uuid.uuid4())[:8], "code": code, "timeout": 10}
        try:
            send_msg(connection, task)
            print(f"[SERVER] Task sent (id={task['task_id']})")
        except OSError:
            print("[ERROR] Not connected.")

    print("[SERVER] Shutting down.")
    conn.close()
    server_sock.close()

if __name__ == "__main__":
    main()