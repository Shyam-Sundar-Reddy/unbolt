"""JSON file persistence for Overrides (decision 0007) - the mechanism
that lets `unbolt override` and a later `unbolt generate` (separate
processes) see the same decisions, and the one place CLI and MCP share
state when pointed at the same file.
"""

import json
from dataclasses import asdict
from pathlib import Path

from unbolt.overrides.overrides import Override, Overrides

DEFAULT_OVERRIDES_PATH = ".unbolt-overrides.json"


def load_overrides(path: str | Path = DEFAULT_OVERRIDES_PATH) -> Overrides:
    """Returns an empty Overrides if the file doesn't exist - no
    override is the common case, not an error.
    """
    file_path = Path(path)
    if not file_path.exists():
        return Overrides()
    data = json.loads(file_path.read_text())
    return Overrides(entries=tuple(Override(**entry) for entry in data["entries"]))


def save_overrides(overrides: Overrides, path: str | Path = DEFAULT_OVERRIDES_PATH) -> None:
    data = {"entries": [asdict(entry) for entry in overrides.entries]}
    Path(path).write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
