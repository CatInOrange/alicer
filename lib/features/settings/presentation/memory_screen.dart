import 'dart:async';

import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../data/memory_repository.dart';
import '../data/settings_store.dart';
import '../domain/app_settings.dart';
import '../domain/memory_models.dart';

class MemoryScreen extends StatefulWidget {
  const MemoryScreen({super.key});

  @override
  State<MemoryScreen> createState() => _MemoryScreenState();
}

class _MemoryScreenState extends State<MemoryScreen> {
  final _queryController = TextEditingController();
  AlicerSettings _settings = const AlicerSettings();
  List<CompanionMemory> _memories = const <CompanionMemory>[];
  String _status = 'active';
  int _pendingQueue = 0;
  bool _isLoading = true;
  bool _isProcessing = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _queryController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final settings = await SettingsStore.load();
    if (!mounted) return;
    setState(() {
      _settings = settings;
      _isLoading = true;
    });
    await _refresh(settings: settings);
  }

  Future<void> _refresh({AlicerSettings? settings}) async {
    try {
      final result = await MemoryRepository(
        settings: settings ?? _settings,
      ).listMemories(status: _status, query: _queryController.text);
      if (!mounted) return;
      setState(() {
        _memories = result.memories;
        _pendingQueue = result.pendingQueue;
        _isLoading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _isLoading = false);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('记忆读取失败：$error')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Scaffold(
      appBar: AppBar(
        title: const Text('记忆'),
        actions: [
          IconButton(
            tooltip: '整理队列',
            onPressed: _isProcessing ? null : _processQueue,
            icon:
                _isProcessing
                    ? const SizedBox.square(
                      dimension: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                    : const Icon(Icons.auto_fix_high_outlined),
          ),
          IconButton(
            tooltip: '新增记忆',
            onPressed: () => _editMemory(_draftMemory()),
            icon: const Icon(Icons.add_rounded),
          ),
        ],
      ),
      body: DecoratedBox(
        decoration: BoxDecoration(color: colors.background),
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 10),
              child: Column(
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _queryController,
                          decoration: InputDecoration(
                            prefixIcon: const Icon(Icons.search_rounded),
                            labelText: '搜索记忆',
                            suffixIcon:
                                _queryController.text.isEmpty
                                    ? null
                                    : IconButton(
                                      tooltip: '清空',
                                      onPressed: () {
                                        _queryController.clear();
                                        unawaited(_refresh());
                                      },
                                      icon: const Icon(Icons.close_rounded),
                                    ),
                          ),
                          onSubmitted: (_) => unawaited(_refresh()),
                        ),
                      ),
                      const SizedBox(width: 8),
                      IconButton.filledTonal(
                        tooltip: '搜索',
                        onPressed: () => unawaited(_refresh()),
                        icon: const Icon(Icons.arrow_forward_rounded),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: SegmentedButton<String>(
                      segments: const [
                        ButtonSegment(value: 'active', label: Text('启用')),
                        ButtonSegment(value: 'pending', label: Text('待确认')),
                        ButtonSegment(value: 'archived', label: Text('归档')),
                        ButtonSegment(value: 'all', label: Text('全部')),
                      ],
                      selected: {_status},
                      onSelectionChanged: (value) {
                        setState(() => _status = value.first);
                        unawaited(_refresh());
                      },
                    ),
                  ),
                  const SizedBox(height: 8),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      '队列 $_pendingQueue 条 · ${_memories.length} 条记忆',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child:
                  _isLoading
                      ? const Center(child: CircularProgressIndicator())
                      : RefreshIndicator(
                        onRefresh: _refresh,
                        child:
                            _memories.isEmpty
                                ? ListView(
                                  children: const [
                                    SizedBox(height: 120),
                                    Center(child: Text('这里还没有记忆')),
                                  ],
                                )
                                : ListView.separated(
                                  padding: const EdgeInsets.fromLTRB(
                                    16,
                                    0,
                                    16,
                                    24,
                                  ),
                                  itemCount: _memories.length,
                                  separatorBuilder:
                                      (_, __) => const SizedBox(height: 10),
                                  itemBuilder:
                                      (context, index) => _MemoryTile(
                                        memory: _memories[index],
                                        onEdit:
                                            () => _editMemory(_memories[index]),
                                        onArchive:
                                            () => _archiveMemory(
                                              _memories[index],
                                            ),
                                        onActivate:
                                            () => _saveMemory(
                                              _memories[index].copyWith(
                                                status: 'active',
                                                enabled: true,
                                              ),
                                            ),
                                      ),
                                ),
                      ),
            ),
          ],
        ),
      ),
    );
  }

  CompanionMemory _draftMemory() {
    final now = DateTime.now();
    return CompanionMemory(
      id: '',
      kind: 'fact',
      subject: 'user',
      content: '',
      summary: '',
      tags: const <String>[],
      confidence: 0.9,
      importance: 0.65,
      status: 'active',
      enabled: true,
      pinned: false,
      sensitive: false,
      createdAt: now,
      updatedAt: now,
    );
  }

  Future<void> _processQueue() async {
    setState(() => _isProcessing = true);
    try {
      await MemoryRepository(settings: _settings).processQueue();
      await _refresh();
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('记忆队列已整理')));
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('整理失败：$error')));
    } finally {
      if (mounted) setState(() => _isProcessing = false);
    }
  }

  Future<void> _archiveMemory(CompanionMemory memory) async {
    try {
      await MemoryRepository(settings: _settings).archiveMemory(memory.id);
      await _refresh();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('归档失败：$error')));
    }
  }

  Future<void> _saveMemory(CompanionMemory memory) async {
    try {
      final repo = MemoryRepository(settings: _settings);
      if (memory.id.isEmpty) {
        await repo.createMemory(memory);
      } else {
        await repo.updateMemory(memory);
      }
      await _refresh();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('保存失败：$error')));
    }
  }

  Future<void> _editMemory(CompanionMemory memory) async {
    final result = await showModalBottomSheet<CompanionMemory>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => _MemoryEditor(memory: memory),
    );
    if (result != null) {
      await _saveMemory(result);
    }
  }
}

class _MemoryTile extends StatelessWidget {
  const _MemoryTile({
    required this.memory,
    required this.onEdit,
    required this.onArchive,
    required this.onActivate,
  });

  final CompanionMemory memory;
  final VoidCallback onEdit;
  final VoidCallback onArchive;
  final VoidCallback onActivate;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: colors.border),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                _MemoryChip(
                  icon: Icons.label_outline_rounded,
                  label: memoryKindLabel(memory.kind),
                ),
                _MemoryChip(
                  icon: Icons.person_outline_rounded,
                  label: memorySubjectLabel(memory.subject),
                ),
                if (memory.status == 'pending')
                  const _MemoryChip(
                    icon: Icons.rate_review_outlined,
                    label: '待确认',
                  ),
                if (memory.pinned)
                  const _MemoryChip(icon: Icons.push_pin_outlined, label: '置顶'),
                if (memory.sensitive)
                  const _MemoryChip(
                    icon: Icons.lock_outline_rounded,
                    label: '敏感',
                  ),
              ],
            ),
            const SizedBox(height: 10),
            Text(memory.content, style: Theme.of(context).textTheme.bodyLarge),
            if (memory.tags.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                memory.tags.map((item) => '#$item').join('  '),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: Text(
                    '重要度 ${(memory.importance * 100).round()}% · 置信度 ${(memory.confidence * 100).round()}%',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
                if (memory.status != 'active')
                  IconButton(
                    tooltip: '启用',
                    onPressed: onActivate,
                    icon: const Icon(Icons.check_circle_outline_rounded),
                  ),
                IconButton(
                  tooltip: '编辑',
                  onPressed: onEdit,
                  icon: const Icon(Icons.edit_outlined),
                ),
                IconButton(
                  tooltip: '归档',
                  onPressed: onArchive,
                  icon: const Icon(Icons.archive_outlined),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _MemoryChip extends StatelessWidget {
  const _MemoryChip({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surfaceSoft,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 14),
            const SizedBox(width: 4),
            Text(label, style: Theme.of(context).textTheme.labelSmall),
          ],
        ),
      ),
    );
  }
}

class _MemoryEditor extends StatefulWidget {
  const _MemoryEditor({required this.memory});

  final CompanionMemory memory;

  @override
  State<_MemoryEditor> createState() => _MemoryEditorState();
}

class _MemoryEditorState extends State<_MemoryEditor> {
  late String _kind = widget.memory.kind;
  late String _subject = widget.memory.subject;
  late String _status = widget.memory.status;
  late bool _pinned = widget.memory.pinned;
  late bool _sensitive = widget.memory.sensitive;
  late double _importance = widget.memory.importance;
  late double _confidence = widget.memory.confidence;
  late final TextEditingController _contentController = TextEditingController(
    text: widget.memory.content,
  );
  late final TextEditingController _summaryController = TextEditingController(
    text: widget.memory.summary,
  );
  late final TextEditingController _tagsController = TextEditingController(
    text: widget.memory.tags.join(', '),
  );

  @override
  void dispose() {
    _contentController.dispose();
    _summaryController.dispose();
    _tagsController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          16,
          0,
          16,
          16 + MediaQuery.of(context).viewInsets.bottom,
        ),
        child: SizedBox(
          height: MediaQuery.of(context).size.height * 0.82,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                widget.memory.id.isEmpty ? '新增记忆' : '编辑记忆',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 12),
              Expanded(
                child: ListView(
                  children: [
                    TextField(
                      controller: _contentController,
                      minLines: 3,
                      maxLines: 8,
                      decoration: const InputDecoration(labelText: '记忆内容'),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _summaryController,
                      decoration: const InputDecoration(labelText: '摘要'),
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: _DropdownField(
                            label: '类型',
                            value: _kind,
                            items: const {
                              'fact': '事实',
                              'preference': '偏好',
                              'relationship': '关系',
                              'state': '近期状态',
                              'self_life': '她自己的生活',
                            },
                            onChanged: (value) => setState(() => _kind = value),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: _DropdownField(
                            label: '主体',
                            value: _subject,
                            items: const {
                              'user': '用户',
                              'companion': '她',
                              'relationship': '我们',
                            },
                            onChanged:
                                (value) => setState(() => _subject = value),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    _DropdownField(
                      label: '状态',
                      value: _status,
                      items: const {
                        'active': '启用',
                        'pending': '待确认',
                        'archived': '归档',
                      },
                      onChanged: (value) => setState(() => _status = value),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _tagsController,
                      decoration: const InputDecoration(labelText: '标签，用逗号分隔'),
                    ),
                    const SizedBox(height: 12),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      value: _pinned,
                      onChanged: (value) => setState(() => _pinned = value),
                      title: const Text('置顶'),
                    ),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      value: _sensitive,
                      onChanged: (value) => setState(() => _sensitive = value),
                      title: const Text('敏感'),
                    ),
                    _SliderField(
                      label: '重要度',
                      value: _importance,
                      onChanged: (value) => setState(() => _importance = value),
                    ),
                    _SliderField(
                      label: '置信度',
                      value: _confidence,
                      onChanged: (value) => setState(() => _confidence = value),
                    ),
                  ],
                ),
              ),
              Row(
                children: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('取消'),
                  ),
                  const Spacer(),
                  FilledButton.icon(
                    onPressed: _save,
                    icon: const Icon(Icons.check_rounded, size: 18),
                    label: const Text('保存'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _save() {
    final content = _contentController.text.trim();
    if (content.isEmpty) return;
    Navigator.of(context).pop(
      widget.memory.copyWith(
        kind: _kind,
        subject: _subject,
        status: _status,
        content: content,
        summary: _summaryController.text.trim(),
        tags: _tagsController.text
            .split(RegExp(r'[,，]'))
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false),
        importance: _importance,
        confidence: _confidence,
        pinned: _pinned,
        sensitive: _sensitive,
        enabled: _status != 'archived',
      ),
    );
  }
}

class _DropdownField extends StatelessWidget {
  const _DropdownField({
    required this.label,
    required this.value,
    required this.items,
    required this.onChanged,
  });

  final String label;
  final String value;
  final Map<String, String> items;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return DropdownButtonFormField<String>(
      value: value,
      decoration: InputDecoration(labelText: label),
      items: [
        for (final item in items.entries)
          DropdownMenuItem(value: item.key, child: Text(item.value)),
      ],
      onChanged: (value) {
        if (value != null) onChanged(value);
      },
    );
  }
}

class _SliderField extends StatelessWidget {
  const _SliderField({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final double value;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('$label ${(value * 100).round()}%'),
        Slider(value: value, onChanged: onChanged),
      ],
    );
  }
}
