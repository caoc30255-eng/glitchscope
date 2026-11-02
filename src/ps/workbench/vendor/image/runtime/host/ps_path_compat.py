"""Resolved path containment using APIs available on Python 3.8."""
from pathlib import Path


def path_within(path, directory):
    try:
        Path(path).resolve().relative_to(Path(directory).resolve())
        return True
    except ValueError:
        return False
