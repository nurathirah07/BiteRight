import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:biteright_mobile/screens/home_screen.dart';
import 'screens/login_screen.dart';
import 'screens/profile_setup_screen.dart';
import 'screens/register_screen.dart';
import 'screens/welcome_screen.dart';
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