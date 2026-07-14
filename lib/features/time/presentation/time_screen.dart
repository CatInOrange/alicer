import 'package:flutter/material.dart';

import '../../../app/theme.dart';

class TimeScreen extends StatelessWidget {
  const TimeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('时光'),
          actions: [
            IconButton(
              tooltip: '新建记录',
              onPressed: () {},
              icon: const Icon(Icons.add),
            ),
          ],
          bottom: const TabBar(
            tabs: [Tab(text: '日记'), Tab(text: '周记'), Tab(text: '月记')],
          ),
        ),
        body: const TabBarView(
          children: [
            _TimelineList(kind: _TimeKind.day),
            _TimelineList(kind: _TimeKind.week),
            _TimelineList(kind: _TimeKind.month),
          ],
        ),
      ),
    );
  }
}

enum _TimeKind { day, week, month }

class _TimelineList extends StatelessWidget {
  const _TimelineList({required this.kind});

  final _TimeKind kind;

  @override
  Widget build(BuildContext context) {
    final items = switch (kind) {
      _TimeKind.day => const [
        _TimeEntry(
          title: '今天我们开始设计 Alicer',
          subtitle: '聊天入口、时光页、提示词配置工作台',
          meta: '今日 · 温暖',
          icon: Icons.wb_sunny_outlined,
        ),
        _TimeEntry(
          title: '她记住了你的产品偏好',
          subtitle: '不要通讯录，第一屏直接聊天；设置页要像酒馆但更轻。',
          meta: '昨天 · 专注',
          icon: Icons.memory_outlined,
        ),
      ],
      _TimeKind.week => const [
        _TimeEntry(
          title: '这一周的关系摘要',
          subtitle: '重点围绕新 App、伴侣体验、记忆沉淀和长期陪伴感展开。',
          meta: '第 29 周',
          icon: Icons.calendar_view_week_outlined,
        ),
      ],
      _TimeKind.month => const [
        _TimeEntry(
          title: '七月陪伴月记',
          subtitle: '把每周的重要回忆整理成更有仪式感的月度记录。',
          meta: '2026 年 7 月',
          icon: Icons.calendar_month_outlined,
        ),
      ],
    };

    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemBuilder: (context, index) => _TimeCard(entry: items[index]),
      separatorBuilder: (_, _) => const SizedBox(height: 12),
      itemCount: items.length,
    );
  }
}

class _TimeEntry {
  const _TimeEntry({
    required this.title,
    required this.subtitle,
    required this.meta,
    required this.icon,
  });

  final String title;
  final String subtitle;
  final String meta;
  final IconData icon;
}

class _TimeCard extends StatelessWidget {
  const _TimeCard({required this.entry});

  final _TimeEntry entry;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;

    return Container(
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: colors.border),
        boxShadow: [
          BoxShadow(
            color: colors.shadow,
            blurRadius: 16,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      padding: const EdgeInsets.all(14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: Theme.of(
                context,
              ).colorScheme.primary.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              entry.icon,
              color: Theme.of(context).colorScheme.primary,
              size: 20,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(entry.meta, style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 5),
                Text(
                  entry.title,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 6),
                Text(entry.subtitle),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
