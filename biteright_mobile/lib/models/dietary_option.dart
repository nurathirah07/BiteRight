// lib/models/dietary_option.dart
class DietaryOption {
  final String id;
  final String label;
  final String category;
  final String? warning;
  final List<String>? synonyms;
  final String? severity;
  final List<String>? severityOptions; // For allergens, user can choose severity
  
  DietaryOption({
    required this.id,
    required this.label,
    required this.category,
    this.warning,
    this.synonyms,
    this.severity,
    this.severityOptions, // Only for allergens
  });
  
  factory DietaryOption.fromJson(Map<String, dynamic> json) {
    return DietaryOption(
      id: json['id'],
      label: json['label'],
      category: json['category'],
      warning: json['warning'],
      severity: json['severity'],
      severityOptions: json['severity_options'] != null
          ? List<String>.from(json['severity_options'])
          : null,
      synonyms: json['synonyms'] != null 
          ? List<String>.from(json['synonyms']) 
          : null,
    );
  }
  
  // Helper to check if this option has severity choices (allergens only)
  bool get hasSeverityOptions => severityOptions != null && severityOptions!.isNotEmpty;
}

// Class to represent a user's allergen with chosen severity
class UserAllergen {
  final String allergenId;
  final String severity; // 'high', 'medium', or 'low'
  
  UserAllergen({
    required this.allergenId,
    required this.severity,
  });
  
  Map<String, dynamic> toJson() {
    return {
      'id': allergenId,
      'severity': severity,
    };
  }
  
  factory UserAllergen.fromJson(Map<String, dynamic> json) {
    return UserAllergen(
      allergenId: json['id'],
      severity: json['severity'] ?? 'medium', // Default to medium if not specified
    );
  }
}