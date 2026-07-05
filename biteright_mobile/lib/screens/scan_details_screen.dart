// lib/screens/scan_details_screen.dart
import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';

class ScanDetailsScreen extends StatefulWidget {
  final String userId;
  final String scanId;
  final Map<String, dynamic> scanData;

  const ScanDetailsScreen({
    super.key,
    required this.userId,
    required this.scanId,
    required this.scanData,
  });

  @override
  State<ScanDetailsScreen> createState() => _ScanDetailsScreenState();
}

class _ScanDetailsScreenState extends State<ScanDetailsScreen> {
  late Map<String, dynamic> _scanData;
  late int _calculatedRiskScore;
  late double _calculatedConfidence;
  late String _calculatedRiskLevel;

  @override
  void initState() {
    super.initState();
    _scanData = ApiService().normalizeScanAnalysis(Map.from(widget.scanData));
    _calculateMetrics();
    _fetchProfileAndCalculate();
  }

  Future<void> _fetchProfileAndCalculate() async {
    try {
      if (widget.userId.isNotEmpty) {
        final profile = await ApiService().getUserProfile(widget.userId);
        if (profile != null && profile['profile'] != null) {
          final Map<String, dynamic> profileData = Map<String, dynamic>.from(profile['profile'] as Map);
          final allergies = profileData['allergies'] ?? [];
          final dietary = profileData['dietary_restrictions'] ?? [];
          
          if (mounted) {
            setState(() {
              _scanData['user_allergies'] = allergies;
              _scanData['dietary_issues'] = dietary;
              _calculateMetrics(forceRecalculate: false);
            });
            return;
          }
        }
      }
    } catch (e) {
      debugPrint('Error loading user profile: $e');
    }
    
    if (mounted) {
      setState(() {
        _calculateMetrics();
      });
    }
  }

  // ─── Risk Score & Confidence Calculation ─────────────────────────────────

  void _calculateMetrics({bool forceRecalculate = false}) {
    final storedRiskLevel = _scanData['risk_level']?.toString();
    final storedRiskScore = _asInt(_scanData['risk_score']);
    final storedConfidence = _asConfidence(_scanData['confidence']);
    if (!forceRecalculate &&
        storedRiskLevel != null &&
        storedRiskLevel.isNotEmpty &&
        storedRiskLevel != 'unknown') {
      _calculatedRiskLevel = storedRiskLevel;
      _calculatedRiskScore = _normalizeDisplayRiskScore(
        storedRiskLevel,
        storedRiskScore,
      );
      _calculatedConfidence = storedConfidence > 0
          ? storedConfidence
          : _calculateConfidence(
              ingredients: List<String>.from(_scanData['ingredients'] ?? []),
              wasEdited: _scanData['was_edited'] ?? false,
              hasProductName:
                  (_scanData['product_name'] ?? '').toString().isNotEmpty,
              allergensFoundCount: List<String>.from(_scanData['alerts'] ?? [])
                  .where((a) => a.toLowerCase().contains('matches your'))
                  .length,
            );
      _scanData['risk_level'] = _calculatedRiskLevel;
      _scanData['risk_score'] = _calculatedRiskScore;
      _scanData['confidence'] = _calculatedConfidence;
      return;
    }

    // Get data from scan
    final allergensFound =
        List<dynamic>.from(_scanData['allergens_found'] ?? []);
    final userAllergies = List<dynamic>.from(_scanData['user_allergies'] ?? []);
    final dietaryIssues = List<dynamic>.from(_scanData['dietary_issues'] ?? []);
    final ingredients = List<String>.from(_scanData['ingredients'] ?? []);
    final alerts = List<String>.from(_scanData['alerts'] ?? []);
    final wasEdited = _scanData['was_edited'] ?? false;
    final hasProductName =
        (_scanData['product_name'] ?? '').toString().isNotEmpty;

    // CRITICAL FIX: Parse alerts to find allergens that weren't in allergens_found array
    final List<String> extractedAllergensFromAlerts = [];

    for (var alert in alerts) {
      final alertLower = alert.toLowerCase();
      // Check for "matches your X allergy" pattern
      if (alertLower.contains('matches your')) {
        extractedAllergensFromAlerts.add(alert);
      }
    }

    // Calculate Risk Score (0-100) - START WITH ALERTS CHECK FIRST
    _calculatedRiskScore = _calculateRiskScore(
      allergensFound: allergensFound,
      userAllergies: userAllergies,
      dietaryIssues: dietaryIssues,
      alerts: alerts,
      extractedAllergensFromAlerts: extractedAllergensFromAlerts,
    );

    // Calculate Confidence Score (0-100%)
    _calculatedConfidence = _calculateConfidence(
      ingredients: ingredients,
      wasEdited: wasEdited,
      hasProductName: hasProductName,
      allergensFoundCount:
          allergensFound.length + extractedAllergensFromAlerts.length,
    );

    // Determine risk level based on score AND alerts
    _calculatedRiskLevel = _determineRiskLevel(_calculatedRiskScore, alerts);

    // Update scan data with calculated values
    _scanData['risk_score'] = _calculatedRiskScore;
    _scanData['confidence'] = _calculatedConfidence;
    _scanData['risk_level'] = _calculatedRiskLevel;
  }

  int _asInt(dynamic value) {
    if (value is int) return value;
    if (value is double) return value.round();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  double _asConfidence(dynamic value) {
    if (value is num) {
      return value > 1 ? (value / 100).clamp(0.0, 1.0) : value.toDouble();
    }
    final parsed = double.tryParse(value?.toString() ?? '') ?? 0.0;
    return parsed > 1 ? (parsed / 100).clamp(0.0, 1.0) : parsed;
  }

  int _normalizeDisplayRiskScore(String riskLevel, int score) {
    // Return score as-is since it has already been converted to Risk Score format.
    return score;
  }

  int _calculateRiskScore({
    required List<dynamic> allergensFound,
    required List<dynamic> userAllergies,
    required List<dynamic> dietaryIssues,
    required List<String> alerts,
    required List<String> extractedAllergensFromAlerts,
  }) {
    // Start with 0 (safest)
    int riskScore = 0;

    // Severity weights for risk
    final Map<String, int> severityScores = {
      'high': 35,
      'medium': 20,
      'low': 10,
    };

    // Create a map of user allergies with their severity
    final Map<String, String> userAllergySeverity = {};
    for (var allergy in userAllergies) {
      if (allergy is Map) {
        final id = allergy['id']?.toString() ?? '';
        final severity = allergy['severity']?.toString() ?? 'medium';
        if (id.isNotEmpty) {
          userAllergySeverity[id] = severity;
        }
      } else {
        userAllergySeverity[allergy.toString()] = 'medium';
      }
    }

    // ADD RISK FOR ALLERGENS FROM ALERTS (CRITICAL FIX)
    // Each "matches your" alert is a direct allergen match
    if (extractedAllergensFromAlerts.isNotEmpty) {
      // Severe risk for direct allergen matches in alerts
      int alertRisk = extractedAllergensFromAlerts.length * 30;
      riskScore += alertRisk;
    }

    // Check alerts for "may violate" patterns (dietary issues)
    for (var alert in alerts) {
      if (alert.toLowerCase().contains('may violate')) {
        riskScore += 15;
      }
    }

    // Add risk points for each allergen found in allergens_found array
    for (var allergen in allergensFound) {
      String allergenId;
      String severity = 'medium';

      if (allergen is Map) {
        allergenId = allergen['id']?.toString() ?? '';
        if (userAllergySeverity.containsKey(allergenId)) {
          severity = userAllergySeverity[allergenId] ?? 'medium';
        } else {
          severity = allergen['severity']?.toString() ?? 'medium';
        }
      } else {
        allergenId = allergen.toString();
        if (userAllergySeverity.containsKey(allergenId)) {
          severity = userAllergySeverity[allergenId] ?? 'medium';
        }
      }

      int addition = severityScores[severity] ?? 20;
      riskScore += addition;
    }

    // Add risk points for dietary issues
    int dietaryRisk = dietaryIssues.length * 15;
    riskScore += dietaryRisk > 50 ? 50 : dietaryRisk;

    // Ensure score stays within 0-100 range
    return riskScore.clamp(0, 100);
  }

  double _calculateConfidence({
    required List<String> ingredients,
    required bool wasEdited,
    required bool hasProductName,
    required int allergensFoundCount,
  }) {
    double confidence = 0.70; // Base confidence (70%)

    // Increase confidence if user manually edited ingredients
    if (wasEdited) {
      confidence += 0.15;
    }

    // Increase confidence if product name is available
    if (hasProductName) {
      confidence += 0.05;
    }

    // Increase confidence if enough ingredients were extracted
    if (ingredients.length >= 5) {
      confidence += 0.05;
    } else if (ingredients.length >= 3) {
      confidence += 0.03;
    } else if (ingredients.length < 2) {
      confidence -= 0.10; // Penalize for too few ingredients
    }

    // Small boost if allergens were detected (system is working)
    if (allergensFoundCount > 0) {
      confidence += 0.05;
    }

    // Cap confidence at 0.95 (95%)
    return confidence > 0.95 ? 0.95 : confidence;
  }

  String _determineRiskLevel(int riskScore, List<String> alerts) {
    // FIRST: Check if there are any direct allergen matches in alerts
    for (var alert in alerts) {
      if (alert.toLowerCase().contains('matches your')) {
        return 'unsafe';
      }
    }

    // SECOND: Check score-based determination
    if (riskScore <= 25) {
      return 'safe';
    } else if (riskScore <= 59) {
      return 'caution';
    } else {
      return 'unsafe';
    }
  }

  // ─── Helpers ────────────────────────────────────────────────────────────────

  Color _riskColor(String riskLevel) {
    switch (riskLevel) {
      case 'safe':
        return AppTheme.safe;
      case 'caution':
        return AppTheme.caution;
      case 'unsafe':
        return AppTheme.unsafe;
      default:
        return Colors.grey;
    }
  }

  Color _riskBgColor(String riskLevel) {
    switch (riskLevel) {
      case 'safe':
        return const Color(0xFFE9F5EE);
      case 'caution':
        return const Color(0xFFFEF7E6);
      case 'unsafe':
        return const Color(0xFFFDECEA);
      default:
        return Colors.grey.shade100;
    }
  }

  Color _riskBorderColor(String riskLevel) {
    switch (riskLevel) {
      case 'safe':
        return const Color(0xFF7EC8A0);
      case 'caution':
        return const Color(0xFFF5C857);
      case 'unsafe':
        return const Color(0xFFE57A75);
      default:
        return Colors.grey.shade300;
    }
  }

  Color _riskIconBg(String riskLevel) {
    switch (riskLevel) {
      case 'safe':
        return const Color(0xFF1D9E75);
      case 'caution':
        return const Color(0xFFBA7517);
      case 'unsafe':
        return const Color(0xFFD84040);
      default:
        return Colors.grey;
    }
  }

  Color _riskMetricBg(String riskLevel) {
    switch (riskLevel) {
      case 'safe':
        return const Color(0xFF1D9E75).withValues(alpha: 0.12);
      case 'caution':
        return const Color(0xFFBA7517).withValues(alpha: 0.12);
      case 'unsafe':
        return const Color(0xFFD84040).withValues(alpha: 0.12);
      default:
        return Colors.grey.withValues(alpha: 0.12);
    }
  }

  Color _riskLabelColor(String riskLevel) {
    switch (riskLevel) {
      case 'safe':
        return const Color(0xFF0F6E56);
      case 'caution':
        return const Color(0xFF854F0B);
      case 'unsafe':
        return const Color(0xFFA32D2D);
      default:
        return Colors.grey.shade700;
    }
  }

  Color _riskValueColor(String riskLevel) {
    switch (riskLevel) {
      case 'safe':
        return const Color(0xFF085041);
      case 'caution':
        return const Color(0xFF633806);
      case 'unsafe':
        return const Color(0xFF791F1F);
      default:
        return Colors.grey.shade800;
    }
  }

  IconData _riskIcon(String riskLevel) {
    switch (riskLevel) {
      case 'safe':
        return Icons.check_circle_outline_rounded;
      case 'caution':
        return Icons.warning_amber_rounded;
      case 'unsafe':
        return Icons.dangerous_rounded;
      default:
        return Icons.help_outline_rounded;
    }
  }

  String _riskHeadline(String riskLevel) {
    switch (riskLevel) {
      case 'safe':
        return 'Recommended for you';
      case 'caution':
        return 'Use with caution';
      case 'unsafe':
        return 'Not recommended for you';
      default:
        return 'Unable to assess';
    }
  }

  String _getRiskScoreDescription(int score) {
    if (score <= 25) {
      return 'Low Risk - Safe to consume';
    } else if (score <= 40) {
      return 'Mild Risk - Minor concerns';
    } else if (score <= 59) {
      return 'Moderate Risk - Exercise caution';
    } else if (score <= 80) {
      return 'High Risk - Not recommended';
    } else {
      return 'Severe Risk - Avoid completely';
    }
  }

  String _getConfidenceDescription(double confidence) {
    int percent = (confidence * 100).toInt();
    if (percent >= 80) {
      return 'High - Analysis is reliable';
    } else if (percent >= 60) {
      return 'Medium - Double-check details';
    } else {
      return 'Low - Review ingredients list';
    }
  }

  // Badge colors per ingredient status
  Color _badgeBg(String status) {
    switch (status) {
      case 'safe':
        return const Color(0xFFE9F5EE);
      case 'caution':
        return const Color(0xFFFEF7E6);
      case 'unsafe':
        return const Color(0xFFFDECEA);
      default:
        return Colors.grey.shade100;
    }
  }

  Color _badgeText(String status) {
    switch (status) {
      case 'safe':
        return const Color(0xFF0F6E56);
      case 'caution':
        return const Color(0xFF854F0B);
      case 'unsafe':
        return const Color(0xFFA32D2D);
      default:
        return Colors.grey.shade700;
    }
  }

  Color _ingredientNameColor(String status) {
    switch (status) {
      case 'caution':
        return const Color(0xFF854F0B);
      case 'unsafe':
        return const Color(0xFFA32D2D);
      default:
        return const Color(0xFF1A1814);
    }
  }

  // ─── Build ──────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final riskLevel = _calculatedRiskLevel;
    final riskScore = _calculatedRiskScore;
    final confidence = _calculatedConfidence;
    final alerts = List<String>.from(_scanData['alerts'] ?? []);
    final ingredients = List<String>.from(_scanData['ingredients'] ?? []);
    final ingredientDetails = List<Map<String, dynamic>>.from(
      _scanData['ingredient_details'] ?? [],
    );
    final recommendations =
        List<String>.from(_scanData['recommendations'] ?? []);
    final productName = _scanData['product_name'] ?? 'Unknown Product';
    final scannedAt = _scanData['scanned_at'] != null
        ? DateTime.parse(_scanData['scanned_at'] as String).toLocal()
        : DateTime.now();

    final riskFraction = (riskScore.toDouble() / 100).clamp(0.0, 1.0);

    return Scaffold(
      backgroundColor: const Color(0xFFF7F4F0),
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        surfaceTintColor: Colors.transparent,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text(
          'Analysis result',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Risk Hero Card ──────────────────────────────────────────────
            _RiskHeroCard(
              riskLevel: riskLevel,
              riskScore: riskScore,
              confidence: confidence,
              riskFraction: riskFraction,
              riskBgColor: _riskBgColor(riskLevel),
              riskBorderColor: _riskBorderColor(riskLevel),
              riskIconBg: _riskIconBg(riskLevel),
              riskColor: _riskColor(riskLevel),
              riskLabelColor: _riskLabelColor(riskLevel),
              riskValueColor: _riskValueColor(riskLevel),
              riskMetricBg: _riskMetricBg(riskLevel),
              riskIcon: _riskIcon(riskLevel),
              riskHeadline: _riskHeadline(riskLevel),
              riskScoreDescription: _getRiskScoreDescription(riskScore),
              confidenceDescription: _getConfidenceDescription(confidence),
            ),

            const SizedBox(height: 12),

            // ── Product Info Card ───────────────────────────────────────────
            _SectionCard(
              headerIcon: Icons.receipt_long_rounded,
              headerTitle: 'Product information',
              children: [
                _InfoRow(
                  icon: Icons.local_grocery_store_outlined,
                  label: 'Product name',
                  value: productName,
                ),
                _InfoRow(
                  icon: Icons.access_time_rounded,
                  label: 'Scanned at',
                  value:
                      '${scannedAt.day} / ${scannedAt.month} / ${scannedAt.year}  '
                      '${scannedAt.hour}:${scannedAt.minute.toString().padLeft(2, '0')}',
                  isLast: true,
                ),
              ],
            ),

            // ── Alerts ──────────────────────────────────────────────────────
            if (alerts.isNotEmpty) ...[
              const SizedBox(height: 12),
              _AlertsBanner(alerts: alerts),
            ],

            const SizedBox(height: 16),

            // ── Ingredient Breakdown ────────────────────────────────────────
            _SectionLabel(
              label: 'Ingredient breakdown',
              trailing: ingredientDetails.isNotEmpty
                  ? '${ingredientDetails.length} detected'
                  : ingredients.isNotEmpty
                      ? '${ingredients.length} detected'
                      : null,
            ),
            const SizedBox(height: 8),
            _SectionCard(
              headerIcon: Icons.science_outlined,
              headerTitle: ingredientDetails.isNotEmpty
                  ? '${ingredientDetails.length} ingredients detected'
                  : 'Ingredients',
              children: [
                if (ingredientDetails.isNotEmpty)
                  ...List.generate(ingredientDetails.length, (i) {
                    final detail = ingredientDetails[i];
                    final name = detail['ingredient']?.toString() ?? 'Unknown';
                    final status = detail['status']?.toString() ?? 'safe';
                    final reasons = List<String>.from(detail['reasons'] ?? []);
                    return _IngredientRow(
                      name: name,
                      status: status,
                      reasons: reasons,
                      nameColor: _ingredientNameColor(status),
                      badgeBg: _badgeBg(status),
                      badgeText: _badgeText(status),
                      isLast: i == ingredientDetails.length - 1,
                    );
                  })
                else
                  ...List.generate(ingredients.length, (i) {
                    return _IngredientRow(
                      name: ingredients[i],
                      status: 'safe',
                      reasons: const [],
                      nameColor: const Color(0xFF1A1814),
                      badgeBg: _badgeBg('safe'),
                      badgeText: _badgeText('safe'),
                      isLast: i == ingredients.length - 1,
                    );
                  }),
              ],
            ),

            // ── Recommendations ─────────────────────────────────────────────
            if (recommendations.isNotEmpty) ...[
              const SizedBox(height: 16),
              const _SectionLabel(label: 'Safety recommendations'),
              const SizedBox(height: 8),
              _SectionCard(
                headerIcon: Icons.tips_and_updates_outlined,
                headerTitle: 'What to keep in mind',
                children: List.generate(recommendations.length, (i) {
                  return _RecommendationRow(
                    text: recommendations[i],
                    isLast: i == recommendations.length - 1,
                  );
                }),
              ),
            ],

            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }
}

// ─── Risk Hero Card ────────────────────────────────────────────────────────────

class _RiskHeroCard extends StatelessWidget {
  final String riskLevel;
  final int riskScore;
  final double confidence;
  final double riskFraction;
  final Color riskBgColor;
  final Color riskBorderColor;
  final Color riskIconBg;
  final Color riskColor;
  final Color riskLabelColor;
  final Color riskValueColor;
  final Color riskMetricBg;
  final IconData riskIcon;
  final String riskHeadline;
  final String riskScoreDescription;
  final String confidenceDescription;

  const _RiskHeroCard({
    required this.riskLevel,
    required this.riskScore,
    required this.confidence,
    required this.riskFraction,
    required this.riskBgColor,
    required this.riskBorderColor,
    required this.riskIconBg,
    required this.riskColor,
    required this.riskLabelColor,
    required this.riskValueColor,
    required this.riskMetricBg,
    required this.riskIcon,
    required this.riskHeadline,
    required this.riskScoreDescription,
    required this.confidenceDescription,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: riskBgColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: riskBorderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Icon + headline
          Row(
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: riskIconBg,
                  shape: BoxShape.circle,
                ),
                child: Icon(riskIcon, color: Colors.white, size: 22),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      riskHeadline,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: riskLabelColor,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'Overall product assessment',
                      style: TextStyle(
                        fontSize: 11,
                        color: riskColor.withValues(alpha: 0.75),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: 14),

          // Three metric pills
          Row(
            children: [
              Expanded(
                child: _MetricPill(
                  label: 'Risk level',
                  value: riskLevel[0].toUpperCase() + riskLevel.substring(1),
                  description: riskScoreDescription,
                  bg: riskMetricBg,
                  labelColor: riskLabelColor,
                  valueColor: riskValueColor,
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _MetricPill(
                  label: 'Risk score',
                  value: '$riskScore/100',
                  description: riskScoreDescription,
                  bg: riskMetricBg,
                  labelColor: riskLabelColor,
                  valueColor: riskValueColor,
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _MetricPill(
                  label: 'Confidence',
                  value: confidence > 0
                      ? '${(confidence * 100).toStringAsFixed(0)}%'
                      : 'N/A',
                  description: confidenceDescription,
                  bg: riskMetricBg,
                  labelColor: riskLabelColor,
                  valueColor: riskValueColor,
                ),
              ),
            ],
          ),

          const SizedBox(height: 10),

          // Score bar
          ClipRRect(
            borderRadius: BorderRadius.circular(99),
            child: LinearProgressIndicator(
              value: riskFraction,
              minHeight: 6,
              backgroundColor: riskColor.withValues(alpha: 0.18),
              valueColor: AlwaysStoppedAnimation<Color>(riskIconBg),
            ),
          ),
        ],
      ),
    );
  }
}

class _MetricPill extends StatelessWidget {
  final String label;
  final String value;
  final String description;
  final Color bg;
  final Color labelColor;
  final Color valueColor;

  const _MetricPill({
    required this.label,
    required this.value,
    required this.description,
    required this.bg,
    required this.labelColor,
    required this.valueColor,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label.toUpperCase(),
            style: TextStyle(
              fontSize: 9,
              fontWeight: FontWeight.w500,
              letterSpacing: 0.5,
              color: labelColor,
            ),
          ),
          const SizedBox(height: 3),
          Text(
            value,
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: valueColor,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            description,
            style: const TextStyle(
              fontSize: 8,
              color: Color(0xFF9A9790),
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}

// ─── Section Card ──────────────────────────────────────────────────────────────

class _SectionCard extends StatelessWidget {
  final IconData headerIcon;
  final String headerTitle;
  final List<Widget> children;

  const _SectionCard({
    required this.headerIcon,
    required this.headerTitle,
    required this.children,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
            child: Row(
              children: [
                Icon(headerIcon, size: 16, color: const Color(0xFF9A9790)),
                const SizedBox(width: 8),
                Text(
                  headerTitle,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF1A1814),
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1, thickness: 0.5, color: Color(0x0F000000)),
          ...children,
        ],
      ),
    );
  }
}

// ─── Info Row ──────────────────────────────────────────────────────────────────

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final bool isLast;

  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
    this.isLast = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        border: isLast
            ? null
            : const Border(
                bottom: BorderSide(color: Color(0x0A000000)),
              ),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 15, color: const Color(0xFF9A9790)),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: const TextStyle(
                    fontSize: 10,
                    color: Color(0xFF9A9790),
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  value,
                  style: const TextStyle(
                    fontSize: 13,
                    color: Color(0xFF1A1814),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Alerts Banner ─────────────────────────────────────────────────────────────

class _AlertsBanner extends StatelessWidget {
  final List<String> alerts;

  const _AlertsBanner({required this.alerts});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFDECEA),
        borderRadius: BorderRadius.circular(12),
        border: const Border(
          left: BorderSide(color: Color(0xFFD84040), width: 3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.warning_amber_rounded,
                  size: 16, color: Color(0xFFA32D2D)),
              SizedBox(width: 6),
              Text(
                'Alerts',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFFA32D2D),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          ...alerts.map(
            (alert) => Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Padding(
                    padding: EdgeInsets.only(top: 5),
                    child: CircleAvatar(
                      radius: 3,
                      backgroundColor: Color(0xFFD84040),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      alert,
                      style: const TextStyle(
                        fontSize: 12,
                        color: Color(0xFF791F1F),
                        height: 1.4,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Ingredient Row ────────────────────────────────────────────────────────────

class _IngredientRow extends StatelessWidget {
  final String name;
  final String status;
  final List<String> reasons;
  final Color nameColor;
  final Color badgeBg;
  final Color badgeText;
  final bool isLast;

  const _IngredientRow({
    required this.name,
    required this.status,
    required this.reasons,
    required this.nameColor,
    required this.badgeBg,
    required this.badgeText,
    this.isLast = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        border: isLast
            ? null
            : const Border(
                bottom: BorderSide(color: Color(0x0A000000)),
              ),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  style: TextStyle(
                    fontSize: 12,
                    color: nameColor,
                    fontWeight:
                        status == 'safe' ? FontWeight.w400 : FontWeight.w500,
                  ),
                ),
                if (reasons.isNotEmpty) ...[
                  const SizedBox(height: 3),
                  Text(
                    reasons.join(' · '),
                    style: const TextStyle(
                      fontSize: 11,
                      color: Color(0xFF9A9790),
                      height: 1.3,
                    ),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(width: 8),
          // Status badge
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: badgeBg,
              borderRadius: BorderRadius.circular(99),
            ),
            child: Text(
              status[0].toUpperCase() + status.substring(1),
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w500,
                color: badgeText,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Recommendation Row ────────────────────────────────────────────────────────

class _RecommendationRow extends StatelessWidget {
  final String text;
  final bool isLast;

  const _RecommendationRow({
    required this.text,
    this.isLast = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        border: isLast
            ? null
            : const Border(
                bottom: BorderSide(color: Color(0x0A000000)),
              ),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.only(top: 2),
            child: Icon(
              Icons.info_outline_rounded,
              size: 15,
              color: Color(0xFF2A6E54),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(
                fontSize: 12,
                color: Color(0xFF5A5754),
                height: 1.5,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Section Label ─────────────────────────────────────────────────────────────

class _SectionLabel extends StatelessWidget {
  final String label;
  final String? trailing;

  const _SectionLabel({required this.label, this.trailing});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label.toUpperCase(),
          style: const TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w500,
            color: Color(0xFF9A9790),
            letterSpacing: 0.6,
          ),
        ),
        if (trailing != null)
          Text(
            trailing!,
            style: const TextStyle(
              fontSize: 11,
              color: Color(0xFF9A9790),
            ),
          ),
      ],
    );
  }
}