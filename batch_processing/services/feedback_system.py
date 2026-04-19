"""
Система обратной связи по результатам определения подсудности.
Запись отзывов пользователей для последующего анализа и улучшения алгоритмов.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FeedbackEntry:
    address: str
    suggested_court: str
    feedback: str  # "correct" | "wrong" | "partial" | произвольный текст
    user_comment: Optional[str] = None


class FeedbackSystem:
    """
    Сбор обратной связи: адрес, выданный суд, оценка пользователя.
    В production можно сохранять в БД (verification_reports в jurisdiction_service).
    """

    def __init__(self, max_entries: int = 10000):
        self._feedback_data: List[Dict[str, Any]] = []
        self._max_entries = max_entries

    def record_feedback(
        self,
        address: str,
        suggested_court: str,
        user_feedback: str,
        user_comment: Optional[str] = None,
    ) -> None:
        self._feedback_data.append({
            "address": address,
            "suggested_court": suggested_court,
            "feedback": user_feedback,
            "user_comment": user_comment,
        })
        if len(self._feedback_data) > self._max_entries:
            self._feedback_data = self._feedback_data[-self._max_entries :]

    def analyze_feedback(self) -> Dict[str, Any]:
        """
        Анализ обратной связи для улучшения алгоритмов.
        Возвращает сводку: количество correct/wrong/partial, примеры ошибок.
        """
        if not self._feedback_data:
            return {"total": 0, "by_feedback": {}, "wrong_examples": []}

        by_feedback: Dict[str, int] = {}
        wrong_examples: List[Dict[str, str]] = []

        for e in self._feedback_data:
            fb = (e.get("feedback") or "").strip().lower() or "unknown"
            by_feedback[fb] = by_feedback.get(fb, 0) + 1
            if fb in ("wrong", "incorrect", "error"):
                wrong_examples.append({
                    "address": e.get("address", ""),
                    "suggested_court": e.get("suggested_court", ""),
                    "comment": e.get("user_comment", ""),
                })
                if len(wrong_examples) > 100:
                    wrong_examples = wrong_examples[-100:]

        return {
            "total": len(self._feedback_data),
            "by_feedback": by_feedback,
            "wrong_examples": wrong_examples[:20],
        }

    def get_all(self) -> List[Dict[str, Any]]:
        """Вернуть все записи (для экспорта)."""
        return list(self._feedback_data)

    def clear(self) -> None:
        self._feedback_data.clear()


_default_feedback: Optional[FeedbackSystem] = None


def get_feedback_system() -> FeedbackSystem:
    global _default_feedback
    if _default_feedback is None:
        _default_feedback = FeedbackSystem()
    return _default_feedback
