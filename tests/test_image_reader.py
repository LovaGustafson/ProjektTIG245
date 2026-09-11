"""Image/document reader tests using synthetic local files only."""

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from PIL import Image
from pypdf import PdfWriter

from src.ingestion.image_reader import read_image
from src.models.ingestion import ReadStatus


@pytest.mark.parametrize("suffix,format", [(".png", "PNG"), (".jpg", "JPEG"),
                                         (".tiff", "TIFF"), (".gif", "GIF"),
                                         (".bmp", "BMP"), (".webp", "WEBP")])
def test_local_image_is_decoded_without_modifying_source(tmp_path, suffix, format):
    path = tmp_path / f"synthetic{suffix}"
    Image.new("RGB", (8, 6), "white").save(path, format=format)
    before, modified = path.read_bytes(), path.stat().st_mtime_ns
    result = read_image(path)
    assert result.status == ReadStatus.LOADED
    assert (result.width, result.height, result.page_count) == (8, 6, 1)
    assert result.content == before
    assert result.ocr_status == "NOT_IMPLEMENTED"
    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == modified


def test_local_pdf(tmp_path):
    path = tmp_path / "synthetic.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as stream:
        writer.write(stream)
    before, modified = path.read_bytes(), path.stat().st_mtime_ns
    result = read_image(str(path))
    assert result.status == ReadStatus.LOADED
    assert result.media_type == "application/pdf"
    assert result.page_count == 1
    assert result.content == before == path.read_bytes()
    assert path.stat().st_mtime_ns == modified


@pytest.mark.parametrize("reference", [None, "", " \t", pd.NA, float("nan")])
def test_missing_reference(reference):
    assert read_image(reference).status == ReadStatus.MISSING_REFERENCE


def test_missing_image_file(tmp_path):
    result = read_image(tmp_path / "missing.png")
    assert result.status == ReadStatus.MISSING_FILE
    assert result.content is None


def test_unsupported_type(tmp_path):
    path = tmp_path / "synthetic.docx"
    path.write_bytes(b"synthetic")
    assert read_image(path).status == ReadStatus.UNSUPPORTED


@pytest.mark.parametrize("reference", ["https://example.invalid/image.png", "file:///tmp/test.png",
                                      "//server/image.png", 123, []])
def test_nonlocal_or_invalid_reference_never_opens_a_file(reference):
    with patch.object(Path, "read_bytes", side_effect=AssertionError("Must not open")):
        assert read_image(reference).status == ReadStatus.UNSUPPORTED


@pytest.mark.parametrize("suffix,content", [(".png", b""), (".jpg", b"invalid"),
                                          (".pdf", b"%PDF-1.7\ninvalid")])
def test_malformed_file(tmp_path, suffix, content):
    path = tmp_path / f"broken{suffix}"
    path.write_bytes(content)
    result = read_image(path)
    assert result.status == ReadStatus.UNREADABLE
    assert result.content is None
    assert path.read_bytes() == content


def test_permission_error(tmp_path):
    with patch.object(Path, "read_bytes", side_effect=PermissionError("synthetic denial")):
        result = read_image(tmp_path / "synthetic.png")
    assert result.status == ReadStatus.UNREADABLE
    assert "denial" in result.reason


def test_directory_is_unreadable(tmp_path):
    directory = tmp_path / "directory.png"
    directory.mkdir()
    assert read_image(directory).status == ReadStatus.UNREADABLE


def test_mismatched_extension(tmp_path):
    path = tmp_path / "synthetic.jpg"
    Image.new("RGB", (4, 4)).save(path, format="PNG")
    assert read_image(path).status == ReadStatus.UNREADABLE


def test_encrypted_pdf_returns_clear_error(tmp_path):
    path = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt("synthetic-password")
    with path.open("wb") as stream:
        writer.write(stream)
    result = read_image(path)
    assert result.status == ReadStatus.UNREADABLE
    assert "Encrypted" in result.reason
