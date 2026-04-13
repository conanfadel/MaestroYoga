"""Muscle groups used by admin training-management UI."""

from __future__ import annotations

TRAINING_MUSCLE_OPTIONS: tuple[dict[str, str], ...] = (
    {"key": "neck", "label": "الرقبة"},
    {"key": "shoulders", "label": "الأكتاف"},
    {"key": "chest", "label": "الصدر"},
    {"key": "back", "label": "الظهر"},
    {"key": "arms", "label": "الذراعان"},
    {"key": "core", "label": "البطن والوسط"},
    {"key": "glutes", "label": "الأرداف"},
    {"key": "quads", "label": "الفخذ الأمامي"},
    {"key": "hamstrings", "label": "الفخذ الخلفي"},
    {"key": "calves", "label": "السمانة"},
    {"key": "mixed", "label": "جميع العضلات (خطة مختلطة)"},
)

TRAINING_MUSCLE_KEY_SET: frozenset[str] = frozenset(row["key"] for row in TRAINING_MUSCLE_OPTIONS)
TRAINING_MUSCLE_LABELS: dict[str, str] = {row["key"]: row["label"] for row in TRAINING_MUSCLE_OPTIONS}

# Keys that may be stored on `TrainingExercise.muscle_key` (excludes UI-only "mixed").
TRAINING_EXERCISE_MUSCLE_KEYS_ORDERED: tuple[str, ...] = tuple(
    row["key"] for row in TRAINING_MUSCLE_OPTIONS if row["key"] != "mixed"
)
TRAINING_EXERCISE_MUSCLE_KEYS: frozenset[str] = frozenset(TRAINING_EXERCISE_MUSCLE_KEYS_ORDERED)
