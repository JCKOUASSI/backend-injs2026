import 'package:flutter/material.dart';

abstract final class AppColors {
  // Aligné sur `frontend/src/index.css` (:root --ci-*)
  static const Color ciWarning = Color(0xFFF5B100);
  static const Color ciWarningDark = Color(0xFFE69700);
  static const Color ciSuccess = Color(0xFF2277C1);
  static const Color ciSuccessDark = Color(0xFF1A68AC);
  static const Color ciWhite = Color(0xFFFFFFFF);
  static const Color ciLight = Color(0xFFFFFBF0);

  static const Color ciDanger = Color(0xFFC62828);
  static const Color ciBlue = Color(0xFF1565C0);
  static const Color ciPurple = Color(0xFF7B1FA2);

  static const Color textPrimary = Color(0xFF1E293B);
  static const Color textSecondary = Color(0xFF64748B);
  static const Color borderColor = Color(0xFFE2E8F0);

  // Aliases (compat) — éviter des changements en cascade dans les pages.
  static const Color textMuted = textSecondary;
  static const Color accentWarning = ciWarning;

  // Surfaces
  static const Color cardBg = ciWhite;
  static const Color cardCream = ciLight;
  static const Color cardGrey = Color(0xFFF7FAFC);

  // Accents utilisés dans l’app mobile
  static const Color navIndicator = Color(0xFFE8EFF5);
  static const Color badgeWarningBg = Color(0xFFFFF8E0);
  static const Color badgeWarningFg = ciWarningDark;
  static const Color iconQrBg = Color(0xFFE8EFF5);
}

ThemeData buildQrBadgeTheme() {
  const seed = AppColors.ciSuccessDark;
  final scheme = ColorScheme.fromSeed(
    seedColor: seed,
    primary: AppColors.ciSuccessDark,
    secondary: AppColors.ciWarning,
    error: AppColors.ciDanger,
    brightness: Brightness.light,
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: AppColors.ciLight,
    dividerColor: AppColors.borderColor,
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.ciSuccessDark,
      foregroundColor: Colors.white,
      elevation: 0,
      centerTitle: true,
      titleTextStyle: TextStyle(
        color: Colors.white,
        fontSize: 20,
        fontWeight: FontWeight.w600,
      ),
      iconTheme: IconThemeData(color: Colors.white),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: AppColors.ciWhite,
      indicatorColor: AppColors.navIndicator,
      labelTextStyle: WidgetStateProperty.resolveWith((states) {
        final selected = states.contains(WidgetState.selected);
        return TextStyle(
          fontSize: 12,
          fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
          color: selected ? AppColors.ciSuccessDark : AppColors.textSecondary,
        );
      }),
      iconTheme: WidgetStateProperty.resolveWith((states) {
        final selected = states.contains(WidgetState.selected);
        return IconThemeData(
          color: selected ? AppColors.ciSuccessDark : AppColors.textSecondary,
          size: 24,
        );
      }),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.ciWhite,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.borderColor),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.borderColor),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.ciWarning, width: 2),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.ciWarning,
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        elevation: 0,
      ),
    ),
  );
}
