"""
IoT Client — connects to server, executes tasks, reports status.
Can run on local PC (Linux \ WSL) as well as remote Raspberry Pi.
Usage: python3 client.py
"""

from enum import Enum
import subprocess, tempfile, os, sys, time, socket, ssl, threading
from collections import deque
import psutil

from protocol import send_msg, recv_msg
from config import *


class Device_Status(Enum):
    READY = "ready"
    WORKING = "working"
    DONE = "done"

currentDevState = Device_Status.READY.value

def set_device_state(state: Device_Status):
    global currentDevState
    print(f"    [DEVICE_STATE] {currentDevState} -> {state.value}")
    currentDevState = state.value

class Task_Status(Enum):
    PENDING = "pending"
    RUNNING = "running"
    CRASHED = "crashed"
    DONE = "done"

currentTaskState = Task_Status.PENDING.value

def set_task_state(state: Task_Status):
    global currentTaskState
    print(f"    [TASK_STATE] {currentTaskState} -> {state.value}")
    currentTaskState = state.value


def execute(code: str, timeout: int) -> dict:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                    delete=False, dir=tempfile.gettempdir()) as f:
        f.write(code)
        tmp = f.name
    try:
        set_task_state(Task_Status.RUNNING)
        result = subprocess.run([sys.executable, tmp], capture_output=True, text=True, timeout=timeout)
        return {
            "stdout": result.stdout, 
            "stderr": result.stderr, 
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Timeout", "exit_code": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1}
    finally:
        os.unlink(tmp)
    
task_queue = deque()

def task_worker(sock):
    while True:
        if task_queue:
            task = task_queue.popleft()
            set_device_state(Device_Status.WORKING)
            set_task_state(Task_Status.RUNNING)
            result = execute(task["code"], task.get("timeout", 10))
            set_task_state(Task_Status.DONE)
            send_msg(sock, {
                "kind": "result",
                "task_id": task["task_id"],
                **result
            })
            time.sleep(0.2)
            set_task_state(Task_Status.PENDING)
            set_device_state(Device_Status.READY)
        else:
            time.sleep(0.1)

def heartbeat_loop(sock):
    """
    Send device status to the server.

    Args:
        sock (socket.socket): Communication socket.
    """
    while True:
        try:
            send_msg(sock, {
                "kind":         "status",
                "device_id":    DEVICE_ID,
                "state":        currentDevState,
                "cpu":          psutil.cpu_percent(),
                "mem":          psutil.virtual_memory().percent,
                "timestamp":    time.time()
            })
        except OSError:
            break
        time.sleep(HEARTBEAT_INTERVAL)
            
def receive_loop(sock):
    """
    Check for messages from the server. Detect disconnect and received tasks. If task is detected then add it into device's task queue.

    Args:
        sock (socket.socket): Communication socket.
    """
    while True:
        try:
            msg = recv_msg(sock)
            if msg is None:
                print("\n[CLIENT] Server disconnected.")
                break

            if msg.get("kind") == "task":
                task_queue.append(msg)
            
        except (ConnectionResetError, BrokenPipeError, OSError):
            print("\n[CLIENT] Connection lost.")
            break

def make_client_socket() -> socket.socket:
    """
    Create client's socket for communication. Use TLS if available.

    Returns:
        socket.socket: Client's communication socket.
    """
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if USE_TLS:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(CA_CERT)
        ctx.load_cert_chain(CLIENT_CERT, CLIENT_KEY)
        ctx.check_hostname = True
        return ctx.wrap_socket(raw, server_hostname=HOST)
    
    return raw


def main():
    retry_delay = 2

    while True:
        try:
            sock = make_client_socket()
            sock.connect((HOST, PORT))
            retry_delay = 2

            threads = [
                threading.Thread(target=heartbeat_loop, args=(sock,), daemon=True),
                threading.Thread(target=task_worker,    args=(sock,), daemon=True),
                threading.Thread(target=receive_loop,   args=(sock,), daemon=True),
            ]

            for t in threads:
                t.start()

            threads[2].join()   # Block until receive_loop exits
            sock.close()
        
        except (ConnectionRefusedError, OSError) as e:
            print(f"[CLIENT] Could not connect: {e}")

        print(f"[CLIENT] Reconnecting in {retry_delay}s...")
        time.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 60)

