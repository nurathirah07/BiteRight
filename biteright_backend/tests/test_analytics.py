"""Unit tests for analytics.py (scan statistics and badge unlocking).

Run with:
    cd biteright_backend
    python -m pytest tests/test_analytics.py -v
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analytics

NOW = datetime(2026, 10, 29, 12, 0, 0)


def _scan(days_ago, risk='safe', name='Chocolate Biscuits', ingredients=('sugar',), allergens=()):
    return {
        'parsed_time': NOW - timedelta(days=days_ago),
        'risk_level': risk,
        'product_name': name,
        'ingredients': list(ingredients),
        'allergens_detected': list(allergens),
        'confidence': 0.9,
    }


class _FakeBatch:
    def __init__(self, store):
        self.store = store
        self.pending = []

    def set(self, ref, data):
        self.pending.append((ref, data))

    def commit(self):
        for ref, data in self.pending:
            self.store[ref] = data
        self.pending = []


class _FakeCollection:
    def __init__(self, name):
        self.name = name

    def document(self, doc_id):
        return f"{self.name}/{doc_id}"


class _FakeDb:
    def __init__(self):
        self.store = {}

    def batch(self):
        return _FakeBatch(self.store)

    def collection(self, name):
        return _FakeCollection(name)


class TestParseDatetime:
    def test_aware_and_naive_values_become_comparable(self):
        aware = analytics.parse_datetime('2026-10-01T10:00:00Z')
        naive = analytics.parse_datetime('2026-10-01T10:00:00')
        assert aware.tzinfo is None and naive.tzinfo is None
        assert (aware - naive) is not None  # would raise TypeError if kinds were mixed

    def test_datetime_objects(self):
        value = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert analytics.parse_datetime(value).tzinfo is None

    def test_garbage_returns_none(self):
        assert analytics.parse_datetime('not a date') is None
        assert analytics.parse_datetime(None) is None


class TestStats:
    def test_streak_counts_consecutive_days(self):
        scans = [_scan(0), _scan(1), _scan(2), _scan(4)]
        assert analytics.current_streak(scans, NOW) == 3

    def test_streak_is_zero_when_last_scan_is_old(self):
        assert analytics.current_streak([_scan(3)], NOW) == 0

    def test_window_and_totals(self):
        scans = sorted([_scan(1), _scan(2, 'unsafe', allergens=['Milk']), _scan(40)],
                       key=lambda s: s['parsed_time'])
        stats = analytics.compute_stats(scans, NOW)
        assert stats['total'] == 3
        assert stats['week']['total'] == 2
        assert stats['week']['unsafe'] == 1
        assert stats['week']['top_allergen'] == 'Milk'
        assert stats['prev_month']['total'] == 1
        assert stats['allergens_avoided'] == 1

    def test_unnamed_scans_are_not_a_category(self):
        assert analytics.product_category({'product_name': 'Scanned Product'}) is None
        assert analytics.product_category({'product_name': 'Oat Milk'}) == 'Milk'


class TestBadges:
    def test_first_scan_unlocks_and_is_persisted_once(self):
        db = _FakeDb()
        stats = analytics.compute_stats([_scan(0)], NOW)

        unlocked, newly = analytics.evaluate_badges(db, 'u1', stats, NOW, unlocked={})
        new_ids = {b['id'] for b in newly}
        assert 'first_scan' in new_ids
        assert 'health_guardian' in new_ids
        assert 'user_badges/u1_first_scan' in db.store

        _, newly_again = analytics.evaluate_badges(db, 'u1', stats, NOW, unlocked=unlocked)
        assert newly_again == []

    def test_badge_list_marks_recent_unlocks_as_new(self):
        unlocked = {'first_scan': (NOW - timedelta(days=1)).isoformat(),
                    'veteran': (NOW - timedelta(days=30)).isoformat()}
        badges, new_count, first_locked = analytics.badge_list(unlocked, NOW)
        assert len(badges) == len(analytics.BADGE_DEFINITIONS)
        assert new_count == 1
        assert first_locked['id'] == 'health_guardian'
