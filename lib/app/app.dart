import 'dart:async';

import 'package:flutter/material.dart';

import '../features/chat/presentation/chat_screen.dart';
import '../features/discover/presentation/discover_screen.dart';
import '../features/settings/presentation/settings_screen.dart';
import '../features/time/data/moment_unread_tracker.dart';
import 'theme.dart';

class AlicerApp extends StatelessWidget {
  const AlicerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Alicer',
      theme: buildAlicerTheme(),
      darkTheme: buildAlicerTheme(brightness: Brightness.dark),
      debugShowCheckedModeBanner: false,
      home: const AlicerShell(),
    );
  }
}

class AlicerShell extends StatefulWidget {
  const AlicerShell({super.key});

  @override
  State<AlicerShell> createState() => _AlicerShellState();
}

class _AlicerShellState extends State<AlicerShell> with WidgetsBindingObserver {
  int _currentIndex = 0;

  static const _pages = <Widget>[
    ChatScreen(),
    DiscoverScreen(),
    SettingsScreen(),
  ];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    MomentUnreadTracker.instance.addListener(_onMomentUnreadChanged);
    unawaited(MomentUnreadTracker.instance.refresh());
  }

  @override
  void dispose() {
    MomentUnreadTracker.instance.removeListener(_onMomentUnreadChanged);
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(MomentUnreadTracker.instance.refresh());
    }
  }

  void _onMomentUnreadChanged() {
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final hasUnreadMoments = MomentUnreadTracker.instance.hasUnread;
    return Scaffold(
      body: IndexedStack(index: _currentIndex, children: _pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _currentIndex,
        onDestinationSelected: (index) {
          setState(() => _currentIndex = index);
          if (index == 1) unawaited(MomentUnreadTracker.instance.refresh());
        },
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.chat_bubble_outline),
            selectedIcon: Icon(Icons.chat_bubble),
            label: '聊天',
          ),
          NavigationDestination(
            icon: _NavBadge(
              show: hasUnreadMoments,
              child: const Icon(Icons.explore_outlined),
            ),
            selectedIcon: _NavBadge(
              show: hasUnreadMoments,
              child: const Icon(Icons.explore),
            ),
            label: '发现',
          ),
          const NavigationDestination(
            icon: Icon(Icons.tune_outlined),
            selectedIcon: Icon(Icons.tune),
            label: '配置',
          ),
        ],
      ),
    );
  }
}

class _NavBadge extends StatelessWidget {
  const _NavBadge({required this.show, required this.child});

  final bool show;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        child,
        if (show)
          Positioned(
            right: -2,
            top: -2,
            child: Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.error,
                shape: BoxShape.circle,
              ),
            ),
          ),
      ],
    );
  }
}
