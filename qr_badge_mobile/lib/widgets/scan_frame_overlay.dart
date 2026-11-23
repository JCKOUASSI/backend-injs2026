import 'package:flutter/material.dart';

import '../theme/qr_badge_theme.dart';

/// Cadre de scan avec coins verts (visuel Play Store).
class ScanFrameOverlay extends StatelessWidget {
  const ScanFrameOverlay({super.key});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final w = constraints.maxWidth * 0.72;
        final h = w * 0.85;
        return Center(
          child: SizedBox(
            width: w,
            height: h,
            child: Stack(
              children: [
                Container(
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.35),
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                ..._corners(w, h),
              ],
            ),
          ),
        );
      },
    );
  }

  List<Widget> _corners(double w, double h) {
    const len = 28.0;
    const thick = 4.0;
    const color = AppColors.ciSuccess;
    Widget corner(Alignment align, {bool top = true, bool left = true}) {
      return Align(
        alignment: align,
        child: SizedBox(
          width: len,
          height: len,
          child: CustomPaint(
            painter: _CornerPainter(
              color: color,
              strokeWidth: thick,
              top: top,
              left: left,
            ),
          ),
        ),
      );
    }

    return [
      corner(Alignment.topLeft, top: true, left: true),
      corner(Alignment.topRight, top: true, left: false),
      corner(Alignment.bottomLeft, top: false, left: true),
      corner(Alignment.bottomRight, top: false, left: false),
    ];
  }
}

class _CornerPainter extends CustomPainter {
  _CornerPainter({
    required this.color,
    required this.strokeWidth,
    required this.top,
    required this.left,
  });

  final Color color;
  final double strokeWidth;
  final bool top;
  final bool left;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = strokeWidth
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    final path = Path();
    if (top && left) {
      path.moveTo(0, size.height * 0.35);
      path.lineTo(0, 0);
      path.lineTo(size.width * 0.35, 0);
    } else if (top && !left) {
      path.moveTo(size.width, size.height * 0.35);
      path.lineTo(size.width, 0);
      path.lineTo(size.width * 0.65, 0);
    } else if (!top && left) {
      path.moveTo(0, size.height * 0.65);
      path.lineTo(0, size.height);
      path.lineTo(size.width * 0.35, size.height);
    } else {
      path.moveTo(size.width, size.height * 0.65);
      path.lineTo(size.width, size.height);
      path.lineTo(size.width * 0.65, size.height);
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
