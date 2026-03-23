import json
import logging
from typing import Any, Optional, Union

import anthropic
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────

TRUE_VALUES = {"true", "t", "verdadero", "v", "1"}
FALSE_VALUES = {"false", "f", "falso", "0"}

SEMANTIC_SIMILARITY_PROMPT = """\
You are a strict exam grader. Compare the student's answer with the correct answer.
Determine if they are semantically equivalent.

Correct answer: {correct}
Student answer: {student}

Respond with EXACTLY one word:
- CORRECT   → if the answers are semantically equivalent
- PARTIAL   → if the student's answer is partially correct or captures the main idea but is incomplete
- INCORRECT → if the answers are clearly different

Your response (one word only):"""

ESSAY_GRADING_PROMPT = """\
You are an expert exam grader. Evaluate the following student essay based on the provided rubric.

Rubric:
{rubric}

Student answer:
{student}

Maximum points: {points}

Return a JSON object with exactly these keys:
{{
  "points_earned": <number between 0 and {points}>,
  "feedback": "<detailed feedback explaining the grade, referencing specific rubric criteria>"
}}

Return ONLY valid JSON, no markdown fences, no explanation outside the JSON."""

FILL_BLANK_PROMPT = """\
You are a strict exam grader. Compare the student's answer with the correct answer for a fill-in-the-blank question.
This requires a more exact match than an essay — spelling errors or minor typos are acceptable, but the core answer must be correct.

Correct answer: {correct}
Student answer: {student}

Respond with EXACTLY one word:
- CORRECT   → if the answers match (minor typos allowed)
- INCORRECT → if the answers are clearly different

Your response (one word only):"""

BATCH_SHORT_ANSWER_PROMPT = """\
You are a strict exam grader. For each question below, compare the student's answer with the correct answer.
Determine if they are semantically equivalent.

Questions:
{questions}

For each question respond with EXACTLY one word on its own line (in order):
- CORRECT   → semantically equivalent
- PARTIAL   → partially correct / captures main idea but incomplete
- INCORRECT → clearly different

Respond with exactly {count} lines, one word per line, nothing else."""

IMPROVEMENT_PLAN_PROMPT = """\
You are an expert educational consultant. Analyze the following exam results and generate
a structured, actionable improvement plan for the student.

Student name: {student_name}

Exam structure:
{template_json}

Grading results:
{results_json}

Analyze the results by section, identify error patterns, and generate a personalized
improvement plan. Prioritize recommendations by impact vs effort.

Return a JSON object with EXACTLY this structure:
{{
  "overall_performance": "Good" | "Average" | "Needs Improvement",
  "score_analysis": {{
    "strengths": ["Section X: 90%", ...],
    "weaknesses": ["Essay writing: 40%", ...]
  }},
  "improvement_plan": {{
    "immediate_actions": [
      {{
        "topic": "<topic>",
        "description": "<actionable description>",
        "resources": ["<resource 1>", "<resource 2>"],
        "estimated_time": "<time estimate>"
      }}
    ],
    "medium_term_goals": [
      {{
        "topic": "<topic>",
        "description": "<description>",
        "resources": ["<resource>"],
        "estimated_time": "<time estimate>"
      }}
    ],
    "long_term_goals": [
      {{
        "topic": "<topic>",
        "description": "<description>",
        "resources": ["<resource>"],
        "estimated_time": "<time estimate>"
      }}
    ]
  }},
  "specific_recommendations": [
    "<recommendation 1>",
    "<recommendation 2>"
  ],
  "next_steps": "<summary of immediate next steps>"
}}

Return ONLY valid JSON, no markdown fences, no explanation outside the JSON."""


class GradingService:
    """Service for grading different types of exam questions."""

    CLAUDE_MODEL = "claude-sonnet-4-20250514"
    HAIKU_MODEL = "claude-sonnet-4-20250514"  # same model for all tasks
    MAX_TOKENS = 1024

    def __init__(self) -> None:
        settings = get_settings()
        self._anthropic = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        logger.info("GradingService initialized (Claude only)")

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _result(
        is_correct: bool,
        points_earned: float,
        points_possible: float,
        feedback: str,
    ) -> dict[str, Any]:
        """Build a standardized grading result dict."""
        return {
            "is_correct": is_correct,
            "points_earned": round(points_earned, 2),
            "points_possible": round(points_possible, 2),
            "feedback": feedback,
        }

    @staticmethod
    def _parse_json_response(text: str) -> dict[str, Any]:
        """Parse JSON from an AI response, stripping markdown fences if present."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            first_newline = cleaned.index("\n")
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]
        cleaned = cleaned.strip()
        return json.loads(cleaned)

    # ── AI calls with retry ──────────────────────────────────

    @retry(
        retry=retry_if_exception_type((anthropic.APIStatusError, anthropic.APIConnectionError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _call_claude(self, prompt: str) -> str:
        """Call Claude and return the text response."""
        logger.debug("Calling Claude (%s)", self.CLAUDE_MODEL)
        response = await self._anthropic.messages.create(
            model=self.CLAUDE_MODEL,
            max_tokens=self.MAX_TOKENS,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.content[0].text
        logger.debug("Claude response: %s", result.strip())
        return result.strip()

    @retry(
        retry=retry_if_exception_type(
            (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError)
        ),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def _call_claude_haiku(self, prompt: str) -> str:
        """Call Claude Haiku (cheap & fast) for simple grading tasks."""
        logger.debug("Calling Claude Haiku (%s)", self.HAIKU_MODEL)
        response = await self._anthropic.messages.create(
            model=self.HAIKU_MODEL,
            max_tokens=self.MAX_TOKENS,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.content[0].text
        logger.debug("Claude Haiku response: %s", result.strip())
        return result.strip()

    # ── 1. Multiple Choice ───────────────────────────────────

    def grade_multiple_choice(
        self, student: str, correct: str, points: float
    ) -> dict[str, Any]:
        """Grade a multiple-choice question by exact comparison."""
        s = student.strip().upper()
        c = correct.strip().upper()
        is_correct = s == c
        earned = points if is_correct else 0.0
        feedback = "Correcto." if is_correct else f"Incorrecto. Respuesta correcta: {correct.strip()}."
        logger.debug("MC: student=%s correct=%s → %s", s, c, is_correct)
        return self._result(is_correct, earned, points, feedback)

    # ── 2. True / False ──────────────────────────────────────

    def grade_true_false(
        self, student: str, correct: str, points: float
    ) -> dict[str, Any]:
        """Grade a true/false question accepting multiple variants."""
        s_norm = student.strip().lower()
        c_norm = correct.strip().lower()

        s_bool: Optional[bool] = None
        c_bool: Optional[bool] = None

        if s_norm in TRUE_VALUES:
            s_bool = True
        elif s_norm in FALSE_VALUES:
            s_bool = False

        if c_norm in TRUE_VALUES:
            c_bool = True
        elif c_norm in FALSE_VALUES:
            c_bool = False

        if s_bool is None:
            return self._result(
                False, 0.0, points,
                f"Respuesta no reconocida: '{student.strip()}'. Se esperaba True/False/Verdadero/Falso.",
            )

        if c_bool is None:
            return self._result(
                False, 0.0, points,
                f"Error en clave de respuesta: '{correct.strip()}' no es un valor válido.",
            )

        is_correct = s_bool == c_bool
        earned = points if is_correct else 0.0
        feedback = "Correcto." if is_correct else f"Incorrecto. Respuesta correcta: {correct.strip()}."
        logger.debug("TF: student=%s(%s) correct=%s(%s) → %s", s_norm, s_bool, c_norm, c_bool, is_correct)
        return self._result(is_correct, earned, points, feedback)

    # ── 3. Short Answer (AI semantic similarity) ─────────────

    async def grade_short_answer(
        self, student: str, correct: str, points: float
    ) -> dict[str, Any]:
        """Grade short answer using Claude Haiku for semantic similarity."""
        if not student.strip():
            return self._result(False, 0.0, points, "Sin respuesta.")

        prompt = SEMANTIC_SIMILARITY_PROMPT.format(
            correct=correct.strip(), student=student.strip()
        )
        verdict = await self._call_claude_haiku(prompt)
        verdict_upper = verdict.upper().strip()

        if "CORRECT" == verdict_upper:
            return self._result(True, points, points, "Correcto.")
        elif "PARTIAL" in verdict_upper:
            earned = round(points * 0.5, 2)
            return self._result(False, earned, points, "Parcialmente correcto.")
        else:
            return self._result(
                False, 0.0, points,
                f"Incorrecto. Respuesta esperada: {correct.strip()}.",
            )

    # ── 3b. Short Answer Batch ───────────────────────────────

    async def grade_short_answers_batch(
        self,
        questions: list[tuple],
    ) -> list[dict[str, Any]]:
        """Grade multiple short-answer questions in a single Claude Haiku call.

        Args:
            questions: List of (q_num, student_answer, correct_answer, points).

        Returns:
            List of grading result dicts in the same order.
        """
        if not questions:
            return []

        q_lines = []
        for i, (q_num, student, correct, points) in enumerate(questions, 1):
            s = student.strip() if student else "(no answer)"
            c = correct.strip() if correct else ""
            q_lines.append(f"Q{i}. Correct: {c} | Student: {s}")

        prompt = BATCH_SHORT_ANSWER_PROMPT.format(
            questions="\n".join(q_lines),
            count=len(questions),
        )

        try:
            raw = await self._call_claude_haiku(prompt)
            verdicts = [ln.strip().upper() for ln in raw.strip().splitlines() if ln.strip()]
            logger.debug("Batch short-answer verdicts (%d): %s", len(verdicts), verdicts)
        except Exception as exc:
            logger.error("Batch short-answer grading failed, falling back to individual: %s", exc)
            results = []
            for _, student, correct, points in questions:
                results.append(await self.grade_short_answer(student, correct, points))
            return results

        results: list[dict[str, Any]] = []
        for i, (q_num, student, correct, points) in enumerate(questions):
            if not (student or "").strip():
                results.append(self._result(False, 0.0, points, "Sin respuesta."))
                continue

            verdict = verdicts[i] if i < len(verdicts) else "INCORRECT"
            if verdict == "CORRECT":
                results.append(self._result(True, points, points, "Correcto."))
            elif "PARTIAL" in verdict:
                earned = round(points * 0.5, 2)
                results.append(self._result(False, earned, points, "Parcialmente correcto."))
            else:
                results.append(self._result(
                    False, 0.0, points,
                    f"Incorrecto. Respuesta esperada: {correct.strip()}.",
                ))

        return results

    # ── 4. Essay (Claude + rubric) ───────────────────────────

    async def grade_essay(
        self, student: str, rubric: dict[str, Any], points: float
    ) -> dict[str, Any]:
        """Grade an essay using Claude with a rubric."""
        if not student.strip():
            return self._result(False, 0.0, points, "Sin respuesta.")

        rubric_text = json.dumps(rubric, ensure_ascii=False, indent=2)
        prompt = ESSAY_GRADING_PROMPT.format(
            rubric=rubric_text, student=student.strip(), points=points
        )
        raw = await self._call_claude(prompt)

        try:
            result = self._parse_json_response(raw)
            earned = float(result.get("points_earned", 0))
            earned = max(0.0, min(earned, points))
            feedback = result.get("feedback", "Sin retroalimentación.")
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.error("Failed to parse essay grading response: %s", exc)
            return self._result(
                False, 0.0, points,
                f"Error al evaluar ensayo: {exc}",
            )

        is_correct = earned >= points * 0.9
        logger.debug("Essay: earned=%.2f/%.2f", earned, points)
        return self._result(is_correct, earned, points, feedback)

    # ── 5. Fill in the Blank ─────────────────────────────────

    async def grade_fill_blank(
        self, student: str, correct: str, points: float
    ) -> dict[str, Any]:
        """Grade fill-in-the-blank — stricter than short answer."""
        if not student.strip():
            return self._result(False, 0.0, points, "Sin respuesta.")

        # Fast path: exact match
        if student.strip().lower() == correct.strip().lower():
            return self._result(True, points, points, "Correcto.")

        prompt = FILL_BLANK_PROMPT.format(
            correct=correct.strip(), student=student.strip()
        )
        verdict = await self._call_claude_haiku(prompt)

        if verdict.upper().strip() == "CORRECT":
            return self._result(True, points, points, "Correcto.")
        return self._result(
            False, 0.0, points,
            f"Incorrecto. Respuesta correcta: {correct.strip()}.",
        )

    # ── 6. Matching ──────────────────────────────────────────

    def grade_matching(
        self, student: dict[str, str], correct: dict[str, str], points: float
    ) -> dict[str, Any]:
        """Grade matching — proportional score per correct pair."""
        total_pairs = len(correct)
        if total_pairs == 0:
            return self._result(True, points, points, "Sin pares para evaluar.")

        correct_count = 0
        wrong_pairs: list[str] = []

        for key, expected in correct.items():
            given = student.get(key, "")
            if str(given).strip().lower() == str(expected).strip().lower():
                correct_count += 1
            else:
                wrong_pairs.append(f"{key}→{expected}")

        earned = round(points * (correct_count / total_pairs), 2)
        is_correct = correct_count == total_pairs

        if is_correct:
            feedback = "Todos los pares son correctos."
        else:
            feedback = (
                f"{correct_count}/{total_pairs} pares correctos. "
                f"Incorrectos: {', '.join(wrong_pairs)}."
            )
        logger.debug("Matching: %d/%d pairs correct", correct_count, total_pairs)
        return self._result(is_correct, earned, points, feedback)

    # ── 7. Multiple Response ─────────────────────────────────

    def grade_multiple_response(
        self, student: list[str], correct: list[str], points: float
    ) -> dict[str, Any]:
        """Grade multiple-response: (correct_selected - incorrect_selected) / total_correct, min 0."""
        s_set = {s.strip().upper() for s in student}
        c_set = {c.strip().upper() for c in correct}

        correct_selected = len(s_set & c_set)
        incorrect_selected = len(s_set - c_set)
        total_correct = len(c_set)

        if total_correct == 0:
            return self._result(True, points, points, "Sin opciones correctas definidas.")

        ratio = max(0.0, (correct_selected - incorrect_selected) / total_correct)
        earned = round(points * ratio, 2)
        is_correct = s_set == c_set

        if is_correct:
            feedback = "Todas las opciones son correctas."
        else:
            missing = c_set - s_set
            extra = s_set - c_set
            parts: list[str] = []
            if missing:
                parts.append(f"Faltaron: {', '.join(sorted(missing))}")
            if extra:
                parts.append(f"Sobraron: {', '.join(sorted(extra))}")
            feedback = f"{correct_selected}/{total_correct} correctas. {'. '.join(parts)}."

        logger.debug(
            "MultiResponse: selected=%d correct, %d incorrect, total=%d",
            correct_selected, incorrect_selected, total_correct,
        )
        return self._result(is_correct, earned, points, feedback)

    # ── 8. Ordering ──────────────────────────────────────────

    def grade_ordering(
        self, student: list[str], correct: list[str], points: float
    ) -> dict[str, Any]:
        """Grade ordering — proportional score for elements in correct position."""
        total = len(correct)
        if total == 0:
            return self._result(True, points, points, "Sin elementos para evaluar.")

        correct_positions = sum(
            1 for s, c in zip(student, correct)
            if str(s).strip().lower() == str(c).strip().lower()
        )

        earned = round(points * (correct_positions / total), 2)
        is_correct = correct_positions == total

        if is_correct:
            feedback = "Orden correcto."
        else:
            feedback = f"{correct_positions}/{total} elementos en posición correcta."

        logger.debug("Ordering: %d/%d correct positions", correct_positions, total)
        return self._result(is_correct, earned, points, feedback)

    # ── Improvement Plan Generation ────────────────────────────

    async def generate_improvement_plan(
        self,
        student_results: dict[str, Any],
        template: dict[str, Any],
        student_name: str,
    ) -> dict[str, Any]:
        """Generate a structured improvement plan using Claude.

        Args:
            student_results: Complete grading results (section_scores, feedback, etc.).
            template: Exam template structure (structure_json).
            student_name: Name of the student.

        Returns:
            A dict with overall_performance, score_analysis, improvement_plan,
            specific_recommendations, and next_steps.
        """
        logger.info("Generating improvement plan for '%s'", student_name)

        template_json = json.dumps(template, ensure_ascii=False, indent=2)
        results_json = json.dumps(student_results, ensure_ascii=False, indent=2)

        prompt = IMPROVEMENT_PLAN_PROMPT.format(
            student_name=student_name,
            template_json=template_json,
            results_json=results_json,
        )

        try:
            raw = await self._call_claude(prompt)
            plan = self._parse_json_response(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Failed to parse improvement plan response: %s", exc)
            plan = self._fallback_improvement_plan(student_results, student_name)
        except Exception as exc:
            logger.error("Claude call failed for improvement plan: %s", exc)
            plan = self._fallback_improvement_plan(student_results, student_name)

        logger.info(
            "Improvement plan generated for '%s': %s",
            student_name, plan.get("overall_performance", "unknown"),
        )
        return plan

    @staticmethod
    def _fallback_improvement_plan(
        student_results: dict[str, Any],
        student_name: str,
    ) -> dict[str, Any]:
        """Build a basic improvement plan without AI when Claude fails."""
        total = float(student_results.get("total_score", 0))
        max_score = float(student_results.get("max_score", 1))
        pct = (total / max_score * 100) if max_score > 0 else 0

        if pct >= 80:
            perf = "Good"
        elif pct >= 60:
            perf = "Average"
        else:
            perf = "Needs Improvement"

        strengths: list[str] = []
        weaknesses: list[str] = []
        section_scores = student_results.get("section_scores_json", {})
        for section, scores in section_scores.items():
            earned = float(scores.get("earned", 0))
            sec_max = float(scores.get("max", 1))
            sec_pct = (earned / sec_max * 100) if sec_max > 0 else 0
            entry = f"{section}: {sec_pct:.0f}%"
            if sec_pct >= 70:
                strengths.append(entry)
            else:
                weaknesses.append(entry)

        return {
            "overall_performance": perf,
            "score_analysis": {
                "strengths": strengths or ["No strong sections identified"],
                "weaknesses": weaknesses or ["No weak sections identified"],
            },
            "improvement_plan": {
                "immediate_actions": [{
                    "topic": "Review weak sections",
                    "description": f"Focus on: {', '.join(weaknesses) or 'general review'}",
                    "resources": ["Textbook review", "Practice exercises"],
                    "estimated_time": "2-3 hours/week",
                }],
                "medium_term_goals": [{
                    "topic": "Consistent practice",
                    "description": "Regular practice on identified weak areas",
                    "resources": ["Online practice tests"],
                    "estimated_time": "4 weeks",
                }],
                "long_term_goals": [{
                    "topic": "Mastery",
                    "description": "Achieve proficiency across all sections",
                    "resources": ["Tutoring if needed"],
                    "estimated_time": "1 semester",
                }],
            },
            "specific_recommendations": [
                f"Overall score: {total}/{max_score} ({pct:.0f}%)",
                "Review incorrect answers and understand the correct solutions",
                "Practice similar question types regularly",
            ],
            "next_steps": f"Focus on weakest areas first: {', '.join(weaknesses[:3]) or 'general review'}",
        }

    # ── Dispatcher ───────────────────────────────────────────

    async def grade_question(
        self,
        question_type: str,
        student_answer: Union[str, list, dict],
        correct_answer: Union[str, list, dict],
        points: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Route to the appropriate grading method based on question type."""
        qtype = question_type.strip().lower()
        logger.info("Grading question type=%s, points=%.2f", qtype, points)

        try:
            if qtype == "multiple_choice":
                return self.grade_multiple_choice(str(student_answer), str(correct_answer), points)

            elif qtype == "true_false":
                return self.grade_true_false(str(student_answer), str(correct_answer), points)

            elif qtype == "short_answer":
                return await self.grade_short_answer(str(student_answer), str(correct_answer), points)

            elif qtype in ("essay", "long_answer"):
                rubric = kwargs.get("rubric", {})
                return await self.grade_essay(str(student_answer), rubric, points)

            elif qtype == "fill_blank":
                return await self.grade_fill_blank(str(student_answer), str(correct_answer), points)

            elif qtype == "matching":
                return self.grade_matching(
                    student_answer if isinstance(student_answer, dict) else {},
                    correct_answer if isinstance(correct_answer, dict) else {},
                    points,
                )

            elif qtype == "multiple_response":
                return self.grade_multiple_response(
                    student_answer if isinstance(student_answer, list) else [],
                    correct_answer if isinstance(correct_answer, list) else [],
                    points,
                )

            elif qtype == "ordering":
                return self.grade_ordering(
                    student_answer if isinstance(student_answer, list) else [],
                    correct_answer if isinstance(correct_answer, list) else [],
                    points,
                )

            else:
                return self._result(
                    False, 0.0, points,
                    f"Tipo de pregunta no soportado: '{question_type}'.",
                )

        except Exception as exc:
            logger.exception("Error grading question type=%s: %s", qtype, exc)
            return self._result(
                False, 0.0, points,
                f"Error al calificar: {exc}",
            )


# ── Module-level singleton ───────────────────────────────────

_grading_service: Optional[GradingService] = None


def get_grading_service() -> GradingService:
    global _grading_service
    if _grading_service is None:
        _grading_service = GradingService()
    return _grading_service
