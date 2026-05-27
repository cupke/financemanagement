"""Unit-тесты для чистых хелперов из app.api.v1.budgets."""
from datetime import datetime, timezone

from app.api.v1.budgets import _collect_descendants, _month_bounds


def test_month_bounds_january() -> None:
    start, end = _month_bounds(2026, 1)
    assert start == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 2, 1, tzinfo=timezone.utc)


def test_month_bounds_december_rolls_over_year() -> None:
    """Граничный случай: декабрь → январь СЛЕДУЮЩЕГО года, не текущего."""
    start, end = _month_bounds(2026, 12)
    assert start == datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert end == datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_month_bounds_february_non_leap() -> None:
    """Февраль в обычном году — конец = 1 марта (длина 28 дней, но это нас не волнует)."""
    start, end = _month_bounds(2026, 2)
    assert start == datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 3, 1, tzinfo=timezone.utc)


def test_collect_descendants_no_children() -> None:
    """Лист дерева — возвращается только сам узел."""
    assert _collect_descendants(1, children={}) == [1]


def test_collect_descendants_one_level() -> None:
    """Корень + двое прямых детей."""
    children = {1: [2, 3]}
    result = _collect_descendants(1, children)
    assert set(result) == {1, 2, 3}


def test_collect_descendants_deep_tree() -> None:
    """Глубокое дерево: 1 → 2 → 4, 1 → 3 → 5 → 6."""
    children = {1: [2, 3], 2: [4], 3: [5], 5: [6]}
    result = _collect_descendants(1, children)
    assert set(result) == {1, 2, 3, 4, 5, 6}


def test_collect_descendants_subtree_does_not_include_siblings() -> None:
    """Если запросить поддерево из узла 2 — не должны попасть братья (3) или их потомки."""
    children = {1: [2, 3], 2: [4], 3: [5]}
    result = _collect_descendants(2, children)
    assert set(result) == {2, 4}
    assert 3 not in result
    assert 5 not in result
