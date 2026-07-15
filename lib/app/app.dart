import 'package:flutter/material.dart';

import '../features/chat/presentation/chat_screen.dart';
import '../features/discover/presentation/discover_screen.dart';
import '../features/settings/presentation/settings_screen.dart';
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

class _AlicerShellState extends State<AlicerShell> {
  int _currentIndex = 0;

  static const _pages = <Widget>[
    ChatScreen(),
    DiscoverScreen(),
    SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _currentIndex, children: _pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _currentIndex,
        onDestinationSelected: (index) => setState(() => _currentIndex = index),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.chat_bubble_outline),
            selectedIcon: Icon(Icons.chat_bubble),
            label: '聊天',
          ),
          NavigationDestination(
            icon: Icon(Icons.explore_outlined),
            selectedIcon: Icon(Icons.explore),
            label: '发现',
          ),
          NavigationDestination(
            icon: Icon(Icons.tune_outlined),
            selectedIcon: Icon(Icons.tune),
            label: '配置',
          ),
        ],
      ),
    );
  }
}
