# -*- coding: utf-8 -*-
"""JSON persistence for inspection projects.

The controller is responsible for serialising/deserialising the project state;
this module only owns the filesystem I/O so the UI stays free of file details.
"""

import json


def save_project(filepath, state):
    """Write a serialised project state to *filepath* as UTF-8 JSON."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_project(filepath):
    """Read and parse a project JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)
