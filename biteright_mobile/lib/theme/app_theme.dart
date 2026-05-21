import 'package:flutter/material.dart';

class AppTheme {
  static const Color primary = Color(0xFFFF6B4A);
  static const Color primaryDark = Color(0xFF17211D);
  static const Color accent = Color(0xFFBCEB7D);
  static const Color teal = Color(0xFF0F7B68);
  static const Color blue = Color(0xFF2563A8);
  static const Color background = Color(0xFFF6F1E8);
  static const Color surface = Color(0xFFFFFCF6);
  static const Color surfaceAlt = Color(0xFFEFE8DA);
  static const Color border = Color(0xFFE2D8C9);
  static const Color text = Color(0xFF1B1A17);
  static const Color textMuted = Color(0xFF706A5F);

  static const Color safe = Color(0xFF54792D);
  static const Color safeBg = Color(0xFFEAF5C7);
  static const Color caution = Color(0xFFB86B19);
  static const Color cautionBg = Color(0xFFFFE5BC);
  static const Color unsafe = Color(0xFFB83A32);
  static const Color unsafeBg = Color(0xFFFFD9D3);

  static const double radius = 12;

  static ThemeData get theme {
    return ThemeData(
      colorScheme: ColorScheme.fromSeed(
        seedColor: primary,
        primary: primary,
        secondary: teal,
        tertiary: blue,
        surface: surface,
        error: unsafe,
      ),
      scaffoldBackgroundColor: background,
      useMaterial3: true,
      fontFamily: 'Roboto',
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        foregroundColor: text,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          color: text,
          fontSize: 15,
          fontWeight: FontWeight.w500,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primary,
          foregroundColor: Colors.white,
          elevation: 0,
          minimumSize: const Size.fromHeight(50),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: primaryDark,
          side: const BorderSide(color: Color(0xFFE4D8B8)),
          minimumSize: const Size.fromHeight(48),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: primary, width: 1.6),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: unsafe),
        ),
        labelStyle: const TextStyle(color: textMuted, fontSize: 13),
        hintStyle: const TextStyle(color: textMuted, fontSize: 13),
      ),
      cardTheme: CardThemeData(
        color: surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radius),
          side: const BorderSide(color: border, width: 0.7),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: surface,
        selectedColor: accent,
        labelStyle: const TextStyle(color: text, fontSize: 12),
        secondaryLabelStyle: const TextStyle(color: primaryDark, fontSize: 12),
        side: const BorderSide(color: border, width: 0.5),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
        ),
      ),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: Colors.white,
        selectedItemColor: primary,
        unselectedItemColor: textMuted,
        elevation: 0,
        type: BottomNavigationBarType.fixed,
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        elevation: 0,
        backgroundColor: primaryDark,
        contentTextStyle: const TextStyle(color: Colors.white, fontSize: 13),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  static const LinearGradient warmGradient = LinearGradient(
    colors: [
      Color(0xFFFFF7E8),
      Color(0xFFFFE7DC),
      Color(0xFFE7F4D1),
    ],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const LinearGradient cardGradient = LinearGradient(
    colors: [
      Color(0xFFFFF5E2),
      Color(0xFFE6F7C8),
      Color(0xFFE7F1FF),
    ],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static Color riskColor(String riskLevel) {
    switch (riskLevel) {
      case 'safe':
        return safe;
      case 'caution':
        return caution;
      case 'unsafe':
        return unsafe;
      default:
        return textMuted;
    }
  }

  static Color riskBg(String riskLevel) {
    switch (riskLevel) {
      case 'safe':
        return safeBg;
      case 'caution':
        return cautionBg;
      case 'unsafe':
        return unsafeBg;
      default:
        return surface;
    }
  }
}

class SectionLabel extends StatelessWidget {
  final String text;

  const SectionLabel(this.text, {super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 16, bottom: 8),
      child: Text(
        text.toUpperCase(),
        style: const TextStyle(
          color: AppTheme.textMuted,
          fontSize: 11,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.5,
        ),
      ),
    );
  }
}

class RiskBadge extends StatelessWidget {
  final String riskLevel;

  const RiskBadge(this.riskLevel, {super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: AppTheme.riskBg(riskLevel),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        riskLevel.toUpperCase(),
        style: TextStyle(
          color: AppTheme.riskColor(riskLevel),
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
