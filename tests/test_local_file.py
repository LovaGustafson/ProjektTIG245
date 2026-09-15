"""Local path classification without accessing the filesystem."""

from pathlib import Path

import pytest

from src.ingestion._local_file import local_path


@pytest.mark.parametrize("path_type", [str, Path])
@pytest.mark.parametrize("text", [
    r"C:\Users\example\invoice.png",
    "C:/Users/example/invoice.png",
    r"d:\invoices\invoice.pdf",
    "data/input/invoice.png",
    "invoice.csv",
])
def test_local_paths_are_accepted(text, path_type):
    assert local_path(path_type(text)) == Path(text)


@pytest.mark.parametrize("text", [
    "http://example.invalid/invoice.png",
    "https://example.invalid/invoice.png",
    "file:///tmp/invoice.png",
    "file://server/share/invoice.png",
    "file:invoice.png",
    "file:C:/invoices/invoice.png",
    r"\\server\share\invoice.png",
    "//server/share/invoice.png",
    r"\\?\C:\invoices\invoice.png",
    "invoice\x00.png",
    "C:/invoices/invoice\x00.png",
    "C:invoice.png",
    "d:invoices/invoice.png",
    "C:",
])
def test_nonlocal_invalid_or_drive_relative_paths_are_rejected(text):
    with pytest.raises(ValueError, match="Only local filesystem paths"):
        local_path(text)


@pytest.mark.parametrize("text", [r"\\server\share\invoice.png", "C:invoice.png"])
def test_unsupported_path_objects_are_rejected(text):
    with pytest.raises(ValueError, match="Only local filesystem paths"):
        local_path(Path(text))
