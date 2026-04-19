"""
Ссылки на статьи ГПК РФ для определения подсудности.
Используется в jurisdiction, court_details, court_matcher.
"""
# Общая подсудность (ст. 28 ГПК РФ) — по месту жительства ответчика
GPK_ARTICLE_28 = "ст. 28 ГПК РФ"

# Исключительная подсудность (ст. 30 ГПК РФ) — иски о правах на недвижимость,
# наследование недвижимости и др. рассматриваются судом по месту нахождения объекта
GPK_ARTICLE_30 = "ст. 30 ГПК РФ"

# Типы дел, подпадающих под ст. 30 ГПК РФ (для будущего расширения)
EXCLUSIVE_JURISDICTION_CASE_TYPES = frozenset([
    "недвижимость",
    "права на недвижимость",
    "наследование недвижимости",
    "иск о правах на земельный участок",
])


def get_gpk_article(case_type: str = None, is_exclusive: bool = False) -> str:
    """
    Возвращает ссылку на статью ГПК РФ в зависимости от типа дела.
    :param case_type: тип дела (опционально)
    :param is_exclusive: признак исключительной подсудности (ст. 30)
    """
    if is_exclusive or (case_type and any(
        k in (case_type or "").lower() for k in EXCLUSIVE_JURISDICTION_CASE_TYPES
    )):
        return GPK_ARTICLE_30
    return GPK_ARTICLE_28
