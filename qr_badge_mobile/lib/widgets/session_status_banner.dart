import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/session_provider.dart';
import '../theme/qr_badge_theme.dart';

/// Bandeau persistant affiché tant qu'une session de badgeage est ouverte.
class SessionStatusBanner extends StatelessWidget {
  const SessionStatusBanner({super.key});

  @override
  Widget build(BuildContext context) {
    final running = context.select<SessionProvider, bool>(
      (s) => s.isSecureHeartbeatRunning,
    );
    if (!running) {
      return const SizedBox.shrink();
    }
    final label = context.select<SessionProvider, String?>(
          (s) => s.openSessionChipLabel,
        ) ??
        'Session ouverte — suivi actif';
    return Material(
      color: AppColors.navIndicator,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        child: Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                color: AppColors.ciSuccessDark,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 10),
            Icon(Icons.sensors, size: 18, color: AppColors.ciSuccessDark),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                label,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: AppColors.ciSuccessDark.withValues(alpha: 0.95),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Chip compact pour l'écran Scanner.
class SessionStatusChip extends StatelessWidget {
  const SessionStatusChip({super.key});

  @override
  Widget build(BuildContext context) {
    final session = context.watch<SessionProvider>();
    if (!session.isSecureHeartbeatRunning) {
      return const SizedBox.shrink();
    }
    final label = session.openSessionChipLabel ?? 'Session ouverte';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.navIndicator,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppColors.ciSuccessDark.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: const BoxDecoration(
              color: AppColors.ciSuccessDark,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 6),
          Text(
            label,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: AppColors.ciSuccessDark,
                ),
          ),
        ],
      ),
    );
  }
}
