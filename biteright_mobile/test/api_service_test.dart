import 'dart:async';
import 'dart:io';

import 'package:biteright_mobile/services/api_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final api = ApiService();

  group('normalizeScanAnalysis', () {
    test('keeps the risk score consistent with the risk level', () {
      final safe = api.normalizeScanAnalysis({'risk_level': 'safe', 'risk_score': 80});
      expect(safe['risk_score'], lessThanOrEqualTo(25));

      final caution =
          api.normalizeScanAnalysis({'risk_level': 'caution', 'risk_score': 5});
      expect(caution['risk_score'], inInclusiveRange(26, 59));

      final unsafe =
          api.normalizeScanAnalysis({'risk_level': 'unsafe', 'risk_score': 10});
      expect(unsafe['risk_score'], greaterThanOrEqualTo(60));
    });

    test('reads nested analysis from pantry and barcode payloads', () {
      final result = api.normalizeScanAnalysis({
        'product_name': 'Acme - Spread',
        'analysis': {
          'risk_level': 'unsafe',
          'risk_score': 85,
          'ingredients': ['sugar', 'milk powder'],
          'alerts': ['milk powder contains Milk/Dairy'],
        },
      });
      expect(result['risk_level'], 'unsafe');
      expect(result['risk_score'], 85);
      expect(result['ingredients'], ['sugar', 'milk powder']);
      expect(result['product_name'], 'Acme - Spread');
    });

    test('converts percentage confidence to a fraction', () {
      final result =
          api.normalizeScanAnalysis({'risk_level': 'safe', 'confidence': 87});
      expect(result['confidence'], closeTo(0.87, 0.0001));
    });

    test('infers a level from alerts when the level is unknown', () {
      final result = api.normalizeScanAnalysis({
        'alerts': ['Peanut matches your Peanuts allergy'],
      });
      expect(result['risk_level'], 'unsafe');
    });

    test('is idempotent', () {
      final once = api.normalizeScanAnalysis({'risk_level': 'caution', 'risk_score': 40});
      final twice = api.normalizeScanAnalysis(once);
      expect(twice, once);
    });
  });

  group('friendlyError', () {
    test('uses the server message for ApiException', () {
      expect(ApiService.friendlyError(const ApiException('Email already used')),
          'Email already used');
    });

    test('explains timeouts and lost connections in plain words', () {
      expect(ApiService.friendlyError(TimeoutException('x')),
          contains('took too long'));
      expect(ApiService.friendlyError(const SocketException('x')),
          contains("Can't reach"));
    });
  });
}
