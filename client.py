#!/usr/bin/env python3
"""
IoT Client — connects to server, executes tasks, reports status.
Can run on local PC (Linux \ WSL) as well as remote Raspberry Pi.
Usage: python3 client.py
"""

import socket, ssl, threading, time, subprocess, tempfile, os, sys
from collections import deque
import psutil

from protocol import send_msg, recv_msg
from config import *

current_state = "ready"
task_queue    = deque()

# ── State ─────────────────────────────────────────────────────────────────────

def set_state(new_state: str):
    global current_state
    print(f"  [STATE] {current_state} → {new_state}")
    current_state = new_state

# ── Code execution ────────────────────────────────────────────────────────────

def execute(code: str, timeout: int) -> dict:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                    delete=False, dir=tempfile.gettempdir()) as f:
        f.write(code)
        tmp = f.name
    try:
        if USE_DOCKER_SANDBOX:
            cmd = [
                "docker", "run", "--rm",
                "--network", "none", "--memory", "128m", "--cpus", "0.5",
                "--read-only", "--tmpfs", "/tmp",
                "-v", f"{tmp}:/code.py:ro",
                "code-sandbox", "python3", "/code.py"
            ]
        else:
            cmd = [sys.executable, tmp]   # Plain subprocess for dev

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "stdout":    result.stdout,
            "stderr":    result.stderr,
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Timeout", "exit_code": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1}
    finally:
        os.unlink(tmp)

# ── Task worker thread ────────────────────────────────────────────────────────

def task_worker(sock):
    while True:
        if task_queue:
            task = task_queue.popleft()
            print(f"\n[TASK] Running task_id={task['task_id']}")
            set_state("working")

            result = execute(task["code"], task.get("timeout", 10))

            set_state("done")
            send_msg(sock, {
                "kind":      "result",
                "task_id":   task["task_id"],
                **result
            })
            print(f"[TASK] Done — exit_code={result['exit_code']}")
            time.sleep(0.2)
            set_state("ready")
        else:
            time.sleep(0.1)

# ── Heartbeat thread ──────────────────────────────────────────────────────────

def heartbeat_loop(sock):
    while True:
        try:
            send_msg(sock, {
                "kind":      "status",
                "device_id": DEVICE_ID,
                "state":     current_state,
                "cpu":       psutil.cpu_percent(),
                "mem":       psutil.virtual_memory().percent,
                "timestamp": time.time()
            })
        except OSError:
            break   # Socket closed — exit thread, main loop handles reconnect
        time.sleep(HEARTBEAT_INTERVAL)

# ── Receive loop thread ───────────────────────────────────────────────────────

def receive_loop(sock):
    while True:
        try:
            msg = recv_msg(sock)
            if msg is None:
                print("\n[CLIENT] Server disconnected.")
                break

            if msg.get("kind") == "task":
                print(f"\n[CLIENT] Task received: id={msg.get('task_id')}")
                task_queue.append(msg)

        except (ConnectionResetError, BrokenPipeError, OSError):
            print("\n[CLIENT] Connection lost.")
            break

# ── TLS / plain socket setup ──────────────────────────────────────────────────

def make_client_socket() -> socket.socket:
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if USE_TLS:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(CA_CERT)                  # Verify server cert
        ctx.load_cert_chain(CLIENT_CERT, CLIENT_KEY)        # Present our cert
        ctx.check_hostname = True
        return ctx.wrap_socket(raw, server_hostname=HOST)

    return raw

# ── Main loop with reconnect ──────────────────────────────────────────────────

def main():
    print(f"=== IoT Client — device: {DEVICE_ID} ===")
    print(f"    Mode: {'TLS' if USE_TLS else 'plain TCP (dev)'} | "
          f"Sandbox: {'Docker' if USE_DOCKER_SANDBOX else 'subprocess'}\n")

    retry_delay = 2   # Exponential backoff starting point

    while True:       # Outer loop — reconnects forever
        try:
            print(f"[CLIENT] Connecting to {HOST}:{PORT}...")
            sock = make_client_socket()
            sock.connect((HOST, PORT))
            print(f"[CLIENT] Connected!\n")
            retry_delay = 2   # Reset backoff on successful connect

            # Start background threads — they all share the same socket
            threads = [
                threading.Thread(target=heartbeat_loop, args=(sock,), daemon=True),
                threading.Thread(target=task_worker,    args=(sock,), daemon=True),
                threading.Thread(target=receive_loop,   args=(sock,), daemon=True),
            ]
            for t in threads:
                t.start()

            # Block until receive_loop exits (i.e. connection dropped)
            threads[2].join()
            sock.close()

        except (ConnectionRefusedError, OSError) as e:
            print(f"[CLIENT] Could not connect: {e}")

        print(f"[CLIENT] Reconnecting in {retry_delay}s...")
        time.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 60)   # Cap backoff at 60s

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[CLIENT] Exiting.")