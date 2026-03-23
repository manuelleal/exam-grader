import logging
import tempfile
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class PDFService:
    """Service for converting PDF files to images using PyMuPDF."""

    def __init__(self, dpi: int = 200) -> None:
        self._dpi = dpi
        self._zoom = dpi / 72  # PDF default is 72 DPI
        logger.info("PDFService initialized (dpi=%d, zoom=%.2f)", dpi, self._zoom)

    async def convert_pdf_to_images(self, pdf_path: str) -> list[str]:
        """Convert a multi-page PDF to a list of JPEG file paths.

        Uses PyMuPDF (fitz) — pure Python, no external dependencies needed.

        Returns: list of temporary JPEG file paths (one per page).
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        logger.info("╔═══ PDF CONVERSION START ═══╗")
        logger.info("║ File: %s", pdf_path)
        logger.info("║ Size: %d bytes", path.stat().st_size)

        image_paths: list[str] = []

        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            logger.info("║ Pages detected: %d", total_pages)

            mat = fitz.Matrix(self._zoom, self._zoom)

            for page_num in range(total_pages):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(matrix=mat)

                tmp = tempfile.NamedTemporaryFile(
                    delete=False, suffix=f"_page{page_num + 1}.jpg", prefix="pdf_"
                )
                tmp.close()

                # Save as JPEG
                pix.save(tmp.name)
                image_paths.append(tmp.name)

                logger.info(
                    "║ Page %d/%d → %s (%dx%d px, %d bytes)",
                    page_num + 1, total_pages, tmp.name,
                    pix.width, pix.height, Path(tmp.name).stat().st_size,
                )

            doc.close()

        except Exception as exc:
            logger.error("║ ✗ PDF conversion failed: %s", exc)
            # Clean up any partial files
            for p in image_paths:
                try:
                    Path(p).unlink(missing_ok=True)
                except OSError:
                    pass
            raise ValueError(f"Cannot convert PDF '{path.name}': {exc}") from exc

        if not image_paths:
            raise ValueError(f"No pages extracted from PDF: {pdf_path}")

        logger.info("╚═══ PDF CONVERSION DONE: %d image(s) ═══╝", len(image_paths))
        return image_paths


# ── Module-level singleton ───────────────────────────────────

_pdf_service: Optional[PDFService] = None


def get_pdf_service() -> PDFService:
    global _pdf_service
    if _pdf_service is None:
        _pdf_service = PDFService()
    return _pdf_service
