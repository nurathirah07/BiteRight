// lib/models/scan_history.dart
import 'package:flutter/material.dart';

class ScanHistory {
  final String id;
  final String productName;
  final List<String> ingredients;
  final String riskLevel;
  final int riskScore;
  final double confidence;
  final List<String> alerts;
  final DateTime scannedAt;
  final bool userEdited;
  
  ScanHistory({
    required this.id,
    required this.productName,
    required this.ingredients,
    required this.riskLevel,
    required this.riskScore,
    required this.confidence,
    required this.alerts,
    required this.scannedAt,
    this.userEdited = false,
  });
  
  factory ScanHistory.fromJson(Map<String, dynamic> json, String id) {
    return ScanHistory(
      id: id,
      productName: json['product_name'] ?? 'Unknown Product',
      ingredients: List<String>.from(json['ingredients'] ?? []),
      riskLevel: json['risk_level'] ?? 'unknown',
      riskScore: json['risk_score'] ?? 0,
      confidence: (json['confidence'] ?? 0.0).toDouble(),
      alerts: List<String>.from(json['alerts'] ?? []),
      scannedAt: json['scanned_at'] != null
          ? DateTime.parse(json['scanned_at'])
          : DateTime.now(),
      userEdited: json['user_edited'] ?? false,
    );
  }
  
  Color getRiskColor() {
    switch (riskLevel) {
      case 'safe':
        return Colors.green;
      case 'caution':
        return Colors.orange;
      case 'unsafe':
        return Colors.red;
      default:
        return Colors.grey;
    }
  }
  
  IconData getRiskIcon() {
    switch (riskLevel) {
      case 'safe':
        return Icons.check_circle;
      case 'caution':
        return Icons.warning;
      case 'unsafe':
        return Icons.dangerous;
      default:
        return Icons.help;
    }
  }
  
  String getRiskLevelText() {
    switch (riskLevel) {
      case 'safe':
        return 'Safe';
      case 'caution':
        return 'Caution';
      case 'unsafe':
        return 'Unsafe';
      default:
        return 'Unknown';
    }
  }
  
  String getFormattedDate() {
    final now = DateTime.now();
    final difference = now.difference(scannedAt);
    
    if (difference.inDays == 0) {
      if (difference.inHours == 0) {
        if (difference.inMinutes == 0) {
          return 'Just now';
        }
        return '${difference.inMinutes} minutes ago';
      }
      return '${difference.inHours} hours ago';
    } else if (difference.inDays == 1) {
      return 'Yesterday';
    } else if (difference.inDays < 7) {
      return '${difference.inDays} days ago';
    } else {
      return '${scannedAt.day}/${scannedAt.month}/${scannedAt.year}';
    }
  }
}