"""Local source-path handling shared by ingestion modules."""

from os import PathLike, fspath
from pathlib import Path
import re
from urllib.parse import urlsplit

import pandas as pd


def local_path(reference: object) -> Path | None:
    """Return a local path, None for absent references, or raise ValueError.

    Relative paths are relative to the current working directory. Windows
    drive-absolute paths are accepted, but drive-relative paths, URI schemes
    and network-share syntax are rejected; no URL is ever opened or fetched.
    """
    if reference is None:
        return None
    if not isinstance(reference, (str, PathLike)):
        if pd.api.types.is_scalar(reference) and pd.isna(reference):
            return None
        raise ValueError("Expected a local filesystem path")
    text = fspath(reference)
    if not isinstance(text, str):
        raise ValueError("Expected a text filesystem path")
    if not text.strip():
        return None
    # URL parsing treats a Windows drive letter as a scheme. Exempt only the
    # explicit drive-absolute form, not ambiguous paths such as C:invoice.png.
    drive_absolute = re.match(r"^[A-Za-z]:[\\/]", text) is not None
    if (text.startswith(("//", "\\\\")) or "\x00" in text
            or (not drive_absolute and urlsplit(text).scheme)):
        raise ValueError("Only local filesystem paths are supported; URLs are not loaded")
    return Path(text)
