import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'screens/home_screen.dart';
import 'screens/login_screen.dart';
import 'screens/profile_setup_screen.dart';
import 'screens/register_screen.dart';
import 'screens/welcome_screen.dart';
import 'services/session_service.dart';
import 'theme/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SessionService.instance.load();
  runApp(const MyApp());
}

class MyApp extends StatefulWidget {
  final bool checkBackendOnStartup;

  const MyApp({
    super.key,
    this.checkBackendOnStartup = true,
  });

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  final GlobalKey<NavigatorState> _navigatorKey = GlobalKey<NavigatorState>();
  final GlobalKey<ScaffoldMessengerState> _messengerKey =
      GlobalKey<ScaffoldMessengerState>();

  @override
  void initState() {
    super.initState();
    SessionService.instance.onSessionExpired = _handleSessionExpired;
  }

  @override
  void dispose() {
    if (SessionService.instance.onSessionExpired == _handleSessionExpired) {
      SessionService.instance.onSessionExpired = null;
    }
    super.dispose();
  }

  void _handleSessionExpired() {
    _navigatorKey.currentState?.pushNamedAndRemoveUntil('/login', (_) => false);
    _messengerKey.currentState?.showSnackBar(
      const SnackBar(
        content: Text('Your session has expired. Please sign in again.'),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: _navigatorKey,
      scaffoldMessengerKey: _messengerKey,
      title: 'BiteRight',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.theme,
      initialRoute: '/',
      onGenerateRoute: _onGenerateRoute,
      builder: (context, child) {
        if (child == null) return const SizedBox.shrink();

        final width = MediaQuery.sizeOf(context).width;
        if (!kIsWeb || width < 700) {
          return child;
        }

        return ColoredBox(
          color: AppTheme.background,
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 430),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: AppTheme.background,
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.08),
                      blurRadius: 30,
                      offset: const Offset(0, 12),
                    ),
                  ],
                ),
                child: child,
              ),
            ),
          ),
        );
      },
    );
  }

  Route<dynamic> _onGenerateRoute(RouteSettings settings) {
    switch (settings.name) {
      case '/':
        return MaterialPageRoute(
          builder: (_) => const WelcomeScreen(),
          settings: settings,
        );
      case '/login':
        return MaterialPageRoute(
          builder: (_) => const LoginScreen(),
          settings: settings,
        );
      case '/register':
        return MaterialPageRoute(
          builder: (_) => const RegisterScreen(),
          settings: settings,
        );
      case '/profile-setup':
        final args = _readRouteArgs(settings);
        return MaterialPageRoute(
          builder: (_) => ProfileSetupScreen(
            userId: args['userId']?.toString() ??
                SessionService.instance.userId ??
                '',
            isSignUp: args['isSignUp'] as bool? ?? false,
          ),
          settings: settings,
        );
      case '/home':
        final args = _readRouteArgs(settings);
        final session = SessionService.instance;
        final userId = args['userId']?.toString() ?? session.userId ?? '';
        if (userId.isEmpty) {
          // No signed-in user: never show an empty home screen.
          return MaterialPageRoute(
            builder: (_) => const LoginScreen(),
            settings: const RouteSettings(name: '/login'),
          );
        }
        return MaterialPageRoute(
          builder: (_) => HomeScreen(
            userId: userId,
            username: args['username']?.toString() ?? session.username,
          ),
          settings: settings,
        );
      default:
        return MaterialPageRoute(
          builder: (_) => const WelcomeScreen(),
          settings: settings,
        );
    }
  }

  Map<String, Object?> _readRouteArgs(RouteSettings settings) {
    final args = settings.arguments;
    if (args is Map<String, Object?>) {
      return args;
    }
    if (args is Map) {
      return args.map((key, value) => MapEntry(key.toString(), value));
    }
    return const {};
  }
}