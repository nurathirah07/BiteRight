// lib/models/user_profile.dart

class UserProfile {
  final String id;
  final String username;
  final String email;
  final List<UserAllergen> allergies;  // Allergens with severity
  final List<String> dietaryRestrictions;  // Just IDs, no severity
  
  UserProfile({
    required this.id,
    required this.username,
    required this.email,
    required this.allergies,
    required this.dietaryRestrictions,
  });
  
  factory UserProfile.fromJson(Map<String, dynamic> json) {
    // Parse allergies with severity
    List<UserAllergen> allergies = [];
    if (json['allergies'] != null) {
      if (json['allergies'] is List) {
        for (var item in json['allergies']) {
          if (item is String) {
            // Legacy format - just IDs, use default severity
            allergies.add(UserAllergen(allergenId: item, severity: 'medium'));
          } else if (item is Map<String, dynamic>) {
            // New format with severity - explicitly cast to Map<String, dynamic>
            allergies.add(UserAllergen.fromJson(item));
          } else if (item is Map) {
            // Handle dynamic map by converting
            // Create a new Map<String, dynamic> from the dynamic map
            Map<String, dynamic> castedMap = {};
            item.forEach((key, value) {
              if (key is String) {
                castedMap[key] = value;
              }
            });
            allergies.add(UserAllergen.fromJson(castedMap));
          }
        }
      }
    }
    
    return UserProfile(
      id: json['id'] ?? json['user_id'] ?? '',
      username: json['username'] ?? '',
      email: json['email'] ?? '',
      allergies: allergies,
      dietaryRestrictions: List<String>.from(json['dietary_restrictions'] ?? []),
    );
  }
}

// Add UserAllergen class if not in a separate file
class UserAllergen {
  final String allergenId;
  final String severity;
  
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
      allergenId: json['id'] ?? json['allergenId'] ?? '',
      severity: json['severity'] ?? 'medium',
    );
  }
}