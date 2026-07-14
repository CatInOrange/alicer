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
  const seed = Color(0xFF7C4DFF);
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
      indicatorColor: seed.withValues(alpha: isDark ? 0.22 : 0.12),
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
      background: Color(0xFFF6F7FB),
      surface: Colors.white,
      surfaceSoft: Color(0xFFF0F2F7),
      inputBackground: Colors.white,
      border: Color(0xFFE5E8F0),
      text: Color(0xFF1F2430),
      textSubtle: Color(0xFF4B5568),
      textMuted: Color(0xFF98A1B3),
      userBubble: Color(0xFF6D4AFF),
      userBubbleText: Colors.white,
      companionBubble: Colors.white,
      shadow: Color(0x121F2430),
    );
  }

  factory AlicerColors.dark() {
    return const AlicerColors(
      background: Color(0xFF111318),
      surface: Color(0xFF1B1E26),
      surfaceSoft: Color(0xFF242936),
      inputBackground: Color(0xFF20242D),
      border: Color(0xFF303644),
      text: Color(0xFFE8ECF5),
      textSubtle: Color(0xFFC5CAD8),
      textMuted: Color(0xFF8F98AA),
      userBubble: Color(0xFF5C4BCB),
      userBubbleText: Color(0xFFF8F7FF),
      companionBubble: Color(0xFF20242D),
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
