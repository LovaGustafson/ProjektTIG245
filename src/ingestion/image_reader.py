"""Read local invoice images/documents into memory without OCR or source edits."""

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import warnings

from PIL import Image
from pypdf import PdfReader

from src.ingestion._local_file import local_path
from src.models.ingestion import ReadStatus


IMAGE_FORMATS = {
    ".png": ("PNG", "image/png"),
    ".jpg": ("JPEG", "image/jpeg"),
    ".jpeg": ("JPEG", "image/jpeg"),
    ".tif": ("TIFF", "image/tiff"),
    ".tiff": ("TIFF", "image/tiff"),
    ".gif": ("GIF", "image/gif"),
    ".bmp": ("BMP", "image/bmp"),
    ".webp": ("WEBP", "image/webp"),
}


@dataclass(frozen=True)
class ImageReadResult:
    path: Path | None
    status: ReadStatus
    reason: str
    content: bytes | None = field(default=None, repr=False)
    media_type: str | None = None
    width: int | None = None
    height: int | None = None
    page_count: int | None = None
    ocr_status: str = "NOT_IMPLEMENTED"


def read_image(image_reference: object) -> ImageReadResult:
    """Load supported local raster images or PDFs and inspect basic metadata.

    All parsing operates on in-memory bytes. Raster frames are decoded to check
    readability; PDFs are parsed but not rendered. PDF embedded images are not
    decoded. LOADED is a technical result, not an invoice correctness judgment.
    No text extraction, OCR, URL fetching, or document-link traversal occurs.
    TODO: AK must confirm Bild linkage/meaning and relevant document content.
    """
    try:
        path = local_path(image_reference)
    except (TypeError, ValueError) as exc:
        return ImageReadResult(None, ReadStatus.UNSUPPORTED, str(exc))
    if path is None:
        return ImageReadResult(None, ReadStatus.MISSING_REFERENCE, "No image_reference supplied")
    suffix = path.suffix.lower()
    if suffix not in IMAGE_FORMATS and suffix != ".pdf":
        return ImageReadResult(path, ReadStatus.UNSUPPORTED, f"Unsupported image/document type: {suffix}")
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return ImageReadResult(path, ReadStatus.MISSING_FILE, f"Image/document file not found: {path}")
    except (OSError, ValueError) as exc:
        return ImageReadResult(path, ReadStatus.UNREADABLE, f"Cannot read image/document: {exc}")

    try:
        if suffix == ".pdf":
            with BytesIO(content) as stream:
                document = PdfReader(stream, strict=True)
                if document.is_encrypted:
                    raise ValueError("Encrypted PDFs are not supported by this reader")
                page_count = len(document.pages)
                for page in document.pages:
                    contents = page.get_contents()
                    if contents is not None:
                        contents.get_data()
            return ImageReadResult(path, ReadStatus.LOADED, "Local PDF parsed; OCR not performed",
                                   content, "application/pdf", page_count=page_count)

        expected_format, media_type = IMAGE_FORMATS[suffix]
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if image.format != expected_format:
                    raise ValueError("Image content does not match its file extension")
                image.verify()
            with Image.open(BytesIO(content)) as image:
                width, height = image.size
                frame_count = getattr(image, "n_frames", 1)
                for index in range(frame_count):
                    image.seek(index)
                    image.load()
        return ImageReadResult(path, ReadStatus.LOADED, "Local image decoded; OCR not performed",
                               content, media_type, width, height, frame_count)
    except Exception as exc:
        # Decoder-specific failures are isolated to this document, not the batch.
        return ImageReadResult(path, ReadStatus.UNREADABLE,
                               f"Cannot decode image/document ({type(exc).__name__}): {exc}")
