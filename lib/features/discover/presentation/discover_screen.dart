import 'dart:async';

import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../rifts/presentation/rift_list_screen.dart';
import '../../time/data/moment_unread_tracker.dart';
import '../../time/presentation/time_screen.dart';

class DiscoverScreen extends StatefulWidget {
  const DiscoverScreen({super.key});

  @override
  State<DiscoverScreen> createState() => _DiscoverScreenState();
}

class _DiscoverScreenState extends State<DiscoverScreen> {
  @override
  void initState() {
    super.initState();
    MomentUnreadTracker.instance.addListener(_onUnreadChanged);
    Future<void>.microtask(MomentUnreadTracker.instance.refresh);
  }

  @override
  void dispose() {
    MomentUnreadTracker.instance.removeListener(_onUnreadChanged);
    super.dispose();
  }

  void _onUnreadChanged() {
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    final hasUnreadMoments = MomentUnreadTracker.instance.hasUnread;
    return Scaffold(
      appBar: AppBar(title: const Text('发现')),
      body: ListView(
        padding: const EdgeInsets.symmetric(vertical: 14),
        children: [
          _DiscoverGroup(
            children: [
              _DiscoverTile(
                icon: Icons.photo_camera_back_outlined,
                label: '朋友圈',
                showBadge: hasUnreadMoments,
                onTap: () {
                  unawaited(_openMoments(context));
                },
              ),
            ],
          ),
          const SizedBox(height: 12),
          _DiscoverGroup(
            children: [
              _DiscoverTile(
                icon: Icons.blur_circular_outlined,
                label: '时空裂隙',
                subtitle: '进入平行副本，选择推进命运',
                onTap:
                    () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (context) => const RiftListScreen(),
                      ),
                    ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          _DiscoverGroup(
            children: [
              _DiscoverTile(
                icon: Icons.auto_stories_outlined,
                label: '时光轮',
                onTap:
                    () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (context) => const TimeScreen(),
                      ),
                    ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Divider(height: 1, color: colors.border),
        ],
      ),
    );
  }

  Future<void> _openMoments(BuildContext context) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (context) => const MomentsScreen()),
    );
    if (!context.mounted) return;
    await MomentUnreadTracker.instance.refresh();
  }
}

class _DiscoverGroup extends StatelessWidget {
  const _DiscoverGroup({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.symmetric(
          horizontal: BorderSide(color: colors.border.withValues(alpha: 0.72)),
        ),
      ),
      child: Column(mainAxisSize: MainAxisSize.min, children: children),
    );
  }
}

class _DiscoverTile extends StatelessWidget {
  const _DiscoverTile({
    required this.icon,
    required this.label,
    this.subtitle = '',
    this.showBadge = false,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final String subtitle;
  final bool showBadge;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    final theme = Theme.of(context);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(18, 14, 16, 14),
          child: Row(
            children: [
              Stack(
                clipBehavior: Clip.none,
                children: [
                  Container(
                    width: 34,
                    height: 34,
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Icon(
                      icon,
                      color: theme.colorScheme.primary,
                      size: 21,
                    ),
                  ),
                  if (showBadge)
                    Positioned(
                      right: -2,
                      top: -2,
                      child: Container(
                        width: 9,
                        height: 9,
                        decoration: BoxDecoration(
                          color: theme.colorScheme.error,
                          shape: BoxShape.circle,
                          border: Border.all(color: colors.surface, width: 1.5),
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      label,
                      style: TextStyle(
                        color: colors.text,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (subtitle.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(
                        subtitle,
                        style: TextStyle(color: colors.textMuted, fontSize: 12),
                      ),
                    ],
                  ],
                ),
              ),
              Icon(Icons.chevron_right_rounded, color: colors.textMuted),
            ],
          ),
        ),
      ),
    );
  }
}
