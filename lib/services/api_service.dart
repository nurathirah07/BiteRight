// lib/services/api_service.dart
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:flutter/foundation.dart'; // For kDebugMode, kIsWeb

class ApiService {
  // Dynamically determine the base URL based on platform
  static String get _defaultBaseUrl {
    if (kIsWeb) {
      return 'http://localhost:5000';
    } else if (Platform.isAndroid) {
      // Android emulator uses 10.0.2.2 to reach host machine's localhost
      return 'http://10.0.2.2:5000';
    } else if (Platform.isIOS) {
      // iOS simulator can use localhost directly
      return 'http://localhost:5000';
    } else {
      // Fallback for other platforms
      return 'http://localhost:5000';
    }
  }

  // Alternative URLs to try if connection fails
  static const List<String> _alternativeUrls = [
    'http://10.0.2.2:5000', // Android emulator
    'http://localhost:5000', // Web / iOS simulator
    'http://127.0.0.1:5000', // Web / iOS simulator (IP loopback)
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
        const Duration(seconds: 10),
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
        const Duration(seconds: 10),
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
          .timeout(const Duration(seconds: 10));

      _log('Scan history response: ${response.statusCode}');

      if (response.statusCode == 200) {
        final List<dynamic> data = json.decode(response.body);
        _log('Found ${data.length} scans');
        return List<Map<String, dynamic>>.from(data);
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
          .timeout(const Duration(seconds: 10));

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
          .timeout(const Duration(seconds: 10));

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
        const Duration(seconds: 10),
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
        const Duration(seconds: 10),
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

  Future<Map<String, dynamic>?> extractIngredients(File image) async {
    try {
      await testConnection();
      _log('Extracting ingredients from: $_currentBaseUrl/extract-ingredients');

      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$_currentBaseUrl/extract-ingredients'),
      );
      request.files.add(await http.MultipartFile.fromPath('image', image.path));

      final streamedResponse =
          await request.send().timeout(const Duration(seconds: 30));
      final response = await http.Response.fromStream(streamedResponse);

      _log('Extract response: ${response.statusCode}');
      if (response.statusCode == 200) {
        return Map<String, dynamic>.from(json.decode(response.body));
      }

      _log('Extract failed: ${response.body}');
      return {
        'error': 'Extraction failed: ${response.statusCode}',
        'details': response.body,
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
        final Map<String, dynamic> analysisResult = 
            Map<String, dynamic>.from(json.decode(response.body));
        
        _log('=== BACKEND ANALYSIS RESULT ===');
        _log('Risk Level: ${analysisResult['risk_level']}');
        _log('Risk Score: ${analysisResult['risk_score']}');
        _log('Confidence: ${analysisResult['confidence']}');
        _log('Alerts: ${analysisResult['alerts']}');
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

  Future<String?> addScanToHistory(
    String userId,
    Map<String, dynamic> scanData,
  ) async {
    try {
      // CRITICAL FIX: Use the values from the analysis result directly
      // DO NOT recalculate anything - the backend already did the calculation
      
      final riskLevel = scanData['risk_level'] ?? 'unknown';
      final riskScore = scanData['risk_score'] ?? 0;
      final confidence = scanData['confidence'] ?? 0.75;
      final alerts = scanData['alerts'] ?? [];
      
      _log('=== SAVING SCAN TO HISTORY ===');
      _log('Risk Level from analysis: $riskLevel');
      _log('Risk Score from analysis: $riskScore');
      _log('Confidence from analysis: $confidence');
      _log('Alerts count: ${alerts.length}');
      
      // Prepare the scan data to save - USE THE EXACT SAME VALUES FROM ANALYSIS
      final Map<String, dynamic> dataToSave = {
        'user_id': userId,
        'product_name': scanData['product_name'] ?? 'Scanned Product',
        'ingredients': scanData['ingredients'] ?? [],
        'ingredient_details': scanData['ingredient_details'] ?? [],
        'risk_level': riskLevel,  // USE BACKEND VALUE
        'risk_score': riskScore,  // USE BACKEND VALUE
        'safety_classification': riskLevel,
        'alerts': alerts,
        'recommendations': scanData['recommendations'] ?? [],
        'confidence': confidence,  // USE BACKEND VALUE
        'detection_method': scanData['detection_method'] ?? 'AI Analysis',
        'allergens_detected': scanData['allergens_detected'] ?? [],
        'raw_text': scanData['raw_text'] ?? '',
        'input_image_url': scanData['input_image_url'] ?? scanData['image_url'] ?? '',
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
          .timeout(const Duration(seconds: 10));

      _log('Add scan history response: ${response.statusCode}');

      if (response.statusCode == 201) {
        final data = json.decode(response.body);
        _log('✅ Scan saved successfully with risk level: $riskLevel');
        return data['scan_id']?.toString();
      } else {
        _log('❌ Failed to save scan history: ${response.body}');
        return null;
      }
    } catch (e) {
      _log('Error saving scan history: $e');
      return null;
    }
  }
}
