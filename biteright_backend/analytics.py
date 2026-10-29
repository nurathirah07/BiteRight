"""
Scan statistics and achievement badges.

The analytics summary endpoint and the post-scan badge check both use
these helpers, so badge rules live in exactly one place.
"""

from datetime import datetime, timedelta

BADGE_DEFINITIONS = [
    {"id": "first_scan", "name": "First Scan", "icon": "🏁", "description": "Complete first product scan"},
    {"id": "health_guardian", "name": "Health Guardian", "icon": "🛡️", "description": "100% safe products for 7+ days"},
    {"id": "consistent_chooser", "name": "Consistent Chooser", "icon": "📊", "description": "80%+ safe choices over 20+ scans"},
    {"id": "active_scanner", "name": "Active Scanner", "icon": "📈", "description": "30+ scans in a single month"},
    {"id": "quick_learner", "name": "Quick Learner", "icon": "⚡", "description": "20%+ improvement in safe choices"},
    {"id": "label_expert", "name": "Label Expert", "icon": "🏷️", "description": "Scan 10+ different product categories"},
    {"id": "streak_master", "name": "Streak Master", "icon": "🔥", "description": "Scan daily for 7+ consecutive days"},
    {"id": "allergen_aware", "name": "Allergen Aware", "icon": "🎯", "description": "Correctly identify allergens 20+ times"},
    {"id": "super_scanner", "name": "Super Scanner", "icon": "🌟", "description": "Reach 100 total scans"},
    {"id": "weekly_warrior", "name": "Weekly Warrior", "icon": "📅", "description": "Scan at least once every week for 4 weeks"},
    {"id": "improvement_badge", "name": "Improvement Badge", "icon": "💪", "description": "50% reduction in unsafe products"},
    {"id": "ingredient_guru", "name": "Ingredient Guru", "icon": "🧠", "description": "Successfully identify 50+ individual ingredients"},
    {"id": "diverse_scanner", "name": "Diverse Scanner", "icon": "🌈", "description": "Scan products from 5+ different categories"},
    {"id": "completionist", "name": "Completionist", "icon": "🏆", "description": "Collect 10+ badges"},
    {"id": "veteran", "name": "Veteran", "icon": "🎖️", "description": "Use the app for 30+ days"},
]
BADGES_BY_ID = {badge["id"]: badge for badge in BADGE_DEFINITIONS}

USER_BADGES_COLLECTION = 'user_badges'


# ============= TIME HELPERS =============

def to_naive_local(value):
    """Convert aware datetimes to naive local time so comparisons never mix kinds."""
    if value.tzinfo is not None:
        return datetime.fromtimestamp(value.timestamp())
    return value


def parse_datetime(value):
    """Parse a Firestore timestamp, datetime or ISO string. Returns None on failure."""
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            return to_naive_local(value)
        if hasattr(value, 'timestamp'):
            return datetime.fromtimestamp(value.timestamp())
        if isinstance(value, str):
            return to_naive_local(datetime.fromisoformat(value.replace('Z', '+00:00')))
    except (ValueError, TypeError, OverflowError, OSError):
        return None
    return None


def scan_time(scan_data, fallback):
    raw = scan_data.get('scan_date') or scan_data.get('scanned_at') or scan_data.get('timestamp')
    return parse_datetime(raw) or fallback


def product_category(scan_data):
    """Rough category: the last word of the product name (e.g. 'Chocolate Biscuits' -> 'Biscuits')."""
    words = str(scan_data.get('product_name', '')).split()
    if not words or words[0] == 'Unknown' or ' '.join(words) == 'Scanned Product':
        return None
    return words[-1]


# ============= DATA LOADING =============

def load_user_scans(db, collection_name, user_id, now=None):
    """Load a user's scans sorted oldest-first, each with a ``parsed_time``."""
    now = now or datetime.now()
    scans = []
    for doc in db.collection(collection_name).where('user_id', '==', user_id).stream():
        data = doc.to_dict()
        data['id'] = doc.id
        data['parsed_time'] = scan_time(data, now)
        scans.append(data)
    scans.sort(key=lambda s: s['parsed_time'])
    return scans


def load_unlocked_badges(db, user_id):
    unlocked = {}
    for doc in db.collection(USER_BADGES_COLLECTION).where('user_id', '==', user_id).stream():
        data = doc.to_dict()
        if data.get('badge_id'):
            unlocked[data['badge_id']] = data.get('unlocked_at')
    return unlocked


# ============= STATISTICS =============

def window_stats(scans, start_time, end_time=None):
    """Counts and insights for scans in ``[start_time, end_time)``."""
    filtered = [
        s for s in scans
        if s['parsed_time'] >= start_time and (end_time is None or s['parsed_time'] < end_time)
    ]
    total = len(filtered)
    safe = sum(1 for s in filtered if s.get('risk_level') == 'safe')
    unsafe = sum(1 for s in filtered if s.get('risk_level') == 'unsafe')
    caution = sum(1 for s in filtered if s.get('risk_level') == 'caution')

    allergens = {}
    categories = {}
    confidence_sum = 0.0
    for s in filtered:
        try:
            confidence_sum += float(s.get('confidence', 0) or 0)
        except (TypeError, ValueError):
            pass
        for allergen in s.get('allergens_detected', []) or []:
            allergens[allergen] = allergens.get(allergen, 0) + 1
        category = product_category(s)
        if category:
            categories[category] = categories.get(category, 0) + 1

    return {
        'total': total,
        'safe': safe,
        'unsafe': unsafe,
        'caution': caution,
        'safe_pct': (safe / total * 100) if total else 0,
        'top_allergen': max(allergens.items(), key=lambda x: x[1])[0] if allergens else "None",
        'avg_conf': (confidence_sum / total) if total else 0,
        'top_categories': [k for k, _ in sorted(categories.items(), key=lambda i: i[1], reverse=True)[:3]],
        'scans': filtered,
    }


def current_streak(scans, now):
    if not scans:
        return 0
    days = sorted({s['parsed_time'].date() for s in scans}, reverse=True)
    if (now.date() - days[0]).days > 1:
        return 0
    streak = 1
    for previous, current in zip(days, days[1:]):
        if (previous - current).days == 1:
            streak += 1
        else:
            break
    return streak


def compute_stats(scans, now):
    """All aggregate numbers used by badges and the analytics summary."""
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)

    total = len(scans)
    total_safe = sum(1 for s in scans if s.get('risk_level') == 'safe')
    week = window_stats(scans, seven_days_ago)
    month = window_stats(scans, thirty_days_ago)
    prev_month = window_stats(scans, sixty_days_ago, thirty_days_ago)

    categories = {c for c in (product_category(s) for s in scans) if c}
    unique_ingredients = {
        str(ing).lower() for s in scans for ing in (s.get('ingredients') or [])
    }

    weeks_with_scans = set()
    for s in month['scans']:
        days_ago = (now.date() - s['parsed_time'].date()).days
        if 0 <= days_ago < 28:
            weeks_with_scans.add(days_ago // 7)

    improvement = month['safe_pct'] - prev_month['safe_pct']
    prev_total = prev_month['total']
    curr_total = month['total']
    if prev_total > 0:
        scans_increase = (curr_total - prev_total) / prev_total * 100
    else:
        scans_increase = 100 if curr_total > 0 else 0

    return {
        'total': total,
        'total_safe': total_safe,
        'safety_rate': (total_safe / total * 100) if total else 0,
        'allergens_avoided': sum(1 for s in scans if s.get('risk_level') == 'unsafe'),
        'week': week,
        'month': month,
        'prev_month': prev_month,
        'improvement': improvement,
        'scans_increase': scans_increase,
        'trend': "improving" if improvement > 0 else ("stable" if improvement == 0 else "decreasing"),
        'current_streak': current_streak(scans, now),
        'categories': categories,
        'unique_ingredients': unique_ingredients,
        'weeks_with_scans': weeks_with_scans,
        'days_active_span': (scans[-1]['parsed_time'] - scans[0]['parsed_time']).days if scans else 0,
    }


# ============= BADGES =============

def _earned_badge_ids(stats):
    earned = []
    week_scans = stats['week']['scans']
    month = stats['month']
    prev_month = stats['prev_month']

    if stats['total'] > 0:
        earned.append("first_scan")
    if week_scans and all(s.get('risk_level') == 'safe' for s in week_scans):
        earned.append("health_guardian")
    if stats['total'] >= 20 and stats['safety_rate'] >= 80:
        earned.append("consistent_chooser")
    if month['total'] >= 30:
        earned.append("active_scanner")
    if month['total'] > 0 and prev_month['total'] > 0 and stats['improvement'] >= 20:
        earned.append("quick_learner")
    if len(stats['categories']) >= 10:
        earned.append("label_expert")
    if stats['current_streak'] >= 7:
        earned.append("streak_master")
    if stats['allergens_avoided'] >= 20:
        earned.append("allergen_aware")
    if stats['total'] >= 100:
        earned.append("super_scanner")
    if len(stats['weeks_with_scans']) == 4:
        earned.append("weekly_warrior")
    if prev_month['unsafe'] > 0 and month['unsafe'] <= prev_month['unsafe'] * 0.5:
        earned.append("improvement_badge")
    if len(stats['unique_ingredients']) >= 50:
        earned.append("ingredient_guru")
    if len(stats['categories']) >= 5:
        earned.append("diverse_scanner")
    if stats['days_active_span'] >= 30:
        earned.append("veteran")
    return earned


def evaluate_badges(db, user_id, stats, now, unlocked=None):
    """Unlock any newly earned badges and persist them.

    Returns ``(unlocked, newly_unlocked)`` where ``unlocked`` maps every
    unlocked badge id to its timestamp and ``newly_unlocked`` lists the
    badge dicts unlocked by this call.
    """
    unlocked = dict(unlocked if unlocked is not None else load_unlocked_badges(db, user_id))
    timestamp = now.isoformat()
    new_ids = [badge_id for badge_id in _earned_badge_ids(stats) if badge_id not in unlocked]

    if len(unlocked) + len(new_ids) >= 10 and "completionist" not in unlocked and "completionist" not in new_ids:
        new_ids.append("completionist")

    if new_ids:
        batch = db.batch()
        for badge_id in new_ids:
            batch.set(db.collection(USER_BADGES_COLLECTION).document(f"{user_id}_{badge_id}"), {
                'user_id': user_id,
                'badge_id': badge_id,
                'unlocked_at': timestamp,
            })
            unlocked[badge_id] = timestamp
        batch.commit()

    newly = [
        {k: BADGES_BY_ID[badge_id][k] for k in ('id', 'name', 'icon', 'description')}
        for badge_id in new_ids if badge_id in BADGES_BY_ID
    ]
    return unlocked, newly


def badge_list(unlocked, now):
    """Every badge with unlock state. Returns ``(badges, new_count, first_locked)``."""
    result = []
    new_count = 0
    first_locked = None
    for badge in BADGE_DEFINITIONS:
        unlocked_at = unlocked.get(badge['id'])
        is_unlocked = badge['id'] in unlocked
        unlocked_time = parse_datetime(unlocked_at)
        is_new = bool(unlocked_time and (now - unlocked_time).days < 7)
        if is_new:
            new_count += 1
        result.append({
            **badge,
            "is_unlocked": is_unlocked,
            "unlocked_at": unlocked_at if isinstance(unlocked_at, str) or unlocked_at is None else str(unlocked_at),
            "is_new": is_new,
        })
        if not is_unlocked and first_locked is None:
            first_locked = badge
    return result, new_count, first_locked
