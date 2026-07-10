#!/usr/bin/env python3
"""Manage credentials for the Starlark HTTP action.

Subcommands:

  genkey
      Generate a new Fernet key and print it. Capture it into the fixed env var:
          export STARLARK_FERNET_KEY=$(./seal.py genkey)

  seal <SECRET_ENV_VAR>
      Seal a secret into a Fernet token. Both inputs come from the environment,
      never argv, so the values don't leak into shell history or `ps`:
        - the key is read from the fixed variable $STARLARK_FERNET_KEY;
        - the secret value is read from the variable whose NAME you pass.
      Prints the token to seal — paste it as a credential's "value" in the
      module's `credentials` config.

          export STARLARK_FERNET_KEY='...'
          export VENDOR_API_TOKEN='sk-...'
          ./seal.py seal VENDOR_API_TOKEN

Needs the `cryptography` package; run with a Python that has it (e.g. the module's
venv, from this directory: `.venv/bin/python seal.py ...`).
"""
import os
import sys

from cryptography.fernet import Fernet

KEY_ENV = "STARLARK_FERNET_KEY"


def genkey(argv: list[str]) -> int:
    if argv:
        print(__doc__, file=sys.stderr)
        return 2
    print(Fernet.generate_key().decode())
    return 0


def seal(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2

    key = os.environ.get(KEY_ENV)
    if not key:
        print(f"error: ${KEY_ENV} is not set", file=sys.stderr)
        return 2

    secret_env = argv[0]
    if secret_env not in os.environ:
        print(f"error: ${secret_env} is not set", file=sys.stderr)
        return 2

    try:
        token = Fernet(key.encode()).encrypt(os.environ[secret_env].encode()).decode()
    except Exception as error:
        print(f"error: could not seal (bad key?): {type(error).__name__}", file=sys.stderr)
        return 1

    print(token)
    return 0


COMMANDS = {"genkey": genkey, "seal": seal}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        print(__doc__, file=sys.stderr)
        return 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
