"""Reuse the existing repository quiz renderer without importing its cluster helper."""

from ._shared import load_component

CourseQuiz = load_component("quiz").CourseQuiz
