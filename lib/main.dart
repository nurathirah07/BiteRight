import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'screens/home_screen.dart';
import 'screens/login_screen.dart';
import 'screens/profile_setup_screen.dart';
import 'screens/register_screen.dart';
import 'screens/welcome_screen.dart';
import 'services/api_service.dart';
import 'theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
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
  final ApiService _apiService = ApiService();

  @override
  void initState() {
    super.initState();
    if (widget.checkBackendOnStartup) {
      _checkBackendConnection();
    }
  }

  Future<void> _checkBackendConnection() async {
    try {
      final isConnected = await _apiService.testConnection();

      if (kDebugMode) {
        debugPrint(
          isConnected
              ? 'Backend connection is reachable.'
              : 'Backend connection is not reachable.',
        );
      }

      if (!isConnected) {
        _showConnectionDialog();
      }
    } catch (error) {
      if (kDebugMode) {
        debugPrint('Backend connection check failed: $error');
      }
      _showConnectionDialog();
    }
  }

  void _showConnectionDialog() {
    final context = _navigatorKey.currentContext;
    if (context == null) {
      return;
    }

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }

      showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Connection Error'),
          content: const Text(
            'Unable to connect to the server. Make sure the backend is running on port 5000. Android emulators use 10.0.2.2 to reach your computer.',
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(context);
                _checkBackendConnection();
              },
              child: const Text('Retry'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Continue Anyway'),
            ),
          ],
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: _navigatorKey,
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
            userId: args['userId']?.toString() ?? '',
          ),
          settings: settings,
        );
      case '/home':
        final args = _readRouteArgs(settings);
        return MaterialPageRoute(
          builder: (_) => HomeScreen(
            userId: args['userId']?.toString() ?? '',
            username: args['username']?.toString() ?? 'User',
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
