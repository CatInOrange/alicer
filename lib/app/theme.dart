import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

String? _desktopFontFamily() {
  if (kIsWeb) return null;
  if (Platform.isWindows) return 'Microsoft YaHei UI';
  if (Platform.isMacOS) return 'PingFang SC';
  if (Platform.isLinux) return 'Noto Sans CJK SC';
  return null;
}

ThemeData buildAlicerTheme({Brightness brightness = Brightness.light}) {
  const seed = Color(0xFF0EA5E9);
  final isDark = brightness == Brightness.dark;
  final colors = isDark ? AlicerColors.dark() : AlicerColors.light();
  final colorScheme = ColorScheme.fromSeed(
    seedColor: seed,
    brightness: brightness,
  );

  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    fontFamily: _desktopFontFamily(),
    colorScheme: colorScheme,
    scaffoldBackgroundColor: colors.background,
    cardColor: colors.surface,
    dividerColor: colors.border,
    extensions: <ThemeExtension<dynamic>>[colors],
    appBarTheme: AppBarTheme(
      backgroundColor: colors.background,
      foregroundColor: colors.text,
      elevation: 0,
      centerTitle: false,
      scrolledUnderElevation: 0,
      surfaceTintColor: Colors.transparent,
      titleTextStyle: TextStyle(
        color: colors.text,
        fontSize: 18,
        fontWeight: FontWeight.w700,
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: colors.surface,
      indicatorColor: seed.withValues(alpha: isDark ? 0.24 : 0.14),
      labelTextStyle: WidgetStateProperty.resolveWith(
        (states) => TextStyle(
          fontSize: 12,
          fontWeight:
              states.contains(WidgetState.selected)
                  ? FontWeight.w700
                  : FontWeight.w500,
        ),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: colors.inputBackground,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide.none,
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide.none,
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(
          color: colorScheme.primary.withValues(alpha: 0.2),
        ),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
    ),
    textTheme: TextTheme(
      titleLarge: TextStyle(
        color: colors.text,
        fontSize: 19,
        fontWeight: FontWeight.w700,
      ),
      titleMedium: TextStyle(
        color: colors.text,
        fontSize: 16,
        fontWeight: FontWeight.w700,
      ),
      bodyLarge: TextStyle(color: colors.text, fontSize: 15, height: 1.45),
      bodyMedium: TextStyle(
        color: colors.textSubtle,
        fontSize: 14,
        height: 1.4,
      ),
      bodySmall: TextStyle(color: colors.textMuted, fontSize: 12, height: 1.3),
    ),
  );
}

extension AlicerThemeX on BuildContext {
  AlicerColors get alicerColors =>
      Theme.of(this).extension<AlicerColors>() ?? AlicerColors.light();
}

class AlicerColors extends ThemeExtension<AlicerColors> {
  const AlicerColors({
    required this.background,
    required this.surface,
    required this.surfaceSoft,
    required this.inputBackground,
    required this.border,
    required this.text,
    required this.textSubtle,
    required this.textMuted,
    required this.userBubble,
    required this.userBubbleText,
    required this.companionBubble,
    required this.shadow,
  });

  factory AlicerColors.light() {
    return const AlicerColors(
      background: Color(0xFFF4FAFF),
      surface: Color(0xFFFFFFFF),
      surfaceSoft: Color(0xFFEAF6FF),
      inputBackground: Color(0xFFF7FBFF),
      border: Color(0xFFD5E8F6),
      text: Color(0xFF132536),
      textSubtle: Color(0xFF40566A),
      textMuted: Color(0xFF7890A3),
      userBubble: Color(0xFF0284C7),
      userBubbleText: Colors.white,
      companionBubble: Color(0xFFEFF8FF),
      shadow: Color(0x14132536),
    );
  }

  factory AlicerColors.dark() {
    return const AlicerColors(
      background: Color(0xFF07141F),
      surface: Color(0xFF0E2130),
      surfaceSoft: Color(0xFF163247),
      inputBackground: Color(0xFF122A3D),
      border: Color(0xFF24445A),
      text: Color(0xFFEAF6FF),
      textSubtle: Color(0xFFC4D9EA),
      textMuted: Color(0xFF8EADC3),
      userBubble: Color(0xFF38BDF8),
      userBubbleText: Color(0xFF062033),
      companionBubble: Color(0xFF12304A),
      shadow: Color(0x66000000),
    );
  }

  final Color background;
  final Color surface;
  final Color surfaceSoft;
  final Color inputBackground;
  final Color border;
  final Color text;
  final Color textSubtle;
  final Color textMuted;
  final Color userBubble;
  final Color userBubbleText;
  final Color companionBubble;
  final Color shadow;

  @override
  AlicerColors copyWith({
    Color? background,
    Color? surface,
    Color? surfaceSoft,
    Color? inputBackground,
    Color? border,
    Color? text,
    Color? textSubtle,
    Color? textMuted,
    Color? userBubble,
    Color? userBubbleText,
    Color? companionBubble,
    Color? shadow,
  }) {
    return AlicerColors(
      background: background ?? this.background,
      surface: surface ?? this.surface,
      surfaceSoft: surfaceSoft ?? this.surfaceSoft,
      inputBackground: inputBackground ?? this.inputBackground,
      border: border ?? this.border,
      text: text ?? this.text,
      textSubtle: textSubtle ?? this.textSubtle,
      textMuted: textMuted ?? this.textMuted,
      userBubble: userBubble ?? this.userBubble,
      userBubbleText: userBubbleText ?? this.userBubbleText,
      companionBubble: companionBubble ?? this.companionBubble,
      shadow: shadow ?? this.shadow,
    );
  }

  @override
  AlicerColors lerp(ThemeExtension<AlicerColors>? other, double t) {
    if (other is! AlicerColors) return this;
    return AlicerColors(
      background: Color.lerp(background, other.background, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      surfaceSoft: Color.lerp(surfaceSoft, other.surfaceSoft, t)!,
      inputBackground: Color.lerp(inputBackground, other.inputBackground, t)!,
      border: Color.lerp(border, other.border, t)!,
      text: Color.lerp(text, other.text, t)!,
      textSubtle: Color.lerp(textSubtle, other.textSubtle, t)!,
      textMuted: Color.lerp(textMuted, other.textMuted, t)!,
      userBubble: Color.lerp(userBubble, other.userBubble, t)!,
      userBubbleText: Color.lerp(userBubbleText, other.userBubbleText, t)!,
      companionBubble: Color.lerp(companionBubble, other.companionBubble, t)!,
      shadow: Color.lerp(shadow, other.shadow, t)!,
    );
  }
}
