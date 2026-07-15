import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../settings/domain/app_settings.dart';
import '../data/rift_repository.dart';
import '../domain/rift_models.dart';

const _genres = [
  '随机',
  '古风权谋',
  '仙侠师门',
  '现代都市',
  '校园青春',
  '赛博霓虹',
  '末日废土',
  '民国旧梦',
  '西幻王庭',
  '悬疑怪谈',
  '星际远航',
  '娱乐圈',
  '黑帮夜色',
];

const _relations = [
  '随机',
  '手动输入',
  '师徒',
  '同门',
  '同事',
  '搭档',
  '上下级',
  '主仆',
  '主奴',
  '契约双方',
  '监护人与被监护人',
  '贵族与侍从',
  '君臣',
  '邻居',
  '同学',
  '室友',
  '雇主与保镖',
  '追捕者与嫌疑人',
  '审讯者与囚徒',
  '神明与信徒',
  '召唤者与被召唤者',
  '敌对阵营',
  '陌生人',
];

const _intensities = ['随机', '轻松日常', '中等戏剧', '高张力', '极限修罗场'];
const _lengths = [10, 20, 30, 50, 100];

class RiftCreateScreen extends StatefulWidget {
  const RiftCreateScreen({super.key, required this.settings});

  final AlicerSettings settings;

  @override
  State<RiftCreateScreen> createState() => _RiftCreateScreenState();
}

class _RiftCreateScreenState extends State<RiftCreateScreen> {
  final _customRelationController = TextEditingController();
  String _genre = '随机';
  String _relation = '随机';
  String _intensity = '随机';
  int _targetTurns = 20;
  bool _creating = false;

  @override
  void dispose() {
    _customRelationController.dispose();
    super.dispose();
  }

  Future<void> _create() async {
    final customRelation = _customRelationController.text.trim();
    if (_relation == '手动输入' && customRelation.isEmpty) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('写一个表面身份关系')));
      return;
    }
    setState(() => _creating = true);
    try {
      final detail = await RiftRepository(settings: widget.settings).createRift(
        genre: _genre,
        surfaceRelation: _relation == '手动输入' ? '随机' : _relation,
        customSurfaceRelation: customRelation,
        intensity: _intensity,
        targetTurns: _targetTurns,
      );
      if (!mounted) return;
      Navigator.of(context).pop<RiftDetail>(detail);
    } catch (error) {
      if (!mounted) return;
      setState(() => _creating = false);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('裂隙开启失败：$error')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Scaffold(
      appBar: AppBar(title: const Text('开启裂隙')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(18, 12, 18, 110),
        children: [
          Text(
            '只选择表层方向。恋爱氛围、隐藏真相和结局走向会在后端随机生成。',
            style: TextStyle(color: colors.textSubtle, height: 1.45),
          ),
          const SizedBox(height: 18),
          _ChoiceSection(
            title: '世界类型',
            options: _genres,
            value: _genre,
            onSelected: (value) => setState(() => _genre = value),
          ),
          const SizedBox(height: 22),
          _ChoiceSection(
            title: '身份关系',
            options: _relations,
            value: _relation,
            onSelected: (value) => setState(() => _relation = value),
          ),
          if (_relation == '手动输入') ...[
            const SizedBox(height: 10),
            TextField(
              controller: _customRelationController,
              maxLength: 24,
              decoration: const InputDecoration(
                labelText: '表面身份关系',
                hintText: '例如：债主与欠债人、船长与偷渡客',
                counterText: '',
              ),
            ),
          ],
          const SizedBox(height: 22),
          _ChoiceSection(
            title: '故事强度',
            options: _intensities,
            value: _intensity,
            onSelected: (value) => setState(() => _intensity = value),
          ),
          const SizedBox(height: 22),
          _LengthSection(
            value: _targetTurns,
            onSelected: (value) => setState(() => _targetTurns = value),
          ),
        ],
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(18, 10, 18, 14),
          child: FilledButton.icon(
            onPressed: _creating ? null : _create,
            icon:
                _creating
                    ? const SizedBox.square(
                      dimension: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                    : const Icon(Icons.auto_awesome_rounded),
            label: Text(_creating ? '正在重写命运…' : '坠入裂隙'),
          ),
        ),
      ),
    );
  }
}

class _LengthSection extends StatelessWidget {
  const _LengthSection({required this.value, required this.onSelected});

  final int value;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '剧本长度',
          style: TextStyle(
            color: colors.text,
            fontSize: 16,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children:
              _lengths.map((turns) {
                return ChoiceChip(
                  label: Text('$turns 轮'),
                  selected: turns == value,
                  onSelected: (_) => onSelected(turns),
                );
              }).toList(),
        ),
      ],
    );
  }
}

class _ChoiceSection extends StatelessWidget {
  const _ChoiceSection({
    required this.title,
    required this.options,
    required this.value,
    required this.onSelected,
  });

  final String title;
  final List<String> options;
  final String value;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: TextStyle(
            color: colors.text,
            fontSize: 16,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children:
              options.map((option) {
                final selected = option == value;
                return ChoiceChip(
                  label: Text(option),
                  selected: selected,
                  onSelected: (_) => onSelected(option),
                );
              }).toList(),
        ),
      ],
    );
  }
}
