"""nxstate — Python reference implementation of the agent-CLI contract.

cli-scaffold copies this tree and substitutes the tokens documented in
references/templates/python/TEMPLATE.md. The contract surface (output, errors, safety
gate, schema, agent) is correct as-is; replace store.py with the real client.
"""

from importlib import metadata


def _version() -> str:
    try:
        return metadata.version("nxstate")
    except metadata.PackageNotFoundError:
        return "dev"


__version__ = _version()
