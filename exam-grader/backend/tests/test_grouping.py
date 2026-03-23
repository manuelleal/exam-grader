"""
Tests for GroupingService — covers grouping, merging, and validation.

All OCR and Vision calls are mocked so tests run offline and deterministically.
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Ensure minimal env vars so Settings can load ─────────────
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake-key")
os.environ.setdefault("DATABASE_URL", "postgresql://fake")
os.environ.setdefault("ANTHROPIC_API_KEY", "fake-anthropic-key")
os.environ.setdefault("OPENAI_API_KEY", "fake-openai-key")
os.environ.setdefault("JWT_SECRET", "fake-jwt-secret")

from app.services.grouping_service import GroupingService


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def mock_ocr():
    """Return a mocked OCRService."""
    ocr = MagicMock()
    ocr.extract_text = AsyncMock(return_value="")
    ocr.detect_name = AsyncMock(return_value=None)
    return ocr


@pytest.fixture
def mock_vision():
    """Return a mocked VisionService."""
    vision = MagicMock()
    vision._call_vision = AsyncMock(return_value='{"student_name": null}')
    vision.extract_student_answers = AsyncMock(return_value={
        "student_name": None,
        "answers": {},
        "confidence_flags": {},
    })
    return vision


@pytest.fixture
def svc(mock_ocr, mock_vision) -> GroupingService:
    """Return a GroupingService with mocked dependencies."""
    return GroupingService(ocr_service=mock_ocr, vision_service=mock_vision)


TEMPLATE = {
    "name": "Test Exam",
    "max_score": 10,
    "sections": [
        {
            "name": "Section 1",
            "total_points": 10,
            "parts": [
                {
                    "name": "MC",
                    "questions": ["1", "2", "3"],
                    "type": "multiple_choice",
                    "options": ["A", "B", "C", "D"],
                    "points_each": 2,
                }
            ],
        }
    ],
}


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

class TestHelpers:
    def test_normalize_name(self):
        assert GroupingService._normalize_name("  juan   perez ") == "Juan Perez"
        assert GroupingService._normalize_name("MARIA LOPEZ") == "Maria Lopez"
        assert GroupingService._normalize_name("ana") == "Ana"

    def test_names_are_similar_true(self):
        assert GroupingService._names_are_similar("Juan Perez", "Juan Pérez") is True
        assert GroupingService._names_are_similar("Juan Perez", "Juan Peres") is True

    def test_names_are_similar_false(self):
        assert GroupingService._names_are_similar("Juan Perez", "Maria Lopez") is False

    def test_parse_json_response_clean(self):
        r = GroupingService._parse_json_response('{"key": "value"}')
        assert r == {"key": "value"}

    def test_parse_json_response_with_fences(self):
        r = GroupingService._parse_json_response('```json\n{"key": "value"}\n```')
        assert r == {"key": "value"}

    def test_parse_json_response_invalid(self):
        with pytest.raises(json.JSONDecodeError):
            GroupingService._parse_json_response("not json")


# ═══════════════════════════════════════════════════════════════
# 1. group_photos_by_student
# ═══════════════════════════════════════════════════════════════

class TestGroupPhotosByStudent:
    @pytest.mark.asyncio
    async def test_ocr_detects_all_names(self, svc, mock_ocr):
        """Each photo has a detectable name via OCR."""
        mock_ocr.extract_text = AsyncMock(side_effect=[
            "Name: Juan Perez\nQ1: B",
            "Name: Maria Lopez\nQ1: A",
            "Name: Carlos Ruiz\nQ1: C",
        ])
        mock_ocr.detect_name = AsyncMock(side_effect=[
            "Juan Perez", "Maria Lopez", "Carlos Ruiz"
        ])

        result = await svc.group_photos_by_student(["p1.jpg", "p2.jpg", "p3.jpg"])

        assert len(result) == 3
        assert "Juan Perez" in result
        assert "Maria Lopez" in result
        assert "Carlos Ruiz" in result
        assert result["Juan Perez"] == ["p1.jpg"]

    @pytest.mark.asyncio
    async def test_vision_fallback_when_ocr_fails(self, svc, mock_ocr, mock_vision):
        """OCR returns no name → falls back to Vision."""
        mock_ocr.extract_text = AsyncMock(return_value="some text without name")
        mock_ocr.detect_name = AsyncMock(return_value=None)
        mock_vision._call_vision = AsyncMock(
            return_value='{"student_name": "Ana Torres"}'
        )

        result = await svc.group_photos_by_student(["p1.jpg"])

        assert "Ana Torres" in result
        assert result["Ana Torres"] == ["p1.jpg"]
        mock_vision._call_vision.assert_called_once()

    @pytest.mark.asyncio
    async def test_continuation_when_no_name(self, svc, mock_ocr, mock_vision):
        """Page 2 has no name → groups with previous student."""
        mock_ocr.extract_text = AsyncMock(side_effect=[
            "Name: Juan Perez\nQ1: B",
            "Q2: C\nQ3: A",  # no name on second page
        ])
        mock_ocr.detect_name = AsyncMock(side_effect=["Juan Perez", None])
        mock_vision._call_vision = AsyncMock(
            return_value='{"student_name": null}'
        )

        result = await svc.group_photos_by_student(["p1.jpg", "p2.jpg"])

        assert len(result) == 1
        assert result["Juan Perez"] == ["p1.jpg", "p2.jpg"]

    @pytest.mark.asyncio
    async def test_desconocido_when_first_has_no_name(self, svc, mock_ocr, mock_vision):
        """First photo has no name and no previous → 'Desconocido'."""
        mock_ocr.extract_text = AsyncMock(return_value="Q1: B")
        mock_ocr.detect_name = AsyncMock(return_value=None)
        mock_vision._call_vision = AsyncMock(
            return_value='{"student_name": null}'
        )

        result = await svc.group_photos_by_student(["p1.jpg"])

        assert "Desconocido" in result
        assert result["Desconocido"] == ["p1.jpg"]

    @pytest.mark.asyncio
    async def test_fuzzy_dedup_similar_names(self, svc, mock_ocr):
        """OCR detects 'Juan Perez' then 'Juan Peres' (typo) → same group."""
        mock_ocr.extract_text = AsyncMock(side_effect=["Name: Juan Perez", "Name: Juan Peres"])
        mock_ocr.detect_name = AsyncMock(side_effect=["Juan Perez", "Juan Peres"])

        result = await svc.group_photos_by_student(["p1.jpg", "p2.jpg"])

        assert len(result) == 1
        assert "Juan Perez" in result
        assert result["Juan Perez"] == ["p1.jpg", "p2.jpg"]

    @pytest.mark.asyncio
    async def test_multiple_students_interleaved(self, svc, mock_ocr):
        """Multiple students, each with 2 pages."""
        mock_ocr.extract_text = AsyncMock(side_effect=[
            "Name: Juan Perez", "Q2 answer",
            "Name: Maria Lopez", "Q2 answer",
        ])
        mock_ocr.detect_name = AsyncMock(side_effect=[
            "Juan Perez", None, "Maria Lopez", None,
        ])

        result = await svc.group_photos_by_student([
            "j1.jpg", "j2.jpg", "m1.jpg", "m2.jpg"
        ])

        assert len(result) == 2
        assert result["Juan Perez"] == ["j1.jpg", "j2.jpg"]
        assert result["Maria Lopez"] == ["m1.jpg", "m2.jpg"]

    @pytest.mark.asyncio
    async def test_ocr_exception_handled(self, svc, mock_ocr, mock_vision):
        """OCR throws an exception → gracefully falls back to Vision."""
        mock_ocr.extract_text = AsyncMock(side_effect=Exception("PaddleOCR crashed"))
        mock_vision._call_vision = AsyncMock(
            return_value='{"student_name": "Rescue Student"}'
        )

        result = await svc.group_photos_by_student(["p1.jpg"])

        assert "Rescue Student" in result

    @pytest.mark.asyncio
    async def test_empty_photo_list(self, svc):
        """Empty input returns empty dict."""
        result = await svc.group_photos_by_student([])
        assert result == {}


# ═══════════════════════════════════════════════════════════════
# 2. merge_student_pages
# ═══════════════════════════════════════════════════════════════

class TestMergeStudentPages:
    @pytest.mark.asyncio
    async def test_single_page_uses_vision_directly(self, svc, mock_vision):
        """Single page → uses VisionService.extract_student_answers."""
        mock_vision.extract_student_answers = AsyncMock(return_value={
            "student_name": "Juan",
            "answers": {"1": "B", "2": "C", "3": "A"},
            "confidence_flags": {},
        })
        grouped = {"Juan Perez": ["p1.jpg"]}

        result = await svc.merge_student_pages(grouped, TEMPLATE)

        assert result["Juan Perez"] == {"1": "B", "2": "C", "3": "A"}
        mock_vision.extract_student_answers.assert_called_once_with(
            image_path="p1.jpg", template=TEMPLATE
        )

    @pytest.mark.asyncio
    async def test_multi_page_uses_ocr_then_vision_merge(self, svc, mock_ocr, mock_vision):
        """Multiple pages → OCR each, then Claude merges."""
        mock_ocr.extract_text = AsyncMock(side_effect=[
            "Q1: B\nQ2: C",
            "Q3: A",
        ])
        mock_vision._call_vision = AsyncMock(
            return_value='{"1": "B", "2": "C", "3": "A"}'
        )
        grouped = {"Juan Perez": ["p1.jpg", "p2.jpg"]}

        result = await svc.merge_student_pages(grouped, TEMPLATE)

        assert result["Juan Perez"] == {"1": "B", "2": "C", "3": "A"}
        assert mock_ocr.extract_text.call_count == 2
        mock_vision._call_vision.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_student_merge(self, svc, mock_vision):
        """Multiple students, single page each."""
        mock_vision.extract_student_answers = AsyncMock(side_effect=[
            {"student_name": "Juan", "answers": {"1": "B"}, "confidence_flags": {}},
            {"student_name": "Maria", "answers": {"1": "A"}, "confidence_flags": {}},
        ])
        grouped = {"Juan Perez": ["j1.jpg"], "Maria Lopez": ["m1.jpg"]}

        result = await svc.merge_student_pages(grouped, TEMPLATE)

        assert result["Juan Perez"] == {"1": "B"}
        assert result["Maria Lopez"] == {"1": "A"}

    @pytest.mark.asyncio
    async def test_merge_handles_vision_failure(self, svc, mock_vision):
        """Vision failure → empty answers dict for that student."""
        mock_vision.extract_student_answers = AsyncMock(
            side_effect=Exception("Claude API down")
        )
        grouped = {"Juan Perez": ["p1.jpg"]}

        result = await svc.merge_student_pages(grouped, TEMPLATE)

        assert result["Juan Perez"] == {}

    @pytest.mark.asyncio
    async def test_merge_ocr_failure_on_one_page(self, svc, mock_ocr, mock_vision):
        """OCR fails on one page → still attempts merge with remaining text."""
        mock_ocr.extract_text = AsyncMock(side_effect=[
            "Q1: B",
            Exception("OCR failed on this page"),
        ])
        mock_vision._call_vision = AsyncMock(
            return_value='{"1": "B", "2": "C"}'
        )
        grouped = {"Juan Perez": ["p1.jpg", "p2.jpg"]}

        result = await svc.merge_student_pages(grouped, TEMPLATE)

        assert result["Juan Perez"] == {"1": "B", "2": "C"}


# ═══════════════════════════════════════════════════════════════
# 3. validate_grouping
# ═══════════════════════════════════════════════════════════════

class TestValidateGrouping:
    def test_clean_grouping_no_warnings(self, svc):
        grouped = {
            "Juan Perez": ["p1.jpg", "p2.jpg"],
            "Maria Lopez": ["p3.jpg", "p4.jpg"],
        }
        warnings = svc.validate_grouping(grouped)
        assert warnings == []

    def test_detects_desconocido(self, svc):
        grouped = {
            "Juan Perez": ["p1.jpg"],
            "Desconocido": ["p2.jpg", "p3.jpg"],
        }
        warnings = svc.validate_grouping(grouped)
        types = [w["type"] for w in warnings]
        assert "unidentified" in types
        msg = next(w for w in warnings if w["type"] == "unidentified")
        assert "2 foto(s)" in msg["message"]

    def test_detects_ambiguous_names(self, svc):
        # Names must fall in 0.65–0.80 similarity to trigger warning.
        # "Juan Rodriguez" vs "Juan Martinez" ≈ 0.667
        grouped = {
            "Juan Rodriguez": ["p1.jpg"],
            "Juan Martinez": ["p2.jpg"],
        }
        warnings = svc.validate_grouping(grouped)
        types = [w["type"] for w in warnings]
        assert "ambiguous_name" in types

    def test_detects_few_pages(self, svc):
        grouped = {
            "Juan Perez": ["p1.jpg", "p2.jpg", "p3.jpg"],
            "Maria Lopez": ["p4.jpg", "p5.jpg", "p6.jpg"],
            "Carlos Ruiz": ["p7.jpg"],  # only 1 page, avg is 2.33
        }
        warnings = svc.validate_grouping(grouped)
        types = [w["type"] for w in warnings]
        assert "few_pages" in types

    def test_detects_many_pages(self, svc):
        grouped = {
            "Juan Perez": ["p1.jpg", "p2.jpg"],
            "Maria Lopez": ["p3.jpg", "p4.jpg"],
            "Carlos Ruiz": [f"p{i}.jpg" for i in range(10, 20)],  # 10 pages, avg ~4.67
        }
        warnings = svc.validate_grouping(grouped)
        types = [w["type"] for w in warnings]
        assert "many_pages" in types

    def test_detects_empty_group(self, svc):
        grouped = {
            "Juan Perez": ["p1.jpg"],
            "Empty Student": [],
        }
        warnings = svc.validate_grouping(grouped)
        types = [w["type"] for w in warnings]
        assert "empty_group" in types

    def test_multiple_warnings_combined(self, svc):
        grouped = {
            "Juan Rodriguez": ["p1.jpg", "p2.jpg", "p3.jpg"],
            "Juan Martinez": ["p4.jpg", "p5.jpg", "p6.jpg"],
            "Desconocido": ["p7.jpg"],
        }
        warnings = svc.validate_grouping(grouped)
        types = [w["type"] for w in warnings]
        assert "unidentified" in types
        assert "ambiguous_name" in types


# ═══════════════════════════════════════════════════════════════
# Full pipeline simulation
# ═══════════════════════════════════════════════════════════════

class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_classroom_scenario(self, svc, mock_ocr, mock_vision):
        """Simulate a real classroom: 3 students, 2 pages each, one with OCR fallback."""
        # Pages in order: Juan p1, Juan p2, Maria p1, Maria p2, Carlos p1, Carlos p2
        # OCR detect_name returns None for pages 2,4,5,6.
        # Vision fallback is called for each None: p2, p4, p5, p6.
        mock_ocr.extract_text = AsyncMock(side_effect=[
            "Name: Juan Perez\nQ1: B\nQ2: C",
            "Q3: A\nQ4: D",
            "Name: Maria Lopez\nQ1: A\nQ2: A",
            "Q3: B\nQ4: C",
            "Some text without name",
            "Q3: D\nQ4: B",
        ])
        mock_ocr.detect_name = AsyncMock(side_effect=[
            "Juan Perez", None, "Maria Lopez", None, None, None,
        ])
        # Vision fallback called for p2, p4, p5, p6 (all where detect_name=None)
        mock_vision._call_vision = AsyncMock(side_effect=[
            '{"student_name": null}',            # p2 → no name → continuation of Juan
            '{"student_name": null}',            # p4 → no name → continuation of Maria
            '{"student_name": "Carlos Ruiz"}',  # p5 → Carlos detected
            '{"student_name": null}',            # p6 → no name → continuation of Carlos
        ])

        # Step 1: Group
        photos = [f"p{i}.jpg" for i in range(1, 7)]
        grouped = await svc.group_photos_by_student(photos)

        assert len(grouped) == 3
        assert grouped["Juan Perez"] == ["p1.jpg", "p2.jpg"]
        assert grouped["Maria Lopez"] == ["p3.jpg", "p4.jpg"]
        assert grouped["Carlos Ruiz"] == ["p5.jpg", "p6.jpg"]

        # Step 2: Validate
        warnings = svc.validate_grouping(grouped)
        assert warnings == []  # clean grouping

        # Step 3: Merge (reset mock for merge calls)
        mock_ocr.extract_text = AsyncMock(side_effect=[
            "Q1: B\nQ2: C", "Q3: A\nQ4: D",
            "Q1: A\nQ2: A", "Q3: B\nQ4: C",
            "Q1: C\nQ2: B", "Q3: D\nQ4: B",
        ])
        mock_vision._call_vision = AsyncMock(side_effect=[
            '{"1": "B", "2": "C", "3": "A", "4": "D"}',
            '{"1": "A", "2": "A", "3": "B", "4": "C"}',
            '{"1": "C", "2": "B", "3": "D", "4": "B"}',
        ])

        merged = await svc.merge_student_pages(grouped, TEMPLATE)

        assert merged["Juan Perez"] == {"1": "B", "2": "C", "3": "A", "4": "D"}
        assert merged["Maria Lopez"] == {"1": "A", "2": "A", "3": "B", "4": "C"}
        assert merged["Carlos Ruiz"] == {"1": "C", "2": "B", "3": "D", "4": "B"}
