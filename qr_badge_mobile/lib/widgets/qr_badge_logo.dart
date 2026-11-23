import 'package:flutter/material.dart';

import '../theme/qr_badge_theme.dart';

/// Logo bouclier + QR (aligné visuels Play Store).
class QrBadgeLogo extends StatelessWidget {
  const QrBadgeLogo({
    super.key,
    this.size = 48,
    this.color = AppColors.ciSuccessDark,
    this.backgroundColor,
  });

  final double size;
  final Color color;
  final Color? backgroundColor;

  @override
  Widget build(BuildContext context) {
    final icon = Icon(
      Icons.verified_user_outlined,
      color: color,
      size: size * 0.55,
    );
    if (backgroundColor == null) {
      return icon;
    }
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: backgroundColor,
        shape: BoxShape.circle,
      ),
      child: Center(child: icon),
    );
  }
}
