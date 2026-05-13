"""Launch Hermes CLI with the urban toolset registered first."""

from __future__ import annotations

import argparse
import os
import re
import sys

from .bootstrap import bootstrap
from .paths import ensure_paths


HERMES_COMMANDS = {
    "auth",
    "config",
    "doctor",
    "fallback",
    "login",
    "logout",
    "model",
    "setup",
    "status",
}


def _run_hermes_command(argv: list[str]) -> None:
    ensure_paths()
    old_argv = sys.argv[:]
    old_disable_lazy = os.environ.get("HERMES_DISABLE_LAZY_INSTALLS")
    try:
        if argv and argv[0] == "setup":
            # Hermes setup performs availability probes for optional backends.
            # Those probes can trigger lazy pip installs, which is undesirable
            # during configuration and can stall or crash the setup flow.
            os.environ["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
        sys.argv = ["hermes", *argv]
        from hermes_cli.main import main as hermes_command_main

        hermes_command_main()
    finally:
        if old_disable_lazy is None:
            os.environ.pop("HERMES_DISABLE_LAZY_INSTALLS", None)
        else:
            os.environ["HERMES_DISABLE_LAZY_INSTALLS"] = old_disable_lazy
        sys.argv = old_argv


def _patch_plain_output_if_needed(*, force: bool = False) -> None:
    """Avoid prompt_toolkit rendering when Hermes-Urban is driven by pipes.

    Hermes' upstream CLI routes many status lines through prompt_toolkit even in
    some one-shot/resume paths. That is pleasant in a real terminal, but crashes
    under PowerShell piping/automation with NoConsoleScreenBufferError. The
    adapter's experiment mode should remain CLI-native while still being
    non-TTY-safe, so we replace Hermes' colored print helper with a plain writer
    only when stdout is not interactive or the caller explicitly requests it.
    """
    if not force and sys.stdout.isatty() and not os.getenv("URBAN_HERMES_PLAIN"):
        return
    try:
        import cli as hermes_cli_module
    except Exception:
        return

    ansi_re = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

    def plain_print(text: str = "") -> None:
        rendered = ansi_re.sub("", str(text))
        try:
            sys.stdout.write(rendered + ("\n" if not rendered.endswith("\n") else ""))
            sys.stdout.flush()
        except UnicodeEncodeError:
            sys.stdout.buffer.write((rendered + "\n").encode("utf-8", errors="replace"))
            sys.stdout.flush()

    hermes_cli_module._cprint = plain_print  # type: ignore[attr-defined]


def main(argv: list[str] | None = None) -> None:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args and raw_args[0] in HERMES_COMMANDS:
        _run_hermes_command(raw_args)
        return

    parser = argparse.ArgumentParser(description="Launch Hermes with Hermes-Urban tools registered.")
    parser.add_argument("query", nargs="?", help="Optional one-shot query. If omitted, Hermes starts interactively.")
    parser.add_argument("--toolsets", default="urban,todo,memory,file,terminal", help="Comma-separated Hermes toolsets.")
    parser.add_argument("--provider", default=None, help="Hermes provider override.")
    parser.add_argument("--model", default=None, help="Hermes model override.")
    parser.add_argument("--max-turns", type=int, default=None, help="Maximum tool-calling turns for one-shot mode.")
    parser.add_argument("--skills", default=None, help="Comma-separated Hermes skills to preload.")
    parser.add_argument("--list-tools", action="store_true", help="List available tools and exit.")
    parser.add_argument("--list-toolsets", action="store_true", help="List available toolsets and exit.")
    parser.add_argument("--quiet", action="store_true", help="Pass quiet mode through to Hermes CLI.")
    parser.add_argument("--compact", action="store_true", help="Pass compact display mode through to Hermes CLI.")
    parser.add_argument("--resume", default=None, help="Resume a previous Hermes session id.")
    parser.add_argument("--ignore-user-config", action="store_true", help="Pass through to Hermes CLI.")
    parser.add_argument("--plain", action="store_true", help="Force plain non-prompt_toolkit output for scripted runs.")
    parser.add_argument("--yolo", action="store_true", help="Bypass Hermes dangerous-command approval prompts for this process.")
    args = parser.parse_args(argv)

    ensure_paths()
    bootstrap()

    if args.yolo:
        os.environ["HERMES_YOLO_MODE"] = "1"

    _patch_plain_output_if_needed(force=args.plain)

    from cli import main as hermes_main

    hermes_main(
        query=args.query,
        toolsets=args.toolsets,
        provider=args.provider,
        model=args.model,
        max_turns=args.max_turns,
        skills=args.skills,
        list_tools=args.list_tools,
        list_toolsets=args.list_toolsets,
        quiet=args.quiet,
        compact=args.compact,
        resume=args.resume,
        ignore_user_config=args.ignore_user_config,
    )


if __name__ == "__main__":
    main()
