"""Thin repository facade for Stage 2 learning data. New learning code should import this layer rather than grow database.py."""
from learning import curriculum, diagnostics_learning, exam_results, student_progress, lesson_plans, materials, homework_stats
