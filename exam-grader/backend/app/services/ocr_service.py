import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

# PaddleOCR requires paddlepaddle which may not have wheels for all Python
# versions (e.g. 3.14). Import is deferred to first use so the module loads
# cleanly and the rest of the app keeps working.
_PaddleOCR = None


def _import_paddleocr():
    global _PaddleOCR
    if _PaddleOCR is not None:
        return _PaddleOCR
    try:
        from paddleocr import PaddleOCR  # noqa: WPS433
        _PaddleOCR = PaddleOCR
        return _PaddleOCR
    except ImportError as exc:
        raise ImportError(
            "PaddleOCR requires 'paddlepaddle'. Install it with: "
            "pip install paddlepaddle paddleocr"
        ) from exc


class OCRService:
    """PaddleOCR-based text extraction service for exam images."""

    def __init__(self, lang: str = "en") -> None:
        self._lang = lang
        self._ocr: Any = None

    def _get_ocr(self) -> Any:
        if self._ocr is None:
            logger.info("Initializing PaddleOCR engine (lang=%s)…", self._lang)
            PaddleOCR = _import_paddleocr()
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang=self._lang,
                show_log=False,
            )
        return self._ocr

    # ── Image pre-processing ─────────────────────────────────

    def _preprocess_image(self, image_path: str) -> np.ndarray:
        """Load, auto-rotate, enhance contrast, and convert to numpy array."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        try:
            img = Image.open(path)
        except Exception as exc:
            raise ValueError(f"Cannot read image {image_path}: {exc}") from exc

        # Apply EXIF rotation
        img = self._apply_exif_rotation(img)

        # Convert to RGB if needed
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Enhance contrast
        img = ImageEnhance.Contrast(img).enhance(1.5)

        # Sharpen slightly for better OCR
        img = img.filter(ImageFilter.SHARPEN)

        return np.array(img)

    @staticmethod
    def _apply_exif_rotation(img: Image.Image) -> Image.Image:
        """Rotate image based on EXIF orientation tag."""
        try:
            exif = img.getexif()
            orientation = exif.get(274)  # 274 = Orientation tag
            rotations = {3: 180, 6: 270, 8: 90}
            if orientation in rotations:
                img = img.rotate(rotations[orientation], expand=True)
        except Exception:
            pass  # No EXIF data — skip
        return img

    # ── Core OCR ─────────────────────────────────────────────

    async def extract_text(self, image_path: str) -> str:
        """Extract all text from an exam image.

        Returns concatenated text lines separated by newlines.
        """
        logger.debug("OCR extract_text: %s", image_path)

        img_array = self._preprocess_image(image_path)
        ocr = self._get_ocr()

        # PaddleOCR is CPU-bound — run in a thread to avoid blocking
        result = await asyncio.to_thread(ocr.ocr, img_array, cls=True)

        if not result or not result[0]:
            logger.warning("OCR returned no results for %s", image_path)
            return ""

        lines: list[str] = []
        for line_info in result[0]:
            # line_info = [bbox, (text, confidence)]
            text: str = line_info[1][0]
            confidence: float = line_info[1][1]
            if confidence >= 0.5:
                lines.append(text)
            else:
                logger.debug("Low-confidence OCR line skipped (%.2f): %s", confidence, text)

        full_text = "\n".join(lines)
        logger.info(
            "OCR extracted %d lines (%d chars) from %s",
            len(lines),
            len(full_text),
            image_path,
        )
        return full_text

    # ── Name detection ───────────────────────────────────────

    _NAME_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"(?:name|nombre|student|alumno)\s*[:\-]?\s*(.+)", re.IGNORECASE),
        re.compile(r"(?:full\s*name|nombre\s*completo)\s*[:\-]?\s*(.+)", re.IGNORECASE),
    ]

    async def detect_name(self, text: str) -> Optional[str]:
        """Try to detect a student name from OCR text.

        Searches for common label patterns like "Name:", "Nombre:", etc.
        Returns None if no name is found.
        """
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            for pattern in self._NAME_PATTERNS:
                match = pattern.search(stripped)
                if match:
                    name = match.group(1).strip().strip("_").strip()
                    if len(name) >= 2:
                        logger.info("Detected student name: %s", name)
                        return name

        logger.warning("No student name detected in OCR text")
        return None


# ── Module-level singleton ───────────────────────────────────

_ocr_service: Optional[OCRService] = None


def get_ocr_service(lang: str = "en") -> OCRService:
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService(lang=lang)
    return _ocr_service