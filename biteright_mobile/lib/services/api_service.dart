// lib/services/api_service.dart
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'session_service.dart';

/// Error with a message that is safe to show to the user.
class ApiException implements Exception {
  final String message;
  final int? statusCode;

  const ApiException(this.message, {this.statusCode});

  @override
  String toString() => message;
}

class ApiService {
  /// Override at build time with
  /// `flutter run --dart-define=API_BASE_URL=http://10.0.2.2:5000`.
  static const String _configuredBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://biteright-g7sm.onrender.com',
  );

  /// Local fallbacks, only tried in debug builds.
  static const List<String> _debugFallbackUrls = [
    'http://10.0.2.2:5000', // Android emulator
    'http://localhost:5000', // Web / iOS simulator
  ];

  static const Duration _shortTimeout = Duration(seconds: 25);
  // Render's free tier can take ~50s to wake up, so data calls get headroom.
  static const Duration _defaultTimeout = Duration(seconds: 60);
  static const Duration _extractTimeout = Duration(seconds: 120);

  late String _currentBaseUrl;
  final SessionService _session = SessionService.instance;

  // Singleton pattern
  static final ApiService _instance = ApiService._internal();
  factory ApiService() => _instance;

  ApiService._internal() {
    _currentBaseUrl = _configuredBaseUrl;
    _log('Platform: ${kIsWeb ? "Web" : Platform.operatingSystem}');
    _log('Using base URL: $_currentBaseUrl');
  }

  String get baseUrl => _currentBaseUrl;

  void _log(String message) {
    if (kDebugMode) {
      debugPrint('ApiService: $message');
    }
  }

  // ───────────────────────── Request helpers ─────────────────────────

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$_currentBaseUrl$path').replace(queryParameters: query);

  Map<String, String> _headers({bool json = false}) {
    final headers = <String, String>{'Accept': 'application/json'};
    if (json) headers['Content-Type'] = 'application/json';
    final token = _session.token;
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  Future<http.Response> _send(
    Future<http.Response> request, {
    Duration timeout = _defaultTimeout,
  }) async {
    final response = await request.timeout(timeout);
    if (response.statusCode == 401 && _session.isSignedIn) {
      _log('Session rejected by server; signing out');
      unawaited(_session.expire());
    }
    return response;
  }

  Future<http.Response> _get(String path,
          {Map<String, String>? query, Duration timeout = _defaultTimeout}) =>
      _send(http.get(_uri(path, query), headers: _headers()),
          timeout: timeout);

  Future<http.Response> _post(String path, Object body,
          {Duration timeout = _defaultTimeout}) =>
      _send(
        http.post(_uri(path),
            headers: _headers(json: true), body: json.encode(body)),
        timeout: timeout,
      );

  Future<http.Response> _put(String path, Object body,
          {Duration timeout = _defaultTimeout}) =>
      _send(
        http.put(_uri(path),
            headers: _headers(json: true), body: json.encode(body)),
        timeout: timeout,
      );

  Future<http.Response> _delete(String path,
          {Duration timeout = _defaultTimeout}) =>
      _send(http.delete(_uri(path), headers: _headers()), timeout: timeout);

  dynamic _decode(http.Response response) {
    if (response.body.isEmpty) return null;
    try {
      return json.decode(utf8.decode(response.bodyBytes));
    } on FormatException {
      return null;
    }
  }

  /// The server's `error`/`message` field, or [fallback].
  String _errorMessage(http.Response response, String fallback) {
    final data = _decode(response);
    if (data is Map) {
      final message = data['error'] ?? data['message'];
      if (message != null && message.toString().trim().isNotEmpty) {
        return message.toString();
      }
    }
    return fallback;
  }

  /// Converts any error into a sentence suitable for a snackbar.
  static String friendlyError(Object error) {
    if (error is ApiException) return error.message;
    if (error is TimeoutException) {
      return 'The server took too long to respond. It may be starting up, '
          'so please try again in a moment.';
    }
    if (error is SocketException || error is http.ClientException) {
      return "Can't reach the BiteRight server. Check your internet connection and try again.";
    }
    return 'Something went wrong. Please try again.';
  }

  // ───────────────────────── Scan normalisation ─────────────────────────

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
      final analysis = Map<String, dynamic>.from(merged['analysis'] as Map);
      for (final entry in analysis.entries) {
        merged.putIfAbsent(entry.key, () => entry.value);
      }
    }

    var riskLevel =
        (merged['risk_level'] ?? merged['safety_classification'] ?? 'unknown')
            .toString()
            .toLowerCase();
    var riskScore = _asInt(merged['risk_score']);
    var confidence = _asConfidence(merged['confidence']);
    final ingredients = List<String>.from(
      (merged['ingredients'] as List?)?.map((e) => e.toString()) ?? const [],
    );
    final rawText = (merged['raw_text'] ?? '').toString().trim();
    final alerts = List<String>.from(
      (merged['alerts'] as List?)?.map((e) => e.toString()) ?? const [],
    );

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

    // Align Risk Score with the verbal riskLevel to prevent contradictory UI
    // displays (e.g. Risk Score 70% on a product labelled Safe).
    if (riskLevel == 'unsafe') {
      final unsafeAlertsCount = alerts.where((a) {
        final lower = a.toLowerCase();
        return lower.contains('matches your') || lower.contains('contains');
      }).length;
      final int minUnsafeScore =
          (60 + (unsafeAlertsCount > 1 ? (unsafeAlertsCount - 1) * 5 : 0))
              .clamp(60, 90);
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

  // ───────────────────────── Connectivity ─────────────────────────

  /// Returns the first base URL that answers, preferring the configured one.
  Future<String?> findWorkingUrl() async {
    final urls = <String>{
      _currentBaseUrl,
      _configuredBaseUrl,
      if (kDebugMode) ..._debugFallbackUrls,
    };
    for (final url in urls) {
      try {
        final response = await http
            .get(Uri.parse('$url/health'))
            .timeout(const Duration(seconds: 5));
        if (response.statusCode == 200) {
          _log('Found working URL: $url');
          return url;
        }
      } catch (e) {
        _log('Failed: $url - ${e.toString().split('\n').first}');
      }
    }
    return null;
  }

  /// Checks the backend is reachable. The first request after the server
  /// has been idle can be slow, so this allows a generous timeout.
  Future<bool> testConnection() async {
    try {
      final response = await http
          .get(_uri('/health'))
          .timeout(_defaultTimeout);
      if (response.statusCode == 200) return true;
    } catch (e) {
      _log('Connection test failed: $e');
    }

    final workingUrl = await findWorkingUrl();
    if (workingUrl != null) {
      _currentBaseUrl = workingUrl;
      return true;
    }
    return false;
  }

  /// Fire-and-forget ping so a sleeping server starts waking up early.
  Future<void> preWarmBackend() async {
    try {
      await http.get(_uri('/health')).timeout(const Duration(seconds: 15));
    } catch (e) {
      _log('Pre-warm ping warning: $e');
    }
  }

  // ───────────────────────── Auth ─────────────────────────

  Future<void> _storeSession(Map<String, dynamic> data) async {
    final user = Map<String, dynamic>.from(data['user'] as Map? ?? const {});
    final userId = (user['id'] ?? data['id'] ?? '').toString();
    final token = (data['token'] ?? '').toString();
    if (userId.isEmpty || token.isEmpty) {
      throw const ApiException(
          'The server did not return a valid session. Please try again.');
    }
    await _session.save(
      userId: userId,
      username: (user['username'] ?? 'User').toString(),
      token: token,
    );
  }

  /// Creates an account and signs in. Throws [ApiException] on failure.
  Future<Map<String, dynamic>> createUser(String username, String email,
      String password, List<String> allergies, List<String> diets) async {
    final response = await _post(
      '/users',
      {
        'username': username,
        'email': email,
        'password': password,
        'allergies': allergies,
        'dietary_restrictions': diets,
      },
      timeout: _defaultTimeout,
    );

    if (response.statusCode == 201) {
      final data = Map<String, dynamic>.from(_decode(response) as Map);
      data['user'] ??= {'id': data['id'], 'username': username};
      await _storeSession(data);
      return data;
    }
    throw ApiException(
      _errorMessage(response, 'Registration failed. Please try again.'),
      statusCode: response.statusCode,
    );
  }

  /// Signs in. Returns null for wrong credentials and throws
  /// [ApiException] for other failures (rate limiting, server errors).
  Future<Map<String, dynamic>?> login(String email, String password) async {
    final response = await _post(
      '/login',
      {'email': email, 'password': password},
    );

    if (response.statusCode == 200) {
      final data = Map<String, dynamic>.from(_decode(response) as Map);
      await _storeSession(data);
      return data;
    }
    if (response.statusCode == 401) return null;
    throw ApiException(
      _errorMessage(response, 'Sign in failed. Please try again.'),
      statusCode: response.statusCode,
    );
  }

  Future<void> logout() => _session.clear();

  /// Asks the server to email a reset code. Throws [ApiException] on failure.
  Future<bool> requestPasswordReset(String email) async {
    final response = await _post('/reset-password-request', {'email': email});
    if (response.statusCode == 200) return true;
    throw ApiException(
      _errorMessage(response, 'Could not send the reset code. Please try again.'),
      statusCode: response.statusCode,
    );
  }

  /// Sets a new password using the emailed code. Throws [ApiException] on failure.
  Future<bool> resetPassword(
      String email, String code, String newPassword) async {
    final response = await _post('/reset-password', {
      'email': email,
      'code': code,
      'new_password': newPassword,
    });
    if (response.statusCode == 200) return true;
    throw ApiException(
      _errorMessage(response, 'Password reset failed. Please try again.'),
      statusCode: response.statusCode,
    );
  }

  // ───────────────────────── Profile ─────────────────────────

  Future<Map<String, dynamic>?> getDietaryOptions() async {
    try {
      final response = await _get('/dietary-options');
      if (response.statusCode == 200) {
        return Map<String, dynamic>.from(_decode(response) as Map);
      }
      _log('Dietary options failed: HTTP ${response.statusCode}');
    } catch (e) {
      _log('Error loading options: $e');
    }
    return null;
  }

  Future<Map<String, dynamic>?> getUserProfile(String userId) async {
    try {
      final response = await _get('/users/$userId/profile');
      if (response.statusCode == 200) {
        return Map<String, dynamic>.from(_decode(response) as Map);
      }
      _log('Profile fetch failed: HTTP ${response.statusCode}');
    } catch (e) {
      _log('Error fetching profile: $e');
    }
    return null;
  }

  Future<bool> updateUserProfileWithSeverity(
    String userId,
    List<Map<String, String>> allergiesList,
    List<String> diets,
  ) async {
    try {
      final response = await _put('/users/$userId/profile', {
        'allergies': allergiesList,
        'dietary_restrictions': diets,
      });
      return response.statusCode == 200;
    } catch (e) {
      _log('Error updating profile: $e');
      return false;
    }
  }

  /// Updates name, email and optionally password. Returns the response body,
  /// or `{'error': message}` on failure.
  Future<Map<String, dynamic>?> updateAccountInfo({
    required String userId,
    required String username,
    required String email,
    String? password,
  }) async {
    final body = <String, dynamic>{'username': username, 'email': email};
    if (password != null && password.trim().isNotEmpty) {
      body['password'] = password.trim();
    }

    try {
      final response = await _put('/users/$userId/profile', body,
          timeout: _shortTimeout);
      if (response.statusCode == 200) {
        await _session.updateUsername(username);
        return Map<String, dynamic>.from(_decode(response) as Map);
      }
      return {'error': _errorMessage(response, 'Failed to update account')};
    } catch (e) {
      _log('Error updating account info: $e');
      return {'error': friendlyError(e)};
    }
  }

  // ───────────────────────── Scanning ─────────────────────────

  Future<Map<String, dynamic>?> extractIngredients(File image) async {
    try {
      final request = http.MultipartRequest('POST', _uri('/extract-ingredients'))
        ..headers.addAll(_headers())
        ..files.add(await http.MultipartFile.fromPath('image', image.path));

      final streamed = await request.send().timeout(_extractTimeout);
      final response =
          await http.Response.fromStream(streamed).timeout(_extractTimeout);

      if (response.statusCode == 200) {
        return Map<String, dynamic>.from(_decode(response) as Map);
      }
      return {
        'error': _errorMessage(response,
            'Could not read the label (error ${response.statusCode}). Please try again.'),
      };
    } on TimeoutException {
      return {
        'error':
            'Reading the label took too long. Use a clear, well-lit photo of '
                'the ingredients list and try again.',
      };
    } catch (e) {
      _log('Error extracting ingredients: $e');
      return {'error': friendlyError(e)};
    }
  }

  Future<Map<String, dynamic>?> analyzeIngredientsWithProfile(
    String userId,
    String ingredientsText,
  ) async {
    try {
      final response = await _post('/analyze-with-profile', {
        'ingredients_text': ingredientsText,
        'user_id': userId,
      });

      if (response.statusCode == 200) {
        final result = normalizeScanAnalysis(
          Map<String, dynamic>.from(_decode(response) as Map),
        );
        _log('Analysis: ${result['risk_level']} '
            '(score ${result['risk_score']}, confidence ${result['confidence']})');
        return result;
      }
      return {
        'error': _errorMessage(response,
            'Analysis failed (error ${response.statusCode}). Please try again.'),
      };
    } catch (e) {
      _log('Error analyzing ingredients: $e');
      return {'error': friendlyError(e)};
    }
  }

  /// Saves an analysed scan. Returns `{scan_id, newly_unlocked_badges}` or null.
  Future<Map<String, dynamic>?> addScanToHistory(
    String userId,
    Map<String, dynamic> scanData,
  ) async {
    try {
      final normalized = normalizeScanAnalysis(scanData);
      final riskLevel = normalized['risk_level'] ?? 'unknown';

      final dataToSave = <String, dynamic>{
        'user_id': userId,
        'product_name': normalized['product_name'] ?? 'Scanned Product',
        'ingredients': normalized['ingredients'] ?? [],
        'ingredient_details': normalized['ingredient_details'] ?? [],
        'risk_level': riskLevel,
        'risk_score': normalized['risk_score'] ?? 0,
        'safety_classification': riskLevel,
        'alerts': normalized['alerts'] ?? [],
        'recommendations': normalized['recommendations'] ?? [],
        'confidence': normalized['confidence'] ?? 0.75,
        'detection_method': normalized['detection_method'] ?? 'AI Analysis',
        'allergens_detected': normalized['allergens_detected'] ?? [],
        'raw_text': normalized['raw_text'] ?? '',
        'was_edited': normalized['was_edited'] ?? false,
        'input_image_url':
            scanData['input_image_url'] ?? scanData['image_url'] ?? '',
        'scanned_at': DateTime.now().toIso8601String(),
      };

      final response = await _post('/users/$userId/scans', dataToSave,
          timeout: _shortTimeout);

      if (response.statusCode == 201) {
        final data = Map<String, dynamic>.from(_decode(response) as Map);
        return {
          'scan_id': data['scan_id']?.toString(),
          'newly_unlocked_badges': data['newly_unlocked_badges'] ?? [],
        };
      }
      _log('Failed to save scan: HTTP ${response.statusCode}');
    } catch (e) {
      _log('Error saving scan history: $e');
    }
    return null;
  }

  Future<List<Map<String, dynamic>>> getScanHistory(String userId,
      {int limit = 50}) async {
    try {
      final response = await _get('/users/$userId/scans');
      if (response.statusCode == 200) {
        final data = _decode(response) as List? ?? const [];
        return data
            .map((scan) => normalizeScanAnalysis(
                  Map<String, dynamic>.from(scan as Map),
                ))
            .toList();
      }
      _log('Scan history failed: HTTP ${response.statusCode}');
    } catch (e) {
      _log('Error fetching scan history: $e');
    }
    return [];
  }

  Future<bool> deleteScan(String userId, String scanId) async {
    try {
      final response = await _delete('/users/$userId/scans/$scanId');
      return response.statusCode == 200;
    } catch (e) {
      _log('Error deleting scan: $e');
      return false;
    }
  }

  Future<Map<String, dynamic>?> getAnalyticsSummary(String userId) async {
    try {
      final response = await _get('/users/$userId/analytics/summary');
      if (response.statusCode == 200) {
        return Map<String, dynamic>.from(_decode(response) as Map);
      }
      _log('Analytics summary failed: HTTP ${response.statusCode}');
    } catch (e) {
      _log('Error fetching analytics summary: $e');
    }
    return null;
  }

  // ───────────────────────── Barcode & pantry ─────────────────────────

  /// Looks up a barcode. Always returns a map: `found: true` with the
  /// analysis, or `found: false` with a user-facing `message`.
  Future<Map<String, dynamic>> lookupBarcode(
      String barcode, String userId) async {
    try {
      final response = await _get(
        '/barcode/$barcode',
        query: userId.isNotEmpty ? {'user_id': userId} : null,
      );

      final data = _decode(response);
      if (response.statusCode == 200 && data is Map) {
        return Map<String, dynamic>.from(data);
      }
      return {
        'found': false,
        'message': _errorMessage(response,
            'No product details found for barcode $barcode. Try photographing the ingredient label instead.'),
      };
    } catch (e) {
      _log('Error looking up barcode: $e');
      return {'found': false, 'message': friendlyError(e)};
    }
  }

  Future<List<Map<String, dynamic>>> getUserPantry(String userId) async {
    try {
      final response = await _get('/users/$userId/pantry');
      if (response.statusCode == 200) {
        final data = _decode(response) as List? ?? const [];
        return data
            .map((item) => Map<String, dynamic>.from(item as Map))
            .toList();
      }
      _log('Pantry fetch failed: HTTP ${response.statusCode}');
    } catch (e) {
      _log('Error fetching pantry: $e');
    }
    return [];
  }

  Future<bool> deletePantryItem(String userId, String itemId) async {
    try {
      final response = await _delete('/users/$userId/pantry/$itemId');
      return response.statusCode == 200;
    } catch (e) {
      _log('Error deleting pantry item: $e');
      return false;
    }
  }
}
