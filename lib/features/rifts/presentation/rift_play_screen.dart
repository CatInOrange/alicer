import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../settings/domain/app_settings.dart';
import '../data/rift_repository.dart';
import '../domain/rift_models.dart';

class RiftPlayScreen extends StatefulWidget {
  const RiftPlayScreen({
    super.key,
    required this.settings,
    this.scenarioId,
    this.initialDetail,
  });

  final AlicerSettings settings;
  final String? scenarioId;
  final RiftDetail? initialDetail;

  @override
  State<RiftPlayScreen> createState() => _RiftPlayScreenState();
}

class _RiftPlayScreenState extends State<RiftPlayScreen> {
  late final RiftRepository _repository;
  RiftDetail? _detail;
  bool _loading = true;
  bool _choosing = false;
  String _error = '';

  @override
  void initState() {
    super.initState();
    _repository = RiftRepository(settings: widget.settings);
    final initial = widget.initialDetail;
    if (initial != null) {
      _detail = initial;
      _loading = false;
    } else {
      _load();
    }
  }

  Future<void> _load() async {
    final id = widget.scenarioId;
    if (id == null) return;
    setState(() {
      _loading = true;
      _error = '';
    });
    try {
      final detail = await _repository.getRift(id);
      if (!mounted) return;
      setState(() {
        _detail = detail;
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

  Future<void> _choose(RiftChoice choice) async {
    final scenario = _detail?.scenario;
    if (scenario == null) return;
    setState(() => _choosing = true);
    try {
      final detail = await _repository.choose(scenario.id, choice.id);
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _choosing = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _choosing = false);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('裂隙推进失败：$error')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    return Scaffold(
      appBar: AppBar(title: Text(detail?.scenario.title ?? '时空裂隙')),
      body:
          _loading
              ? const Center(child: CircularProgressIndicator())
              : _error.isNotEmpty
              ? Center(child: Text(_error))
              : detail == null
              ? const Center(child: Text('裂隙不存在'))
              : _RiftBody(
                detail: detail,
                choosing: _choosing,
                onChoose: _choose,
              ),
    );
  }
}

class _RiftBody extends StatelessWidget {
  const _RiftBody({
    required this.detail,
    required this.choosing,
    required this.onChoose,
  });

  final RiftDetail detail;
  final bool choosing;
  final ValueChanged<RiftChoice> onChoose;

  @override
  Widget build(BuildContext context) {
    final scenario = detail.scenario;
    final colors = context.alicerColors;
    return Column(
      children: [
        _ScenarioHeader(scenario: scenario),
        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 18),
            itemCount: detail.events.length,
            separatorBuilder: (_, _) => const SizedBox(height: 12),
            itemBuilder:
                (context, index) => _EventCard(event: detail.events[index]),
          ),
        ),
        DecoratedBox(
          decoration: BoxDecoration(
            color: colors.surface,
            border: Border(top: BorderSide(color: colors.border)),
          ),
          child: SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
              child:
                  scenario.isEnded
                      ? Text(
                        '这条世界线已经抵达终点',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: colors.textSubtle,
                          fontWeight: FontWeight.w700,
                        ),
                      )
                      : Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (choosing)
                            const Padding(
                              padding: EdgeInsets.only(bottom: 10),
                              child: LinearProgressIndicator(),
                            ),
                          for (final choice in scenario.currentChoices) ...[
                            SizedBox(
                              width: double.infinity,
                              child: OutlinedButton(
                                onPressed:
                                    choosing ? null : () => onChoose(choice),
                                style: OutlinedButton.styleFrom(
                                  alignment: Alignment.centerLeft,
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 14,
                                    vertical: 12,
                                  ),
                                ),
                                child: Text('${choice.id}. ${choice.text}'),
                              ),
                            ),
                            const SizedBox(height: 8),
                          ],
                        ],
                      ),
            ),
          ),
        ),
      ],
    );
  }
}

class _ScenarioHeader extends StatelessWidget {
  const _ScenarioHeader({required this.scenario});

  final RiftScenario scenario;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border(bottom: BorderSide(color: colors.border)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                _HeaderChip(scenario.genre),
                _HeaderChip(scenario.surfaceRelation),
                _HeaderChip(scenario.intensity),
                _HeaderChip('第 ${scenario.turnCount} 轮'),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              '你：${scenario.userRole}',
              style: TextStyle(color: colors.text, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 4),
            Text(
              '她：${scenario.aiRole}',
              style: TextStyle(color: colors.textSubtle),
            ),
          ],
        ),
      ),
    );
  }
}

class _HeaderChip extends StatelessWidget {
  const _HeaderChip(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.1),
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

class _EventCard extends StatelessWidget {
  const _EventCard({required this.event});

  final RiftEvent event;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: event.isEnding ? colors.surfaceSoft : colors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: colors.border.withValues(alpha: 0.72)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (event.choiceText.isNotEmpty) ...[
              Text(
                '你选择：${event.choiceText}',
                style: TextStyle(
                  color: Theme.of(context).colorScheme.primary,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 10),
            ],
            if (event.sceneText.isNotEmpty)
              Text(
                event.sceneText,
                style: TextStyle(
                  color: colors.text,
                  height: 1.55,
                  fontSize: 15,
                ),
              ),
            if (event.aiDialogue.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(
                '“${event.aiDialogue}”',
                style: TextStyle(
                  color: colors.textSubtle,
                  height: 1.5,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
