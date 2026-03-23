"""
Tests for standalone sequential grouping functions and detect_name_in_text.
"""

import os
import asyncio
from unittest.mock import AsyncMock, MagicMock

# Ensure minimal env vars so Settings can load
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake-key")
os.environ.setdefault("DATABASE_URL", "postgresql://fake")
os.environ.setdefault("ANTHROPIC_API_KEY", "fake-anthropic-key")
os.environ.setdefault("OPENAI_API_KEY", "fake-openai-key")
os.environ.setdefault("JWT_SECRET", "fake-jwt-secret")

from app.services.grouping_service import (
    detect_name_in_text,
    group_photos_by_student_sequential,
)


def test_detect_name_in_text():
    """Test detect_name_in_text with various patterns."""
    passed = 0
    total = 0

    cases = [
        ("Name: Camila Rodriguez", "Camila Rodriguez"),
        ("Nombre: Juan Perez Garcia", "Juan Perez Garcia"),
        ("Student: Maria Lopez", "Maria Lopez"),
        ("Alumno: Carlos Mendez", "Carlos Mendez"),
        ("Estudiante: Ana Torres", "Ana Torres"),
        ("Q1: B\nQ2: A", None),              # No name
        ("Some random text", None),           # No name
        ("Name: Jo", None),                   # Too short
        ("Name: A", None),                    # Too short
    ]

    for text, expected in cases:
        total += 1
        result = detect_name_in_text(text)
        status = "PASS" if result == expected else "FAIL"
        if result == expected:
            passed += 1
        print(f"  {status}: detect_name_in_text({text!r}) = {result!r} (expected {expected!r})")

    print(f"\ndetect_name_in_text: {passed}/{total} passed")
    return passed == total


def test_sequential_grouping():
    """Test group_photos_by_student_sequential with mocked services."""
    passed = 0
    total = 0

    # Mock OCR service
    mock_ocr = MagicMock()
    mock_storage = MagicMock()
    mock_storage.download_to_temp = AsyncMock(side_effect=[
        "/tmp/fake1.jpg", "/tmp/fake2.jpg", "/tmp/fake3.jpg", "/tmp/fake4.jpg"
    ])

    # Simulate: Camila page1 (has name), Camila page2 (no name), Juan page1 (has name), Juan page2 (no name)
    mock_ocr.extract_text = AsyncMock(side_effect=[
        "Name: Camila Rodriguez\nQ1: B\nQ2: A",
        "Q3: C\nQ4: D",
        "Nombre: Juan Perez\nQ1: A\nQ2: B",
        "Q3: D\nQ4: C",
    ])

    # Patch os.path.exists and os.unlink so cleanup doesn't fail
    original_exists = os.path.exists
    original_unlink = os.unlink
    os.path.exists = lambda p: False
    os.unlink = lambda p: None

    try:
        groups = asyncio.run(group_photos_by_student_sequential(
            photo_urls=["url1", "url2", "url3", "url4"],
            ocr_service=mock_ocr,
            storage_service=mock_storage,
        ))

        # Test 1: Should have 2 groups
        total += 1
        if len(groups) == 2:
            passed += 1
            print("  PASS: 2 student groups created")
        else:
            print(f"  FAIL: Expected 2 groups, got {len(groups)}")

        # Test 2: First group is Camila with 2 photos
        total += 1
        if groups[0]["student_name"] == "Camila Rodriguez" and groups[0]["page_count"] == 2:
            passed += 1
            print(f"  PASS: Camila Rodriguez has 2 pages")
        else:
            print(f"  FAIL: First group = {groups[0]}")

        # Test 3: Second group is Juan with 2 photos
        total += 1
        if groups[1]["student_name"] == "Juan Perez" and groups[1]["page_count"] == 2:
            passed += 1
            print(f"  PASS: Juan Perez has 2 pages")
        else:
            print(f"  FAIL: Second group = {groups[1]}")

        # Test 4: Photo URLs are correct
        total += 1
        if groups[0]["photo_urls"] == ["url1", "url2"] and groups[1]["photo_urls"] == ["url3", "url4"]:
            passed += 1
            print("  PASS: Photo URLs correctly assigned")
        else:
            print(f"  FAIL: URLs wrong: {[g['photo_urls'] for g in groups]}")

    finally:
        os.path.exists = original_exists
        os.unlink = original_unlink

    print(f"\nsequential_grouping: {passed}/{total} passed")
    return passed == total


def test_first_photo_no_name():
    """Test that first photo without name creates Unknown_Student."""
    mock_ocr = MagicMock()
    mock_storage = MagicMock()
    mock_storage.download_to_temp = AsyncMock(return_value="/tmp/fake.jpg")
    mock_ocr.extract_text = AsyncMock(return_value="Q1: B\nQ2: A")

    original_exists = os.path.exists
    original_unlink = os.unlink
    os.path.exists = lambda p: False
    os.unlink = lambda p: None

    try:
        groups = asyncio.run(group_photos_by_student_sequential(
            photo_urls=["url1"],
            ocr_service=mock_ocr,
            storage_service=mock_storage,
        ))

        if len(groups) == 1 and groups[0]["student_name"].startswith("Unknown_Student"):
            print("  PASS: First photo with no name creates Unknown_Student")
            return True
        else:
            print(f"  FAIL: Expected Unknown_Student, got {groups}")
            return False
    finally:
        os.path.exists = original_exists
        os.unlink = original_unlink


if __name__ == "__main__":
    print("=" * 60)
    print("TEST 1: detect_name_in_text")
    print("=" * 60)
    r1 = test_detect_name_in_text()

    print("\n" + "=" * 60)
    print("TEST 2: Sequential grouping (2 students, 2 pages each)")
    print("=" * 60)
    r2 = test_sequential_grouping()

    print("\n" + "=" * 60)
    print("TEST 3: First photo with no name")
    print("=" * 60)
    r3 = test_first_photo_no_name()

    print("\n" + "=" * 60)
    all_pass = r1 and r2 and r3
    if all_pass:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)
