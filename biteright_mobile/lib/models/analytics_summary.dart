// lib/models/analytics_summary.dart

class AnalyticsBadge {
  final String id;
  final String name;
  final String icon;
  final String description;
  final bool isUnlocked;
  final DateTime? unlockedAt;
  final bool isNew;

  AnalyticsBadge({
    required this.id,
    required this.name,
    required this.icon,
    required this.description,
    required this.isUnlocked,
    this.unlockedAt,
    required this.isNew,
  });

  factory AnalyticsBadge.fromJson(Map<String, dynamic> json) {
    return AnalyticsBadge(
      id: json['id'] ?? '',
      name: json['name'] ?? '',
      icon: json['icon'] ?? '',
      description: json['description'] ?? '',
      isUnlocked: json['is_unlocked'] ?? false,
      unlockedAt: json['unlocked_at'] != null
          ? DateTime.tryParse(json['unlocked_at'])
          : null,
      isNew: json['is_new'] ?? false,
    );
  }
}

class AnalyticsSummary {
  final WeeklyStats weekly;
  final MonthlyStats monthly;
  final int totalScansAllTime;
  final int totalSafeScans;
  final double safetyRate;
  final int currentStreak;
  final int allergensAvoided;
  final List<AnalyticsBadge> badges;
  final int newBadgeCount;
  final String? recommendationTip;
  final NextMilestone? nextMilestone;

  AnalyticsSummary({
    required this.weekly,
    required this.monthly,
    required this.totalScansAllTime,
    required this.totalSafeScans,
    required this.safetyRate,
    required this.currentStreak,
    required this.allergensAvoided,
    required this.badges,
    required this.newBadgeCount,
    this.recommendationTip,
    this.nextMilestone,
  });

  factory AnalyticsSummary.fromJson(Map<String, dynamic> json) {
    return AnalyticsSummary(
      weekly: WeeklyStats.fromJson(json['weekly'] ?? {}),
      monthly: MonthlyStats.fromJson(json['monthly'] ?? {}),
      totalScansAllTime: json['total_scans_all_time'] ?? 0,
      totalSafeScans: json['total_safe_scans'] ?? 0,
      safetyRate: (json['safety_rate'] ?? 0.0).toDouble(),
      currentStreak: json['current_streak'] ?? 0,
      allergensAvoided: json['allergens_avoided'] ?? 0,
      badges: (json['badges'] as List?)
              ?.map((b) => AnalyticsBadge.fromJson(b))
              .toList() ??
          [],
      newBadgeCount: json['new_badge_count'] ?? 0,
      recommendationTip: json['recommendation_tip'],
      nextMilestone: json['next_milestone'] != null
          ? NextMilestone.fromJson(json['next_milestone'])
          : null,
    );
  }
}

class WeeklyStats {
  final int totalScans;
  final int safeCount;
  final int unsafeCount;
  final int cautionCount;
  final double safePercentage;
  final String topAllergen;
  final double avgConfidence;
  final String insightTitle;
  final String insightMessage;
  final List<int> scansByDay;

  WeeklyStats({
    required this.totalScans,
    required this.safeCount,
    required this.unsafeCount,
    required this.cautionCount,
    required this.safePercentage,
    required this.topAllergen,
    required this.avgConfidence,
    required this.insightTitle,
    required this.insightMessage,
    required this.scansByDay,
  });

  factory WeeklyStats.fromJson(Map<String, dynamic> json) {
    return WeeklyStats(
      totalScans: json['total_scans'] ?? 0,
      safeCount: json['safe_count'] ?? 0,
      unsafeCount: json['unsafe_count'] ?? 0,
      cautionCount: json['caution_count'] ?? 0,
      safePercentage: (json['safe_percentage'] ?? 0.0).toDouble(),
      topAllergen: json['top_allergen'] ?? 'None',
      avgConfidence: (json['avg_confidence'] ?? 0.0).toDouble(),
      insightTitle: json['insight_title'] ?? '',
      insightMessage: json['insight_message'] ?? '',
      scansByDay: List<int>.from(json['scans_by_day'] ?? [0, 0, 0, 0, 0, 0, 0]),
    );
  }
}

class MonthlyStats {
  final int totalScans;
  final int safeCount;
  final int unsafeCount;
  final int cautionCount;
  final double safePercentage;
  final double improvement;
  final double scansIncrease;
  final String trend;
  final String insightTitle;
  final String insightMessage;
  final List<int> scansByWeek;
  final List<String> topCategories;

  MonthlyStats({
    required this.totalScans,
    required this.safeCount,
    required this.unsafeCount,
    required this.cautionCount,
    required this.safePercentage,
    required this.improvement,
    required this.scansIncrease,
    required this.trend,
    required this.insightTitle,
    required this.insightMessage,
    required this.scansByWeek,
    required this.topCategories,
  });

  factory MonthlyStats.fromJson(Map<String, dynamic> json) {
    return MonthlyStats(
      totalScans: json['total_scans'] ?? 0,
      safeCount: json['safe_count'] ?? 0,
      unsafeCount: json['unsafe_count'] ?? 0,
      cautionCount: json['caution_count'] ?? 0,
      safePercentage: (json['safe_percentage'] ?? 0.0).toDouble(),
      improvement: (json['improvement'] ?? 0.0).toDouble(),
      scansIncrease: (json['scans_increase'] ?? 0.0).toDouble(),
      trend: json['trend'] ?? 'stable',
      insightTitle: json['insight_title'] ?? '',
      insightMessage: json['insight_message'] ?? '',
      scansByWeek: List<int>.from(json['scans_by_week'] ?? [0, 0, 0, 0]),
      topCategories: List<String>.from(json['top_categories'] ?? []),
    );
  }
}

class NextMilestone {
  final int target;
  final int current;
  final String message;

  NextMilestone({
    required this.target,
    required this.current,
    required this.message,
  });

  factory NextMilestone.fromJson(Map<String, dynamic> json) {
    return NextMilestone(
      target: json['target'] ?? 0,
      current: json['current'] ?? 0,
      message: json['message'] ?? '',
    );
  }
}
