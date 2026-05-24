import 'package:flutter/material.dart';

class RiskAssessment {
  final String riskLevel; // 'safe', 'caution', 'unsafe'
  final int riskScore;    // 0-100
  final double confidence; // 0.0-1.0
  final List<String> alerts;
  final List<String> recommendations;
  final Map<String, int> severityCounts;
  
  RiskAssessment({
    required this.riskLevel,
    required this.riskScore,
    required this.confidence,
    required this.alerts,
    required this.recommendations,
    required this.severityCounts,
  });
  
  factory RiskAssessment.fromJson(Map<String, dynamic> json) {
    return RiskAssessment(
      riskLevel: json['risk_level'] ?? 'safe',
      riskScore: json['risk_score'] ?? 0,
      confidence: json['confidence']?.toDouble() ?? 0.0,
      alerts: List<String>.from(json['alerts'] ?? []),
      recommendations: List<String>.from(json['recommendations'] ?? []),
      severityCounts: Map<String, int>.from(json['severity_counts'] ?? {}),
    );
  }
  
  Color getRiskColor() {
    switch (riskLevel) {
      case 'safe': return Colors.green;
      case 'caution': return Colors.orange;
      case 'unsafe': return Colors.red;
      default: return Colors.grey;
    }
  }
  
  IconData getRiskIcon() {
    switch (riskLevel) {
      case 'safe': return Icons.check_circle;
      case 'caution': return Icons.warning;
      case 'unsafe': return Icons.dangerous;
      default: return Icons.help;
    }
  }
  
  String getConfidenceLabel() {
    if (confidence >= 0.9) return 'High Confidence';
    if (confidence >= 0.7) return 'Medium Confidence';
    return 'Low Confidence - Verify Ingredients';
  }
}