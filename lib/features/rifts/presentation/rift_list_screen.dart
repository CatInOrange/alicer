import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../settings/data/settings_store.dart';
import '../../settings/domain/app_settings.dart';
import '../data/rift_repository.dart';
import '../domain/rift_models.dart';
import 'rift_create_screen.dart';
import 'rift_play_screen.dart';

class RiftListScreen extends StatefulWidget {
  const RiftListScreen({super.key});

  @override
  State<RiftListScreen> createState() => _RiftListScreenState();
}

class _RiftListScreenState extends State<RiftListScreen> {
  AlicerSettings _settings = const AlicerSettings();
  List<RiftScenario> _rifts = const [];
  bool _loading = true;
  String _error = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = '';
    });
    try {
      final settings = await SettingsStore.load();
      final rifts = await RiftRepository(settings: settings).listRifts();
      if (!mounted) return;
      setState(() {
        _settings = settings;
        _rifts = rifts;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString();
        _loading = false;
      });
    }
  }

  Future<void> _create() async {
    final detail = await Navigator.of(context).push<RiftDetail>(
      MaterialPageRoute(
        builder: (context) => RiftCreateScreen(settings: _settings),
      ),
    );
    if (!mounted || detail == null) return;
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder:
            (context) =>
                RiftPlayScreen(settings: _settings, initialDetail: detail),
      ),
    );
    _load();
  }

  Future<void> _open(RiftScenario scenario) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder:
            (context) =>
                RiftPlayScreen(settings: _settings, scenarioId: scenario.id),
      ),
    );
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Scaffold(
      appBar: AppBar(title: const Text('时空裂隙')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _create,
        icon: const Icon(Icons.auto_awesome_rounded),
        label: const Text('开启裂隙'),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child:
            _loading
                ? const Center(child: CircularProgressIndicator())
                : _error.isNotEmpty
                ? ListView(
                  padding: const EdgeInsets.all(24),
                  children: [
                    Text('裂隙暂时无法打开：$_error'),
                    const SizedBox(height: 12),
                    FilledButton(onPressed: _load, child: const Text('重试')),
                  ],
                )
                : _rifts.isEmpty
                ? ListView(
                  padding: const EdgeInsets.fromLTRB(22, 42, 22, 120),
                  children: [
                    Icon(
                      Icons.blur_circular_rounded,
                      color: colors.textMuted,
                      size: 44,
                    ),
                    const SizedBox(height: 14),
                    Text(
                      '还没有裂隙',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '选择一个世界和身份关系，剩下的交给命运重写。',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: colors.textSubtle),
                    ),
                  ],
                )
                : ListView.separated(
                  padding: const EdgeInsets.fromLTRB(14, 14, 14, 96),
                  itemCount: _rifts.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 10),
                  itemBuilder: (context, index) {
                    final rift = _rifts[index];
                    return _RiftCard(rift: rift, onTap: () => _open(rift));
                  },
                ),
      ),
    );
  }
}

class _RiftCard extends StatelessWidget {
  const _RiftCard({required this.rift, required this.onTap});

  final RiftScenario rift;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Material(
      color: colors.surface,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      rift.title,
                      style: const TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                  _StatusPill(ended: rift.isEnded),
                ],
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  _MiniChip(rift.genre),
                  _MiniChip(rift.surfaceRelation),
                  _MiniChip(rift.intensity),
                  _MiniChip('第 ${rift.turnCount} 轮'),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                rift.summary.isEmpty ? rift.coreConflict : rift.summary,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: colors.textSubtle, height: 1.35),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MiniChip extends StatelessWidget {
  const _MiniChip(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surfaceSoft,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
        child: Text(
          label,
          style: TextStyle(color: colors.textSubtle, fontSize: 12),
        ),
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.ended});

  final bool ended;

  @override
  Widget build(BuildContext context) {
    final color =
        ended
            ? context.alicerColors.textMuted
            : Theme.of(context).colorScheme.primary;
    return Text(
      ended ? '已完结' : '进行中',
      style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w700),
    );
  }
}
