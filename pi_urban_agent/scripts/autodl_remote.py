"""Credential-safe AutoDL SSH/SFTP helper.

The workspace .env stores the SSH command on line 49 and its password on line
50.  This helper parses them in memory and never prints either value.
"""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from pathlib import Path

import paramiko


def connection_details(env_path: Path) -> tuple[str, int, str, str]:
    lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    command_index = next(
        (index for index, line in enumerate(lines) if line.strip().startswith("ssh ")),
        None,
    )
    if command_index is None or command_index + 1 >= len(lines):
        raise RuntimeError("Expected an SSH command followed by its password in .env")
    command = lines[command_index].strip()
    password = lines[command_index + 1].strip()
    tokens = shlex.split(command, posix=True)
    port = 22
    target = ""
    for index, token in enumerate(tokens):
        if token == "-p" and index + 1 < len(tokens):
            port = int(tokens[index + 1])
        elif "@" in token and not token.startswith("-"):
            target = token
    if not target:
        match = re.search(r"([^\s@]+)@([^\s]+)", command)
        if not match:
            raise RuntimeError("Could not parse SSH user and host")
        user, host = match.group(1), match.group(2)
    else:
        user, host = target.rsplit("@", 1)
    return host, port, user, password


def connect(env_path: Path) -> paramiko.SSHClient:
    host, port, user, password = connection_details(env_path)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=user,
        password=password,
        timeout=30,
        banner_timeout=30,
        auth_timeout=30,
    )
    return client


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True, type=Path)
    sub = parser.add_subparsers(dest="action", required=True)
    exec_parser = sub.add_parser("exec")
    exec_parser.add_argument("--command", required=True)
    exec_parser.add_argument("--timeout", type=int, default=3600)
    put_parser = sub.add_parser("put")
    put_parser.add_argument("--local", required=True, type=Path)
    put_parser.add_argument("--remote", required=True)
    get_parser = sub.add_parser("get")
    get_parser.add_argument("--remote", required=True)
    get_parser.add_argument("--local", required=True, type=Path)
    args = parser.parse_args()

    client = connect(args.env)
    try:
        if args.action == "exec":
            _, stdout, stderr = client.exec_command(args.command, timeout=args.timeout)
            for line in iter(stdout.readline, ""):
                print(line, end="")
            error_text = stderr.read().decode("utf-8", errors="replace")
            if error_text:
                print(error_text, end="")
            return stdout.channel.recv_exit_status()
        with client.open_sftp() as sftp:
            if args.action == "put":
                sftp.put(str(args.local), args.remote)
            else:
                args.local.parent.mkdir(parents=True, exist_ok=True)
                sftp.get(args.remote, str(args.local))
        print(f"{args.action}:ok")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
