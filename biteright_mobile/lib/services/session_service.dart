import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Holds the signed-in user's identity and session token.
///
/// Values are cached in memory after [load] so the API client can attach the
/// token synchronously, and persisted with SharedPreferences so the user stays
/// signed in across app restarts.
class SessionService {
  SessionService._();
  static final SessionService instance = SessionService._();

  static const _userIdKey = 'userId';
  static const _usernameKey = 'username';
  static const _tokenKey = 'authToken';
  static const _tabKey = 'selectedTabIndex';

  String? _userId;
  String? _username;
  String? _token;

  /// Called when the backend rejects the session (HTTP 401). The app wires
  /// this up to send the user back to the sign-in screen.
  VoidCallback? onSessionExpired;
  bool _expiring = false;

  String? get userId => _userId;
  String get username => (_username?.isNotEmpty ?? false) ? _username! : 'User';
  String? get token => _token;
  bool get isSignedIn =>
      (_userId?.isNotEmpty ?? false) && (_token?.isNotEmpty ?? false);

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    _userId = prefs.getString(_userIdKey);
    _username = prefs.getString(_usernameKey);
    _token = prefs.getString(_tokenKey);
  }

  Future<void> save({
    required String userId,
    required String username,
    required String token,
  }) async {
    _userId = userId;
    _username = username;
    _token = token;
    _expiring = false;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_userIdKey, userId);
    await prefs.setString(_usernameKey, username);
    await prefs.setString(_tokenKey, token);
    await prefs.setInt(_tabKey, 0);
  }

  Future<void> updateUsername(String username) async {
    if (username.trim().isEmpty) return;
    _username = username.trim();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_usernameKey, _username!);
  }

  Future<int> savedTabIndex() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getInt(_tabKey) ?? 0;
  }

  Future<void> saveTabIndex(int index) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_tabKey, index);
  }

  Future<void> clear() async {
    _userId = null;
    _username = null;
    _token = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_userIdKey);
    await prefs.remove(_usernameKey);
    await prefs.remove(_tokenKey);
    await prefs.remove(_tabKey);
  }

  /// Clears the session once and notifies listeners, even if several
  /// requests fail with 401 at the same time.
  Future<void> expire() async {
    if (_expiring || !isSignedIn) return;
    _expiring = true;
    await clear();
    onSessionExpired?.call();
  }
}
