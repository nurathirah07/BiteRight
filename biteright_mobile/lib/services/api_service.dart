// lib/services/api_service.dart
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:flutter/foundation.dart'; // For kDebugMode, kIsWeb

class ApiService {
  // Live Render Production Backend URL
  static const String _liveProductionUrl = 'https://biteright-g7sm.onrender.com';

  // Dynamically determine the base URL (defaults to live production backend)
  static String get _defaultBaseUrl {
    return _liveProductionUrl;
  }

  // Alternative URLs to try if connection fails
  static List<String> get _alternativeUrls => [
        _liveProductionUrl, // Live Render Cloud Backend
        'http://172.20.10.4:5000', // Local computer IP fallback
        'http://10.0.2.2:5000', // Android emulator fallback
        'http://localhost:5000', // Web / iOS simulator fallback
      ];

  late String _currentBaseUrl;

  // Singleton pattern
  static final ApiService _instance = ApiService._internal();
  factory ApiService() => _instance;

  ApiService._internal() {
    _currentBaseUrl = _defaultBaseUrl;
    _log('Platform: ${kIsWeb ? "Web" : Platform.operatingSystem}');
    _log('Using base URL: $_currentBaseUrl');
  }

  void _log(String message) {
    if (kDebugMode) {
      print('🔍 ApiService: $message');
    }
  }

  int _min(int a, int b) => a < b ? a : b;

  double _asConfidence(dynamic value) {
    if (value is num) {
      return value > 1 ? (value / 100).clamp(0.0, 1.0) : value.toDouble();
    }
    final parsed = double.tryParse(value?.toString() ?? '') ?? 0.0;
    return parsed > 1 ? (parsed / 100).clamp(0.0, 1.0) : parsed;
  }

  int _asInt(dynamic value) {
    if (value is int) return value;
    if (value is double) return value.round();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  /// Normalizes backend/legacy scan payloads for UI (safety score + confidence).
  Map<String, dynamic> normalizeScanAnalysis(Map<String, dynamic> raw) {
    if (raw['isNormalized'] == true) {
      return Map<String, dynamic>.from(raw);
    }
    final merged = Map<String, dynamic>.from(raw);
    if (merged['analysis'] is Map) {
      merged.addAll(Map<String, dynamic>.from(merged['analysis'] as Map));
    }

    var riskLevel = (merged['risk_level'] ?? merged['safety_classification'] ?? 'unknown')
        .toString()
        .toLowerCase();
    var riskScore = _asInt(merged['risk_score']);
    var confidence = _asConfidence(merged['confidence']);
    final ingredients = List<String>.from(merged['ingredients'] ?? []);
    final rawText = (merged['raw_text'] ?? '').toString().trim();
    final alerts = List<String>.from(merged['alerts'] ?? []);

    // Keep backend Risk Score (0 = safest, 100 = most dangerous) directly
    riskScore = riskScore.clamp(0, 100);

    if (confidence <= 0 && (ingredients.isNotEmpty || rawText.isNotEmpty)) {
      confidence = 0.72;
    }

    if ((riskLevel.isEmpty || riskLevel == 'unknown') && alerts.isNotEmpty) {
      final hasUnsafe = alerts.any(
        (a) => a.toLowerCase().contains('matches your'),
      );
      final hasCaution = alerts.any(
        (a) => a.toLowerCase().contains('may violate'),
      );
      if (hasUnsafe) {
        riskLevel = 'unsafe';
        if (riskScore <= 30) riskScore = 75;
      } else if (hasCaution) {
        riskLevel = 'caution';
        if (riskScore <= 30) riskScore = 45;
      } else {
        riskLevel = 'safe';
        if (riskScore > 30) riskScore = 0;
      }
    }

    // Align Risk Score with the verbal riskLevel to prevent contradictory UI displays
    // (e.g. displaying Risk Score: 70% but calling the product Safe).
    if (riskLevel == 'unsafe') {
      final unsafeAlertsCount = alerts.where((a) {
        final lower = a.toLowerCase();
        return lower.contains('matches your') || lower.contains('contains');
      }).length;
      final int minUnsafeScore = (60 + (unsafeAlertsCount > 1 ? (unsafeAlertsCount - 1) * 5 : 0)).clamp(60, 90);
      if (riskScore < minUnsafeScore) {
        riskScore = minUnsafeScore;
      }
    } else if (riskLevel == 'caution') {
      riskScore = riskScore.clamp(26, 59);
    } else if (riskLevel == 'safe') {
      riskScore = riskScore.clamp(0, 25);
    }

    merged['risk_level'] = riskLevel;
    merged['risk_score'] = riskScore;
    merged['confidence'] = confidence;
    if (ingredients.isNotEmpty) {
      merged['ingredients'] = ingredients;
    }
    merged['isNormalized'] = true;
    return merged;
  }

  /// Tests multiple URLs and returns the first working one
  Future<String?> findWorkingUrl() async {
    _log('Testing multiple URLs to find working connection...');

    List<String> urlsToTry = [_currentBaseUrl, ..._alternativeUrls];
    urlsToTry = urlsToTry.toSet().toList();

    for (String url in urlsToTry) {
      try {
        _log('Testing: $url/');
        final response = await http
            .get(
              Uri.parse('$url/'),
            )
            .timeout(const Duration(seconds: 2));

        if (response.statusCode == 200 || response.statusCode == 404) {
          _log('✅ Found working URL: $url');
          return url;
        }
      } catch (e) {
        _log('❌ Failed: $url - ${e.toString().split('\n').first}');
      }
    }

    _log('⚠️ No working URL found');
    return null;
  }

  /// Tests the current connection and auto-switches URL if needed
  Future<bool> testConnection() async {
    try {
      _log('Testing connection to $_currentBaseUrl');
      final response = await http
          .get(
            Uri.parse('$_currentBaseUrl/'),
          )
          .timeout(const Duration(seconds: 5));

      _log('Test connection status: ${response.statusCode}');
      if (response.statusCode == 200 || response.statusCode == 404) {
        _log('✅ Connection successful');
        return true;
      }

      _log('Unexpected status code, trying alternatives...');
      String? workingUrl = await findWorkingUrl();
      if (workingUrl != null) {
        _currentBaseUrl = workingUrl;
        _log('✅ Switched to working URL: $_currentBaseUrl');
        return true;
      }

      return false;
    } catch (e) {
      _log('Connection test failed: $e');

      String? workingUrl = await findWorkingUrl();
      if (workingUrl != null) {
        _currentBaseUrl = workingUrl;
        _log('✅ Switched to working URL: $_currentBaseUrl');
        return true;
      }

      return false;
    }
  }

  // Core app API methods

  Future<Map<String, dynamic>?> getDietaryOptions() async {
    try {
      _log('Fetching from: $_currentBaseUrl/dietary-options');

      final response = await http
          .get(
        Uri.parse('$_currentBaseUrl/dietary-options'),
      )
          .timeout(
        const Duration(seconds: 45),
        onTimeout: () {
          _log('Connection timeout');
          throw Exception('Connection timeout');
        },
      );

      _log('Status code: ${response.statusCode}');

      if (response.statusCode == 200) {
        final String responseBody = response.body;
        _log(
            'Response body preview: ${responseBody.substring(0, _min(200, responseBody.length))}...');

        final data = json.decode(responseBody);
        _log('Successfully parsed data');
        _log('Data keys: ${data.keys}');
        return data;
      } else {
        _log('Error: HTTP ${response.statusCode}');
        return null;
      }
    } catch (e) {
      _log('Error loading options: $e');
      await testConnection();
      return null;
    }
  }

  Future<Map<String, dynamic>?> getUserProfile(String userId) async {
    try {
      _log('Fetching profile for user: $userId');

      final response = await http
          .get(
        Uri.parse('$_currentBaseUrl/users/$userId/profile'),
      )
          .timeout(
        const Duration(seconds: 45),
        onTimeout: () {
          _log('Connection timeout');
          throw Exception('Connection timeout');
        },
      );

      _log('Profile response status: ${response.statusCode}');

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        _log('Profile data received');
        return data;
      } else if (response.statusCode == 404) {
        _log('User not found');
        return null;
      } else {
        _log('Error: HTTP ${response.statusCode}');
        return null;
      }
    } catch (e) {
      _log('Error fetching profile: $e');
      return null;
    }
  }

  Future<List<Map<String, dynamic>>> getScanHistory(String userId,
      {int limit = 50}) async {
    try {
      _log('Fetching scan history for user: $userId');

      final response = await http
          .get(
            Uri.parse('$_currentBaseUrl/users/$userId/scans'),
          )
          .timeout(const Duration(seconds: 45));

      _log('Scan history response: ${response.statusCode}');

      if (response.statusCode == 200) {
        final List<dynamic> data = json.decode(response.body);
        _log('Found ${data.length} scans');
        return data
            .map((scan) => normalizeScanAnalysis(
                  Map<String, dynamic>.from(scan as Map),
                ))
            .toList();
      } else {
        _log('Failed to fetch scan history: ${response.body}');
        return [];
      }
    } catch (e) {
      _log('Error fetching scan history: $e');
      return [];
    }
  }

  Future<bool> deleteScan(String userId, String scanId) async {
    try {
      _log('Deleting scan: $scanId');

      final response = await http
          .delete(
            Uri.parse('$_currentBaseUrl/users/$userId/scans/$scanId'),
          )
          .timeout(const Duration(seconds: 45));

      return response.statusCode == 200;
    } catch (e) {
      _log('Error deleting scan: $e');
      return false;
    }
  }

  Future<Map<String, dynamic>?> createUser(String username, String email,
      String password, List<String> allergies, List<String> diets) async {
    try {
      _log('Creating user: $username, $email');
      _log('Allergies: $allergies');
      _log('Diets: $diets');

      final response = await http
          .post(
            Uri.parse('$_currentBaseUrl/users'),
            headers: {'Content-Type': 'application/json'},
            body: json.encode({
              'username': username,
              'email': email,
              'password': password,
              'allergies': allergies,
              'dietary_restrictions': diets,
            }),
          )
          .timeout(const Duration(seconds: 25));

      _log('Create user response: ${response.statusCode}');

      if (response.statusCode == 201) {
        final data = json.decode(response.body);
        _log('User created successfully');
        _log('Response data: $data');

        if (data['user'] != null) {
          return data;
        } else if (data['id'] != null) {
          return {'user': data};
        } else {
          return data;
        }
      } else if (response.statusCode == 409) {
        _log('User already exists');
        throw Exception('User already exists');
      } else {
        _log('Failed to create user: ${response.body}');
        return null;
      }
    } catch (e) {
      _log('Error creating user: $e');
      return null;
    }
  }

  Future<bool> updateUserProfile(
      String userId, List<String> allergies, List<String> diets) async {
    try {
      _log('Updating profile for user: $userId');
      _log('Allergies: $allergies');
      _log('Diets: $diets');

      final response = await http
          .put(
        Uri.parse('$_currentBaseUrl/users/$userId/profile'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'allergies': allergies,
          'dietary_restrictions': diets,
        }),
      )
          .timeout(
        const Duration(seconds: 45),
        onTimeout: () {
          _log('Connection timeout');
          throw Exception('Connection timeout');
        },
      );

      _log('Update response status: ${response.statusCode}');

      if (response.statusCode == 200) {
        _log('Profile updated successfully');
        return true;
      } else {
        _log('Update failed: ${response.body}');
        return false;
      }
    } catch (e) {
      _log('Error updating profile: $e');
      return false;
    }
  }

  Future<Map<String, dynamic>?> login(String email, String password) async {
    try {
      _log('Logging in user: $email');

      final response = await http
          .post(
            Uri.parse('$_currentBaseUrl/login'),
            headers: {'Content-Type': 'application/json'},
            body: json.encode({
              'email': email,
              'password': password,
            }),
          )
          .timeout(const Duration(seconds: 10));

      _log('Login response: ${response.statusCode}');

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        _log('Login successful');
        return data;
      } else if (response.statusCode == 401) {
        _log('Invalid credentials');
        return null;
      } else {
        _log('Login failed: ${response.statusCode}');
        return null;
      }
    } catch (e) {
      _log('Error logging in: $e');
      return null;
    }
  }

  Future<String?> requestPasswordReset(String email) async {
    try {
      _log('Requesting password reset for: $email');

      final response = await http
          .post(
            Uri.parse('$_currentBaseUrl/reset-password-request'),
            headers: {'Content-Type': 'application/json'},
            body: json.encode({
              'email': email,
            }),
          )
          .timeout(const Duration(seconds: 10));

      _log('Reset request response: ${response.statusCode}');

      if (response.statusCode == 200) {
        _log('Password reset code generated successfully');
        final data = json.decode(response.body);
        return (data['code'] ?? '').toString();
      } else {
        final data = json.decode(response.body);
        final errorMsg = data['error'] ?? 'Unknown error';
        _log('Password reset request failed: $errorMsg');
        throw Exception(errorMsg);
      }
    } catch (e) {
      _log('Error in requestPasswordReset: $e');
      rethrow;
    }
  }

  Future<bool> resetPassword(String email, String code, String newPassword) async {
    try {
      _log('Resetting password for: $email with code: $code');

      final response = await http
          .post(
            Uri.parse('$_currentBaseUrl/reset-password'),
            headers: {'Content-Type': 'application/json'},
            body: json.encode({
              'email': email,
              'code': code,
              'new_password': newPassword,
            }),
          )
          .timeout(const Duration(seconds: 10));

      _log('Reset password response: ${response.statusCode}');

      if (response.statusCode == 200) {
        _log('Password reset successfully');
        return true;
      } else {
        final data = json.decode(response.body);
        final errorMsg = data['error'] ?? 'Unknown error';
        _log('Password reset failed: $errorMsg');
        throw Exception(errorMsg);
      }
    } catch (e) {
      _log('Error in resetPassword: $e');
      rethrow;
    }
  }

  Future<bool> updateUserProfileWithSeverity(
    String userId,
    List<Map<String, String>> allergiesList,
    List<String> diets,
  ) async {
    try {
      _log('Updating profile with severity for user: $userId');
      _log('Allergies: $allergiesList');
      _log('Diets: $diets');

      final response = await http
          .put(
        Uri.parse('$_currentBaseUrl/users/$userId/profile'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'allergies': allergiesList,
          'dietary_restrictions': diets,
        }),
      )
          .timeout(
        const Duration(seconds: 45),
        onTimeout: () {
          _log('Connection timeout');
          throw Exception('Connection timeout');
        },
      );

      _log('Update with severity response status: ${response.statusCode}');

      if (response.statusCode == 200) {
        _log('Profile with severity updated successfully');
        return true;
      } else {
        _log('Update with severity failed: ${response.body}');
        return false;
      }
    } catch (e) {
      _log('Error updating profile with severity: $e');
      return false;
    }
  }

  Future<Map<String, dynamic>?> updateAccountInfo({
    required String userId,
    required String username,
    required String email,
    String? password,
  }) async {
    try {
      _log('Updating account info for user: $userId');

      final body = <String, dynamic>{
        'username': username,
        'email': email,
      };
      if (password != null && password.trim().isNotEmpty) {
        body['password'] = password.trim();
      }

      final response = await http
          .put(
            Uri.parse('$_currentBaseUrl/users/$userId/profile'),
            headers: {'Content-Type': 'application/json'},
            body: json.encode(body),
          )
          .timeout(const Duration(seconds: 25));

      _log('Update account response status: ${response.statusCode}');

      if (response.statusCode == 200) {
        return Map<String, dynamic>.from(json.decode(response.body));
      }

      final details =
          response.body.isNotEmpty ? response.body : response.reasonPhrase;
      throw Exception(details ?? 'Failed to update account');
    } catch (e) {
      _log('Error updating account info: $e');
      return {'error': e.toString()};
    }
  }

  static const Duration _extractTimeout = Duration(seconds: 120);

  Future<Map<String, dynamic>?> extractIngredients(File image) async {
    try {
      await testConnection();
      _log('Extracting ingredients from: $_currentBaseUrl/extract-ingredients');

      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$_currentBaseUrl/extract-ingredients'),
      );
      request.files.add(await http.MultipartFile.fromPath('image', image.path));

      final streamedResponse = await request.send().timeout(
        _extractTimeout,
        onTimeout: () {
          throw TimeoutException(
            'Ingredient extraction timed out after ${_extractTimeout.inSeconds}s',
          );
        },
      );
      final response = await http.Response.fromStream(streamedResponse).timeout(
        _extractTimeout,
        onTimeout: () {
          throw TimeoutException(
            'Timed out while reading extraction response',
          );
        },
      );

      _log('Extract response: ${response.statusCode}');
      if (response.statusCode == 200) {
        return Map<String, dynamic>.from(json.decode(response.body));
      }

      _log('Extract failed: ${response.body}');
      return {
        'error': 'Extraction failed: ${response.statusCode}',
        'details': response.body,
      };
    } on TimeoutException catch (e) {
      _log('Error extracting ingredients: $e');
      return {
        'error':
            'Extraction took too long. Use a clear photo of the ingredients list, '
            'ensure the backend is running, and try again.',
      };
    } catch (e) {
      _log('Error extracting ingredients: $e');
      return {'error': 'Network error: $e'};
    }
  }

  Future<Map<String, dynamic>?> analyzeIngredientsWithProfile(
    String userId,
    String ingredientsText,
  ) async {
    try {
      await testConnection();
      _log('Analyzing ingredients for user: $userId');
      _log('Ingredients text length: ${ingredientsText.length}');

      final response = await http
          .post(
            Uri.parse('$_currentBaseUrl/analyze-with-profile'),
            headers: {'Content-Type': 'application/json'},
            body: json.encode({
              'ingredients_text': ingredientsText,
              'user_id': userId,
            }),
          )
          .timeout(const Duration(seconds: 20));

      _log('Analyze response status: ${response.statusCode}');

      if (response.statusCode == 200) {
        final Map<String, dynamic> analysisResult = normalizeScanAnalysis(
          Map<String, dynamic>.from(json.decode(response.body)),
        );

        _log('=== BACKEND ANALYSIS RESULT ===');
        _log('Risk Level: ${analysisResult['risk_level']}');
        _log('Risk Score: ${analysisResult['risk_score']}');
        _log('Confidence: ${analysisResult['confidence']}');
        _log('Alerts: ${analysisResult['alerts']}');
        if (analysisResult['model_info'] != null) {
          final info = analysisResult['model_info'];
          _log('Model Info: ${json.encode(info)}');
          if (info['ocr_engine'] != null) {
            _log('OCR Engine Used: ${info['ocr_engine']}');
            _log('OCR Confidence: ${info['ocr_confidence']}');
          }
        }
        _log('Raw Body: ${response.body}');
        _log('===============================');

        return analysisResult;
      }

      _log('Analyze failed: ${response.body}');
      return {
        'error': 'Analysis failed: ${response.statusCode}',
        'details': response.body,
      };
    } catch (e) {
      _log('Error analyzing ingredients: $e');
      return {'error': 'Network error: $e'};
    }
  }

  Future<Map<String, dynamic>?> addScanToHistory(
    String userId,
    Map<String, dynamic> scanData,
  ) async {
    try {
      // CRITICAL FIX: Use the values from the analysis result directly
      // DO NOT recalculate anything - the backend already did the calculation

      final normalized = normalizeScanAnalysis(scanData);
      final riskLevel = normalized['risk_level'] ?? 'unknown';
      final riskScore = normalized['risk_score'] ?? 0;
      final confidence = normalized['confidence'] ?? 0.75;
      final alerts = normalized['alerts'] ?? [];

      _log('=== SAVING SCAN TO HISTORY ===');
      _log('Risk Level from analysis: $riskLevel');
      _log('Risk Score from analysis: $riskScore');
      _log('Confidence from analysis: $confidence');
      _log('Alerts count: ${alerts.length}');

      // Prepare the scan data to save - USE THE EXACT SAME VALUES FROM ANALYSIS
      final Map<String, dynamic> dataToSave = {
        'user_id': userId,
        'product_name': normalized['product_name'] ?? scanData['product_name'] ?? 'Scanned Product',
        'ingredients': normalized['ingredients'] ?? scanData['ingredients'] ?? [],
        'ingredient_details':
            normalized['ingredient_details'] ?? scanData['ingredient_details'] ?? [],
        'risk_level': riskLevel,
        'risk_score': riskScore,
        'safety_classification': riskLevel,
        'alerts': alerts,
        'recommendations':
            normalized['recommendations'] ?? scanData['recommendations'] ?? [],
        'confidence': confidence,
        'detection_method':
            normalized['detection_method'] ?? scanData['detection_method'] ?? 'AI Analysis',
        'allergens_detected':
            normalized['allergens_detected'] ?? scanData['allergens_detected'] ?? [],
        'raw_text': normalized['raw_text'] ?? scanData['raw_text'] ?? '',
        'input_image_url':
            scanData['input_image_url'] ?? scanData['image_url'] ?? '',
        'scanned_at': DateTime.now().toIso8601String(),
      };

      _log('Data being saved:');
      _log('  risk_level: ${dataToSave['risk_level']}');
      _log('  risk_score: ${dataToSave['risk_score']}');
      _log('  confidence: ${dataToSave['confidence']}');

      final response = await http
          .post(
            Uri.parse('$_currentBaseUrl/users/$userId/scans'),
            headers: {'Content-Type': 'application/json'},
            body: json.encode(dataToSave),
          )
          .timeout(const Duration(seconds: 25));

      _log('Add scan history response: ${response.statusCode}');

      if (response.statusCode == 201) {
        final data = json.decode(response.body);
        _log('✅ Scan saved successfully with risk level: $riskLevel');
        return {
          'scan_id': data['scan_id']?.toString(),
          'newly_unlocked_badges': data['newly_unlocked_badges'] ?? [],
        };
      } else {
        _log('❌ Failed to save scan history: ${response.body}');
        return null;
      }
    } catch (e) {
      _log('Error saving scan history: $e');
      return null;
    }
  }

  Future<Map<String, dynamic>?> getAnalyticsSummary(String userId) async {
    try {
      _log('Fetching analytics summary for user: $userId');

      final response = await http
          .get(
            Uri.parse('$_currentBaseUrl/users/$userId/analytics/summary'),
          )
          .timeout(const Duration(seconds: 45));

      _log('Analytics summary response: ${response.statusCode}');

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        _log('Successfully fetched analytics summary');
        return data;
      } else {
        _log('Failed to fetch analytics summary: ${response.body}');
        return null;
      }
    } catch (e) {
      _log('Error fetching analytics summary: $e');
      return null;
    }
  }
}