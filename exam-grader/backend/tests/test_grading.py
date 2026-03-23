"""
Tests for GradingService — covers all 8 question types + dispatcher.

AI-dependent methods (short_answer, essay, fill_blank) are tested with
mocked API responses so the suite runs offline and deterministically.
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ── Ensure minimal env vars so Settings can load ─────────────
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake-key")
os.environ.setdefault("DATABASE_URL", "postgresql://fake")
os.environ.setdefault("ANTHROPIC_API_KEY", "fake-anthropic-key")
os.environ.setdefault("OPENAI_API_KEY", "fake-openai-key")
os.environ.setdefault("JWT_SECRET", "fake-jwt-secret")

from app.services.grading_service import GradingService


# ── Fixture ──────────────────────────────────────────────────

@pytest.fixture
def svc() -> GradingService:
    """Return a GradingService with mocked AI clients."""
    with patch("app.services.grading_service.get_settings") as mock_settings:
        s = MagicMock()
        s.ANTHROPIC_API_KEY = "fake"
        s.OPENAI_API_KEY = "fake"
        mock_settings.return_value = s
        service = GradingService()
    return service


# ═══════════════════════════════════════════════════════════════
# 1. Multiple Choice
# ═══════════════════════════════════════════════════════════════

class TestMultipleChoice:
    def test_correct(self, svc: GradingService):
        r = svc.grade_multiple_choice("B", "B", 2.0)
        assert r["is_correct"] is True
        assert r["points_earned"] == 2.0
        assert r["points_possible"] == 2.0

    def test_correct_case_insensitive(self, svc: GradingService):
        r = svc.grade_multiple_choice("b", "B", 2.0)
        assert r["is_correct"] is True

    def test_correct_with_whitespace(self, svc: GradingService):
        r = svc.grade_multiple_choice("  c  ", "C", 1.0)
        assert r["is_correct"] is True

    def test_incorrect(self, svc: GradingService):
        r = svc.grade_multiple_choice("A", "D", 3.0)
        assert r["is_correct"] is False
        assert r["points_earned"] == 0.0
        assert "D" in r["feedback"]


# ═══════════════════════════════════════════════════════════════
# 2. True / False
# ═══════════════════════════════════════════════════════════════

class TestTrueFalse:
    @pytest.mark.parametrize("student,correct", [
        ("True", "True"),
        ("T", "Verdadero"),
        ("V", "True"),
        ("verdadero", "T"),
        ("False", "False"),
        ("F", "Falso"),
        ("falso", "F"),
    ])
    def test_correct_variants(self, svc: GradingService, student: str, correct: str):
        r = svc.grade_true_false(student, correct, 1.0)
        assert r["is_correct"] is True
        assert r["points_earned"] == 1.0

    def test_incorrect(self, svc: GradingService):
        r = svc.grade_true_false("True", "False", 1.0)
        assert r["is_correct"] is False
        assert r["points_earned"] == 0.0

    def test_unrecognized_student_answer(self, svc: GradingService):
        r = svc.grade_true_false("maybe", "True", 1.0)
        assert r["is_correct"] is False
        assert "no reconocida" in r["feedback"]


# ═══════════════════════════════════════════════════════════════
# 3. Short Answer (mocked OpenAI)
# ═══════════════════════════════════════════════════════════════

class TestShortAnswer:
    @pytest.mark.asyncio
    async def test_correct(self, svc: GradingService):
        svc._call_openai = AsyncMock(return_value="CORRECT")
        r = await svc.grade_short_answer("mitocondria", "la mitocondria", 5.0)
        assert r["is_correct"] is True
        assert r["points_earned"] == 5.0

    @pytest.mark.asyncio
    async def test_partial(self, svc: GradingService):
        svc._call_openai = AsyncMock(return_value="PARTIAL")
        r = await svc.grade_short_answer("celula", "la mitocondria", 4.0)
        assert r["is_correct"] is False
        assert r["points_earned"] == 2.0

    @pytest.mark.asyncio
    async def test_incorrect(self, svc: GradingService):
        svc._call_openai = AsyncMock(return_value="INCORRECT")
        r = await svc.grade_short_answer("nucleo", "la mitocondria", 4.0)
        assert r["is_correct"] is False
        assert r["points_earned"] == 0.0

    @pytest.mark.asyncio
    async def test_empty_answer(self, svc: GradingService):
        r = await svc.grade_short_answer("", "answer", 3.0)
        assert r["is_correct"] is False
        assert r["points_earned"] == 0.0
        assert "Sin respuesta" in r["feedback"]


# ═══════════════════════════════════════════════════════════════
# 4. Essay (mocked Claude)
# ═══════════════════════════════════════════════════════════════

class TestEssay:
    @pytest.mark.asyncio
    async def test_high_score(self, svc: GradingService):
        svc._call_claude = AsyncMock(return_value=json.dumps({
            "points_earned": 9.5,
            "feedback": "Excellent analysis with strong arguments.",
        }))
        rubric = {"content": 5, "grammar": 3, "structure": 2}
        r = await svc.grade_essay("A well-written essay...", rubric, 10.0)
        assert r["points_earned"] == 9.5
        assert r["is_correct"] is True  # >=90%

    @pytest.mark.asyncio
    async def test_low_score(self, svc: GradingService):
        svc._call_claude = AsyncMock(return_value=json.dumps({
            "points_earned": 3.0,
            "feedback": "Needs improvement in structure.",
        }))
        rubric = {"content": 5, "grammar": 3, "structure": 2}
        r = await svc.grade_essay("Short essay.", rubric, 10.0)
        assert r["points_earned"] == 3.0
        assert r["is_correct"] is False

    @pytest.mark.asyncio
    async def test_empty_essay(self, svc: GradingService):
        r = await svc.grade_essay("", {}, 10.0)
        assert r["points_earned"] == 0.0
        assert "Sin respuesta" in r["feedback"]

    @pytest.mark.asyncio
    async def test_malformed_ai_response(self, svc: GradingService):
        svc._call_claude = AsyncMock(return_value="not json at all")
        r = await svc.grade_essay("Some essay text", {"criteria": 10}, 10.0)
        assert r["points_earned"] == 0.0
        assert "Error" in r["feedback"]


# ═══════════════════════════════════════════════════════════════
# 5. Fill in the Blank (mocked OpenAI)
# ═══════════════════════════════════════════════════════════════

class TestFillBlank:
    @pytest.mark.asyncio
    async def test_exact_match(self, svc: GradingService):
        r = await svc.grade_fill_blank("photosynthesis", "Photosynthesis", 2.0)
        assert r["is_correct"] is True
        assert r["points_earned"] == 2.0

    @pytest.mark.asyncio
    async def test_typo_accepted(self, svc: GradingService):
        svc._call_openai = AsyncMock(return_value="CORRECT")
        r = await svc.grade_fill_blank("photosintesis", "photosynthesis", 2.0)
        assert r["is_correct"] is True

    @pytest.mark.asyncio
    async def test_wrong_answer(self, svc: GradingService):
        svc._call_openai = AsyncMock(return_value="INCORRECT")
        r = await svc.grade_fill_blank("respiration", "photosynthesis", 2.0)
        assert r["is_correct"] is False
        assert r["points_earned"] == 0.0

    @pytest.mark.asyncio
    async def test_empty(self, svc: GradingService):
        r = await svc.grade_fill_blank("  ", "answer", 2.0)
        assert r["is_correct"] is False


# ═══════════════════════════════════════════════════════════════
# 6. Matching
# ═══════════════════════════════════════════════════════════════

class TestMatching:
    def test_all_correct(self, svc: GradingService):
        student = {"A": "1", "B": "2", "C": "3"}
        correct = {"A": "1", "B": "2", "C": "3"}
        r = svc.grade_matching(student, correct, 6.0)
        assert r["is_correct"] is True
        assert r["points_earned"] == 6.0

    def test_partial(self, svc: GradingService):
        student = {"A": "1", "B": "3", "C": "2"}
        correct = {"A": "1", "B": "2", "C": "3"}
        r = svc.grade_matching(student, correct, 6.0)
        assert r["is_correct"] is False
        assert r["points_earned"] == 2.0  # 1/3 * 6

    def test_all_wrong(self, svc: GradingService):
        student = {"A": "3", "B": "1", "C": "2"}
        correct = {"A": "1", "B": "2", "C": "3"}
        r = svc.grade_matching(student, correct, 6.0)
        assert r["points_earned"] == 0.0

    def test_missing_keys(self, svc: GradingService):
        student = {"A": "1"}
        correct = {"A": "1", "B": "2", "C": "3"}
        r = svc.grade_matching(student, correct, 6.0)
        assert r["points_earned"] == 2.0  # 1/3 * 6


# ═══════════════════════════════════════════════════════════════
# 7. Multiple Response
# ═══════════════════════════════════════════════════════════════

class TestMultipleResponse:
    def test_all_correct(self, svc: GradingService):
        r = svc.grade_multiple_response(["A", "C", "D"], ["A", "C", "D"], 4.0)
        assert r["is_correct"] is True
        assert r["points_earned"] == 4.0

    def test_partial_no_extra(self, svc: GradingService):
        r = svc.grade_multiple_response(["A", "C"], ["A", "C", "D"], 3.0)
        assert r["is_correct"] is False
        assert r["points_earned"] == 2.0  # 2/3 * 3

    def test_with_incorrect_selection(self, svc: GradingService):
        # correct_selected=2, incorrect=1, total=3 → (2-1)/3 = 1/3
        r = svc.grade_multiple_response(["A", "C", "B"], ["A", "C", "D"], 3.0)
        assert r["points_earned"] == 1.0  # 1/3 * 3

    def test_all_wrong_floors_at_zero(self, svc: GradingService):
        r = svc.grade_multiple_response(["B", "E"], ["A", "C", "D"], 3.0)
        assert r["points_earned"] == 0.0

    def test_case_insensitive(self, svc: GradingService):
        r = svc.grade_multiple_response(["a", "c"], ["A", "C"], 2.0)
        assert r["is_correct"] is True


# ═══════════════════════════════════════════════════════════════
# 8. Ordering
# ═══════════════════════════════════════════════════════════════

class TestOrdering:
    def test_correct_order(self, svc: GradingService):
        r = svc.grade_ordering(["s1", "s2", "s3"], ["s1", "s2", "s3"], 3.0)
        assert r["is_correct"] is True
        assert r["points_earned"] == 3.0

    def test_partial_order(self, svc: GradingService):
        r = svc.grade_ordering(["s1", "s3", "s2"], ["s1", "s2", "s3"], 3.0)
        assert r["is_correct"] is False
        assert r["points_earned"] == 1.0  # 1/3 * 3

    def test_all_wrong_order(self, svc: GradingService):
        r = svc.grade_ordering(["s3", "s1", "s2"], ["s1", "s2", "s3"], 3.0)
        assert r["points_earned"] == 0.0

    def test_empty_correct(self, svc: GradingService):
        r = svc.grade_ordering([], [], 3.0)
        assert r["is_correct"] is True
        assert r["points_earned"] == 3.0


# ═══════════════════════════════════════════════════════════════
# Dispatcher – grade_question()
# ═══════════════════════════════════════════════════════════════

class TestDispatcher:
    @pytest.mark.asyncio
    async def test_routes_multiple_choice(self, svc: GradingService):
        r = await svc.grade_question("multiple_choice", "B", "B", 2.0)
        assert r["is_correct"] is True

    @pytest.mark.asyncio
    async def test_routes_true_false(self, svc: GradingService):
        r = await svc.grade_question("true_false", "Verdadero", "True", 1.0)
        assert r["is_correct"] is True

    @pytest.mark.asyncio
    async def test_routes_short_answer(self, svc: GradingService):
        svc._call_openai = AsyncMock(return_value="CORRECT")
        r = await svc.grade_question("short_answer", "answer", "answer", 5.0)
        assert r["is_correct"] is True

    @pytest.mark.asyncio
    async def test_routes_essay(self, svc: GradingService):
        svc._call_claude = AsyncMock(return_value=json.dumps({
            "points_earned": 10, "feedback": "Perfect.",
        }))
        r = await svc.grade_question(
            "essay", "My essay", "ignored", 10.0,
            rubric={"content": 10}
        )
        assert r["is_correct"] is True

    @pytest.mark.asyncio
    async def test_routes_long_answer_alias(self, svc: GradingService):
        svc._call_claude = AsyncMock(return_value=json.dumps({
            "points_earned": 8, "feedback": "Good.",
        }))
        r = await svc.grade_question("long_answer", "text", "ignored", 10.0, rubric={})
        assert r["points_earned"] == 8.0

    @pytest.mark.asyncio
    async def test_routes_fill_blank(self, svc: GradingService):
        r = await svc.grade_question("fill_blank", "answer", "answer", 2.0)
        assert r["is_correct"] is True

    @pytest.mark.asyncio
    async def test_routes_matching(self, svc: GradingService):
        r = await svc.grade_question(
            "matching",
            {"A": "1", "B": "2"},
            {"A": "1", "B": "2"},
            4.0,
        )
        assert r["is_correct"] is True

    @pytest.mark.asyncio
    async def test_routes_multiple_response(self, svc: GradingService):
        r = await svc.grade_question(
            "multiple_response",
            ["A", "C"],
            ["A", "C"],
            2.0,
        )
        assert r["is_correct"] is True

    @pytest.mark.asyncio
    async def test_routes_ordering(self, svc: GradingService):
        r = await svc.grade_question("ordering", ["a", "b"], ["a", "b"], 2.0)
        assert r["is_correct"] is True

    @pytest.mark.asyncio
    async def test_unsupported_type(self, svc: GradingService):
        r = await svc.grade_question("unknown_type", "x", "y", 1.0)
        assert r["is_correct"] is False
        assert "no soportado" in r["feedback"]


# ═══════════════════════════════════════════════════════════════
# Full exam simulation
# ═══════════════════════════════════════════════════════════════

class TestFullExamSimulation:
    """Simulate grading a complete multi-type exam."""

    @pytest.mark.asyncio
    async def test_biology_exam(self, svc: GradingService):
        svc._call_openai = AsyncMock(return_value="CORRECT")
        svc._call_claude = AsyncMock(return_value=json.dumps({
            "points_earned": 8.0,
            "feedback": "Good analysis of photosynthesis process.",
        }))

        exam = [
            ("multiple_choice", "B", "B", 2.0, {}),
            ("multiple_choice", "A", "C", 2.0, {}),
            ("true_false", "Verdadero", "True", 1.0, {}),
            ("true_false", "F", "True", 1.0, {}),
            ("short_answer", "La mitocondria es la central energética", "Mitocondria", 5.0, {}),
            ("fill_blank", "ADN", "ADN", 2.0, {}),
            ("matching", {"A": "1", "B": "2", "C": "3"}, {"A": "1", "B": "2", "C": "3"}, 6.0, {}),
            ("multiple_response", ["A", "C", "D"], ["A", "C", "D"], 4.0, {}),
            ("ordering", ["s1", "s2", "s3"], ["s1", "s2", "s3"], 3.0, {}),
            ("essay", "Detailed essay about cell division...", "ignored", 10.0,
             {"rubric": {"content": 5, "clarity": 3, "examples": 2}}),
        ]

        total_earned = 0.0
        total_possible = 0.0
        results = []

        for qtype, student, correct, pts, kw in exam:
            r = await svc.grade_question(qtype, student, correct, pts, **kw)
            total_earned += r["points_earned"]
            total_possible += r["points_possible"]
            results.append(r)

        assert total_possible == 36.0
        # Q1: 2, Q2: 0, Q3: 1, Q4: 0, Q5: 5, Q6: 2, Q7: 6, Q8: 4, Q9: 3, Q10: 8
        assert total_earned == 31.0

    @pytest.mark.asyncio
    async def test_english_exam(self, svc: GradingService):
        svc._call_openai = AsyncMock(return_value="PARTIAL")
        svc._call_claude = AsyncMock(return_value=json.dumps({
            "points_earned": 6.0,
            "feedback": "Decent grammar but lacks vocabulary variety.",
        }))

        exam = [
            ("multiple_choice", "A", "A", 1.0, {}),
            ("multiple_choice", "B", "A", 1.0, {}),
            ("multiple_choice", "C", "C", 1.0, {}),
            ("true_false", "True", "True", 1.0, {}),
            ("true_false", "False", "False", 1.0, {}),
            ("fill_blank", "went", "went", 2.0, {}),
            ("short_answer", "He go to school", "He went to school", 3.0, {}),
            ("matching", {"1": "B", "2": "A"}, {"1": "A", "2": "B"}, 4.0, {}),
            ("ordering", ["first", "then", "finally"], ["first", "then", "finally"], 3.0, {}),
            ("essay", "My essay about climate change...", "ignored", 10.0,
             {"rubric": {"thesis": 3, "arguments": 4, "grammar": 3}}),
        ]

        total_earned = 0.0
        total_possible = 0.0

        for qtype, student, correct, pts, kw in exam:
            r = await svc.grade_question(qtype, student, correct, pts, **kw)
            total_earned += r["points_earned"]
            total_possible += r["points_possible"]

        assert total_possible == 27.0
        # Q1:1, Q2:0, Q3:1, Q4:1, Q5:1, Q6:2, Q7:1.5(partial), Q8:0, Q9:3, Q10:6
        assert total_earned == 16.5
