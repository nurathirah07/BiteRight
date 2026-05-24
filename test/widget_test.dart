// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter_test/flutter_test.dart';

import 'package:biteright_mobile/main.dart';

void main() {
  testWidgets('shows the BiteRight welcome screen', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp(checkBackendOnStartup: false));

    expect(find.text('BiteRight'), findsOneWidget);
    expect(find.text('Scan food labels with confidence'), findsOneWidget);
    expect(find.text('Create safety profile'), findsOneWidget);
  });
}
