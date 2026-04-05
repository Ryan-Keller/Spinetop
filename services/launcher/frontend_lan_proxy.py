#!/usr/bin/env python3
from __future__ import annotations

import argparse
import signal
import socket
import sys
import threading


def relay(source: socket.socket, target: socket.socket, stop_event: threading.Event) -> None:
    try:
        while not stop_event.is_set():
            chunk = source.recv(65536)
            if not chunk:
                break
            target.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            target.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def handle_client(client: socket.socket, target_host: str, target_port: int, stop_event: threading.Event) -> None:
    upstream: socket.socket | None = None
    try:
        upstream = socket.create_connection((target_host, target_port), timeout=5)
    except OSError as exc:
        print(f"proxy connect failed: {exc}", file=sys.stderr, flush=True)
        try:
            client.close()
        except OSError:
            pass
        return

    client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    upstream.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    forward_to_upstream = threading.Thread(target=relay, args=(client, upstream, stop_event), daemon=True)
    forward_to_client = threading.Thread(target=relay, args=(upstream, client, stop_event), daemon=True)
    forward_to_upstream.start()
    forward_to_client.start()
    forward_to_upstream.join()
    forward_to_client.join()

    for sock in (client, upstream):
        try:
            sock.close()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="LAN TCP proxy for the Spinetop frontend dev server")
    parser.add_argument("--listen-address", required=True)
    parser.add_argument("--listen-port", required=True, type=int)
    parser.add_argument("--target-address", required=True)
    parser.add_argument("--target-port", required=True, type=int)
    args = parser.parse_args()

    stop_event = threading.Event()

    def request_stop(signum: int, frame) -> None:  # noqa: ARG001
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((args.listen_address, args.listen_port))
    listener.listen(64)
    listener.settimeout(1.0)

    print(
        f"frontend LAN proxy listening on {args.listen_address}:{args.listen_port} "
        f"-> {args.target_address}:{args.target_port}",
        flush=True,
    )

    try:
        while not stop_event.is_set():
            try:
                client, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if stop_event.is_set():
                    break
                raise
            threading.Thread(
                target=handle_client,
                args=(client, args.target_address, args.target_port, stop_event),
                daemon=True,
            ).start()
    finally:
        try:
            listener.close()
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
