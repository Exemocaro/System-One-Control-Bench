"""Finding API keys, without ever putting one in the repository.

A real environment variable always wins over the file, so CI and a local `.env`
can disagree without surprise. Keys are read at the moment they are needed and
never stored on a record, a manifest or a log line.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DOTENV = Path(".env")


class CredentialError(RuntimeError):
    """Raised when a required API key cannot be found."""


def read_dotenv(path: Path | str = DEFAULT_DOTENV) -> dict[str, str]:
    """Parse a `.env` file. An absent file is simply empty."""
    target = Path(path)
    if not target.exists():
        return {}

    parsed: dict[str, str] = {}
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        name = name.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        parsed[name] = value
    return parsed


def load_api_key(*names: str, dotenv_path: Path | str = DEFAULT_DOTENV) -> str:
    """First of `names` set in the environment or the `.env` file."""
    if not names:
        raise ValueError("load_api_key needs at least one variable name")

    for name in names:
        value = os.environ.get(name)
        if value:
            return value

    from_file = read_dotenv(dotenv_path)
    for name in names:
        value = from_file.get(name)
        if value:
            return value

    tried = ", ".join(names)
    raise CredentialError(
        f"no API key found. Set one of {tried} in the environment or in {Path(dotenv_path)}."
    )
