import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import cloudinary
import cloudinary.uploader
import fitz  # PyMuPDF

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_configured = False


def _ensure_configured() -> None:
    global _configured
    if _configured:
        return
    settings = get_settings()
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )
    _configured = True


class StorageService:
    """Cloudinary-backed image storage service."""

    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"}
    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

    def __init__(self) -> None:
        _ensure_configured()

    # ── Upload ────────────────────────────────────────────────

    async def upload_template_image(
        self,
        file_bytes: bytes,
        filename: str,
        teacher_id: str,
        template_id: str,
        subfolder: str = "template",
    ) -> str:
        """Upload a template image (or PDF) to Cloudinary and return the URL(s).

        For single images: returns a single URL string.
        For PDFs: converts each page to a PNG image, uploads each separately,
        and returns a JSON array string of URLs, e.g. '["url1","url2","url3"]'.
        """
        self._validate_file(file_bytes, filename)

        is_pdf = Path(filename).suffix.lower() == ".pdf"
        folder = f"exam-grader/templates/{teacher_id}/{template_id}/{subfolder}"
        stem = Path(filename).stem

        logger.info("Uploading template file to Cloudinary: %s (pdf=%s)", f"{folder}/{stem}", is_pdf)

        if is_pdf:
            return await self._upload_pdf_as_pages(file_bytes, folder, stem)
        else:
            public_id = f"{folder}/{stem}"
            result = cloudinary.uploader.upload(file_bytes, **{
                "public_id": public_id,
                "resource_type": "image",
                "overwrite": True,
                "invalidate": True,
            })
            url: str = result["secure_url"]
            logger.info("Upload complete: %s", url)
            return url

    async def _upload_pdf_as_pages(
        self, pdf_bytes: bytes, folder: str, stem: str,
    ) -> str:
        """Convert PDF pages to images and upload each as a Cloudinary image.

        Returns a JSON array string of URLs: '["url1","url2","url3"]'
        """
        import json as _json

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = len(doc)
        logger.info("PDF has %d page(s) — converting and uploading each", page_count)

        urls: list[str] = []
        for i, page in enumerate(doc):
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            # Save to temp PNG (close handle first for Windows)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_page{i+1}.png")
            tmp_name = tmp.name
            tmp.close()
            pix.save(tmp_name)

            public_id = f"{folder}/{stem}_page{i+1}"
            try:
                img_bytes = Path(tmp_name).read_bytes()
                result = cloudinary.uploader.upload(img_bytes, **{
                    "public_id": public_id,
                    "resource_type": "image",
                    "overwrite": True,
                    "invalidate": True,
                })
                url = result["secure_url"]
                urls.append(url)
                logger.info(
                    "  Page %d/%d uploaded: %s (%d×%d)",
                    i + 1, page_count, url[:80], pix.width, pix.height,
                )
            finally:
                os.unlink(tmp_name)

        doc.close()
        logger.info("PDF upload complete: %d page images", len(urls))

        # Return as JSON array string so the DB field can hold multiple URLs
        return _json.dumps(urls)

    # ── Download (for Vision processing) ─────────────────────

    async def download_to_temp(self, image_url: str) -> str:
        """Download an image from URL to a temporary file. Returns the temp path."""
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(image_url)
            resp.raise_for_status()

        suffix = Path(image_url).suffix or ".jpg"
        # Strip query params from suffix (e.g. ".pdf?v=123" -> ".pdf")
        if "?" in suffix:
            suffix = suffix.split("?")[0]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(resp.content)
        tmp.close()

        logger.debug("Downloaded to temp: %s (%d bytes)", tmp.name, len(resp.content))
        return tmp.name

    async def download_pdf_as_images(self, pdf_url: str) -> list[str]:
        """Download a PDF and convert each page to a temp PNG image.

        Returns a list of temp file paths (one per page). Caller must delete them.
        """
        import httpx

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(pdf_url)
            resp.raise_for_status()

        pdf_bytes = resp.content
        logger.info("Downloaded PDF: %d bytes from %s", len(pdf_bytes), pdf_url[:80])

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = len(doc)
        logger.info("PDF → %d page(s) to convert", page_count)

        temp_paths: list[str] = []
        for i, page in enumerate(doc):
            # Render at 2x resolution for better OCR/Vision quality
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            # Close temp file BEFORE pix.save() — Windows locks the handle
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_page{i+1}.png")
            tmp_name = tmp.name
            tmp.close()
            pix.save(tmp_name)
            file_size = os.path.getsize(tmp_name)
            logger.info(
                "  Page %d/%d → %s (%d×%d, %.1f KB)",
                i + 1, page_count, tmp_name,
                pix.width, pix.height, file_size / 1024,
            )
            temp_paths.append(tmp_name)

        doc.close()
        logger.info("PDF conversion complete: %d images", len(temp_paths))
        return temp_paths

    # ── Validation ────────────────────────────────────────────

    def _validate_file(self, file_bytes: bytes, filename: str) -> None:
        ext = Path(filename).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{ext}'. "
                f"Allowed: {', '.join(sorted(self.ALLOWED_EXTENSIONS))}"
            )
        if len(file_bytes) > self.MAX_FILE_SIZE:
            raise ValueError(
                f"File too large ({len(file_bytes) / 1024 / 1024:.1f} MB). "
                f"Max {self.MAX_FILE_SIZE / 1024 / 1024:.0f} MB."
            )
        if len(file_bytes) == 0:
            raise ValueError("File is empty")

    # ── Student exam uploads ──────────────────────────────────

    async def upload_student_exam_image(
        self,
        file_bytes: bytes,
        filename: str,
        teacher_id: str,
        session_id: str,
    ) -> str:
        """Upload a student exam image/PDF to Cloudinary."""
        self._validate_file(file_bytes, filename)

        is_pdf = Path(filename).suffix.lower() == ".pdf"
        folder = f"exam-grader/sessions/{teacher_id}/{session_id}"
        public_id = f"{folder}/{Path(filename).stem}"

        upload_kwargs: dict = {
            "public_id": public_id,
            "resource_type": "image",
            "overwrite": False,
            "invalidate": True,
        }
        if is_pdf:
            upload_kwargs["format"] = "jpg"
            upload_kwargs["page"] = 1

        result = cloudinary.uploader.upload(file_bytes, **upload_kwargs)
        return result["secure_url"]


# ── Module-level singleton ───────────────────────────────────

_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
