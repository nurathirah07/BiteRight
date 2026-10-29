import 'package:biteright_mobile/services/session_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final session = SessionService.instance;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await session.clear();
    session.onSessionExpired = null;
  });

  test('save persists the session and load restores it', () async {
    await session.save(userId: 'u1', username: 'Aisha', token: 't0k3n');
    expect(session.isSignedIn, isTrue);

    await session.clear();
    expect(session.isSignedIn, isFalse);

    SharedPreferences.setMockInitialValues({
      'userId': 'u1',
      'username': 'Aisha',
      'authToken': 't0k3n',
    });
    await session.load();
    expect(session.userId, 'u1');
    expect(session.username, 'Aisha');
    expect(session.token, 't0k3n');
    expect(session.isSignedIn, isTrue);
  });

  test('a stored user without a token is not signed in', () async {
    SharedPreferences.setMockInitialValues({'userId': 'legacy-user'});
    await session.load();
    expect(session.userId, 'legacy-user');
    expect(session.isSignedIn, isFalse);
  });

  test('expire clears the session and notifies exactly once', () async {
    await session.save(userId: 'u1', username: 'Aisha', token: 't0k3n');
    var calls = 0;
    session.onSessionExpired = () => calls++;

    await Future.wait([session.expire(), session.expire()]);

    expect(calls, 1);
    expect(session.isSignedIn, isFalse);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('authToken'), isNull);
  });

  test('username falls back to "User" and can be updated', () async {
    expect(session.username, 'User');
    await session.save(userId: 'u1', username: '', token: 't');
    expect(session.username, 'User');
    await session.updateUsername('  New Name ');
    expect(session.username, 'New Name');
  });
}
