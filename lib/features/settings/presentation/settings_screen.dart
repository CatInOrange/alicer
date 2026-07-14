import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../domain/prompt_models.dart';
import 'app_update_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late List<PromptModule> _modules;
  EnvironmentToggles _environment = const EnvironmentToggles(
    time: true,
    location: false,
    weather: false,
    anniversary: true,
  );
  MemoryToggles _memory = const MemoryToggles(
    shortTerm: true,
    longTerm: true,
    autoExtract: true,
    reviewBeforeSave: true,
  );
  final _roleController = TextEditingController(
    text: '她是用户的虚拟伴侣，温柔、聪明、偶尔撒娇，会主动关心用户的状态。',
  );
  final _styleController = TextEditingController(
    text: '自然、亲密、简洁，不像客服；可以轻微调侃，但要尊重边界。',
  );
  final List<String> _traits = ['温柔', '敏锐', '主动', '轻微占有欲'];

  @override
  void initState() {
    super.initState();
    _modules = [...defaultPromptModules]
      ..sort((a, b) => a.order.compareTo(b.order));
  }

  @override
  void dispose() {
    _roleController.dispose();
    _styleController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('配置'),
        actions: [
          IconButton(
            tooltip: '预览最终提示词',
            onPressed: _showPromptPreview,
            icon: const Icon(Icons.visibility_outlined),
          ),
          IconButton(
            tooltip: '保存',
            onPressed: () {
              ScaffoldMessenger.of(
                context,
              ).showSnackBar(const SnackBar(content: Text('配置保存接口待接入')));
            },
            icon: const Icon(Icons.save_outlined),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          _SectionHeader(
            title: '角色',
            subtitle: '伴侣的身份、性格和说话方式。',
            action: TextButton.icon(
              onPressed: () {},
              icon: const Icon(Icons.person_outline, size: 18),
              label: const Text('Alice'),
            ),
          ),
          _ConfigPanel(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextField(
                  controller: _roleController,
                  minLines: 3,
                  maxLines: 6,
                  decoration: const InputDecoration(labelText: '角色描述'),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final trait in _traits)
                      InputChip(
                        label: Text(trait),
                        onDeleted: () => setState(() => _traits.remove(trait)),
                      ),
                    ActionChip(
                      avatar: const Icon(Icons.add, size: 18),
                      label: const Text('特质'),
                      onPressed: () => setState(() => _traits.add('新的特质')),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _styleController,
                  minLines: 2,
                  maxLines: 4,
                  decoration: const InputDecoration(labelText: '回复风格'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 22),
          _SectionHeader(
            title: '提示词模块',
            subtitle: '借鉴酒馆的模块化 Prompt，可开关、排序、预览。',
            action: FilledButton.icon(
              onPressed: _showPromptPreview,
              icon: const Icon(Icons.code, size: 18),
              label: const Text('预览'),
            ),
          ),
          ..._modules.map(
            (module) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _PromptModuleTile(
                module: module,
                onChanged: (value) => _toggleModule(module.id, value),
              ),
            ),
          ),
          const SizedBox(height: 12),
          _SectionHeader(title: '环境', subtitle: '时间、地点、天气等现实上下文。'),
          _ConfigPanel(
            child: Column(
              children: [
                _SwitchRow(
                  icon: Icons.schedule_outlined,
                  title: '当前时间',
                  subtitle: '让回复知道日期、时段和节日。',
                  value: _environment.time,
                  onChanged:
                      (value) => setState(
                        () => _environment = _environment.copyWith(time: value),
                      ),
                ),
                _SwitchRow(
                  icon: Icons.place_outlined,
                  title: '当前位置',
                  subtitle: '需要用户授权，默认关闭。',
                  value: _environment.location,
                  onChanged:
                      (value) => setState(
                        () =>
                            _environment = _environment.copyWith(
                              location: value,
                            ),
                      ),
                ),
                _SwitchRow(
                  icon: Icons.cloud_outlined,
                  title: '天气',
                  subtitle: '由后端根据地点查询后注入。',
                  value: _environment.weather,
                  onChanged:
                      (value) => setState(
                        () =>
                            _environment = _environment.copyWith(
                              weather: value,
                            ),
                      ),
                ),
                _SwitchRow(
                  icon: Icons.favorite_border,
                  title: '纪念日',
                  subtitle: '认识天数、特殊日期和关系里程碑。',
                  value: _environment.anniversary,
                  onChanged:
                      (value) => setState(
                        () =>
                            _environment = _environment.copyWith(
                              anniversary: value,
                            ),
                      ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 22),
          _SectionHeader(title: '记忆', subtitle: '短期上下文负责连续性，长期记忆负责陪伴感。'),
          _ConfigPanel(
            child: Column(
              children: [
                _SwitchRow(
                  icon: Icons.short_text_outlined,
                  title: '短期记忆',
                  subtitle: '最近话题、今日状态和对话摘要。',
                  value: _memory.shortTerm,
                  onChanged:
                      (value) => setState(
                        () => _memory = _memory.copyWith(shortTerm: value),
                      ),
                ),
                _SwitchRow(
                  icon: Icons.auto_stories_outlined,
                  title: '长期记忆',
                  subtitle: '偏好、事实、关系事件和重要回忆。',
                  value: _memory.longTerm,
                  onChanged:
                      (value) => setState(
                        () => _memory = _memory.copyWith(longTerm: value),
                      ),
                ),
                _SwitchRow(
                  icon: Icons.auto_awesome_outlined,
                  title: '自动提取',
                  subtitle: '聊天后异步提取候选记忆。',
                  value: _memory.autoExtract,
                  onChanged:
                      (value) => setState(
                        () => _memory = _memory.copyWith(autoExtract: value),
                      ),
                ),
                _SwitchRow(
                  icon: Icons.fact_check_outlined,
                  title: '写入前审核',
                  subtitle: '候选长期记忆先确认再保存。',
                  value: _memory.reviewBeforeSave,
                  onChanged:
                      (value) => setState(
                        () =>
                            _memory = _memory.copyWith(reviewBeforeSave: value),
                      ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 22),
          _SectionHeader(title: '应用', subtitle: '版本检查、安装包下载和系统安装器。'),
          _ConfigPanel(
            child: _ActionRow(
              icon: Icons.system_update_alt_rounded,
              title: '应用更新',
              subtitle: '检查 GitHub Actions 发布的 Android 安装包。',
              onTap: () {
                Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (context) => const AppUpdateScreen(),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  void _toggleModule(String id, bool enabled) {
    setState(() {
      _modules =
          _modules
              .map(
                (module) =>
                    module.id == id
                        ? module.copyWith(enabled: enabled)
                        : module,
              )
              .toList();
    });
  }

  void _showPromptPreview() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) {
        final preview = _buildPromptPreview();
        return SafeArea(
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              16,
              0,
              16,
              16 + MediaQuery.of(context).viewInsets.bottom,
            ),
            child: SizedBox(
              height: MediaQuery.of(context).size.height * 0.72,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '最终提示词预览',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '后端会按启用模块和环境/记忆开关渲染变量。',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 12),
                  Expanded(
                    child: SingleChildScrollView(
                      child: SelectableText(
                        preview,
                        style: const TextStyle(
                          fontFamily: 'monospace',
                          fontSize: 13,
                          height: 1.45,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  String _buildPromptPreview() {
    final enabledModules = _modules.where((module) => module.enabled);
    final buffer =
        StringBuffer()
          ..writeln('基础规则：')
          ..writeln('你是 Alicer 的伴侣智能体，需要自然、真诚、有边界地陪伴用户。')
          ..writeln()
          ..writeln('角色描述：')
          ..writeln(_roleController.text.trim())
          ..writeln()
          ..writeln('性格特质：${_traits.join('、')}')
          ..writeln()
          ..writeln('回复风格：')
          ..writeln(_styleController.text.trim())
          ..writeln()
          ..writeln('启用模块：');

    for (final module in enabledModules) {
      buffer
        ..writeln('- ${module.title}')
        ..writeln('  ${module.content}');
    }

    buffer
      ..writeln()
      ..writeln('环境开关：')
      ..writeln('- 时间：${_environment.time ? '启用' : '关闭'}')
      ..writeln('- 地点：${_environment.location ? '启用' : '关闭'}')
      ..writeln('- 天气：${_environment.weather ? '启用' : '关闭'}')
      ..writeln('- 纪念日：${_environment.anniversary ? '启用' : '关闭'}')
      ..writeln()
      ..writeln('记忆开关：')
      ..writeln('- 短期记忆：${_memory.shortTerm ? '启用' : '关闭'}')
      ..writeln('- 长期记忆：${_memory.longTerm ? '启用' : '关闭'}')
      ..writeln('- 自动提取：${_memory.autoExtract ? '启用' : '关闭'}')
      ..writeln('- 写入前审核：${_memory.reviewBeforeSave ? '启用' : '关闭'}');

    return buffer.toString();
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({
    required this.title,
    required this.subtitle,
    this.action,
  });

  final String title;
  final String subtitle;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 3),
                Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          ),
          if (action != null) action!,
        ],
      ),
    );
  }
}

class _ConfigPanel extends StatelessWidget {
  const _ConfigPanel({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Container(
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: colors.border),
      ),
      padding: const EdgeInsets.all(14),
      child: child,
    );
  }
}

class _PromptModuleTile extends StatelessWidget {
  const _PromptModuleTile({required this.module, required this.onChanged});

  final PromptModule module;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Container(
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: colors.border),
      ),
      padding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
      child: Row(
        children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color:
                  module.enabled
                      ? Theme.of(
                        context,
                      ).colorScheme.primary.withValues(alpha: 0.1)
                      : colors.surfaceSoft,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              module.icon,
              size: 20,
              color:
                  module.enabled
                      ? Theme.of(context).colorScheme.primary
                      : colors.textMuted,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  module.title,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 4),
                Text(
                  module.description,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          Switch(value: module.enabled, onChanged: onChanged),
        ],
      ),
    );
  }
}

class _SwitchRow extends StatelessWidget {
  const _SwitchRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Icon(icon, color: colors.textMuted, size: 22),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 3),
                Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          ),
          Switch(value: value, onChanged: onChanged),
        ],
      ),
    );
  }
}

class _ActionRow extends StatelessWidget {
  const _ActionRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return InkWell(
      borderRadius: BorderRadius.circular(8),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          children: [
            Icon(icon, color: colors.textMuted, size: 22),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 3),
                  Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
            const Icon(Icons.chevron_right_rounded),
          ],
        ),
      ),
    );
  }
}
