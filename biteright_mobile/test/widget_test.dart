import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:biteright_mobile/main.dart';

void main() {
  setUp(() {
    // Mock SharedPreferences values for testing environment
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('BiteRight App startup smoke test', (WidgetTester tester) async {
    // Build our app
    await tester.pumpWidget(const MyApp(checkBackendOnStartup: false));

    // Render the initial frame of the WelcomeScreen directly
    await tester.pump();

    // Allow the WelcomeScreen's first frame to render
    await tester.pump(const Duration(milliseconds: 100));

    // Verify that we are directly on the welcome screen
    expect(find.text('BiteRight'), findsAtLeastNWidgets(1));
    expect(find.text('Scan food labels with confidence'), findsOneWidget);
    expect(find.text('Create safety profile'), findsOneWidget);
    expect(find.text('I already have an account'), findsOneWidget);
  });
}
