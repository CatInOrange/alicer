import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../../../app/theme.dart';
import '../../../core/network/api_client.dart';
import '../../chat/data/chat_repository.dart';
import '../../environment/application/environment_service.dart';
import '../data/settings_store.dart';
import '../domain/app_settings.dart';
import 'app_update_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _imagePicker = ImagePicker();
  final _environmentService = EnvironmentService();
  final _apiBaseController = TextEditingController();
  final _companionNameController = TextEditingController();
  final _userNameController = TextEditingController();
  final _maxTokensController = TextEditingController();

  AlicerSettings _settings = const AlicerSettings();
  bool _isLoading = true;
  bool _isSaving = false;
  String _environmentStatus = '尚未读取';
  String _backendStatus = '未检测';

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _apiBaseController.dispose();
    _companionNameController.dispose();
    _userNameController.dispose();
    _maxTokensController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final settings = await SettingsStore.load();
    if (!mounted) return;
    _applySettings(settings);
    setState(() => _isLoading = false);
    unawaited(_checkBackend());
  }

  void _applySettings(AlicerSettings settings) {
    _settings = settings;
    _apiBaseController.text = settings.apiBaseUrl;
    _companionNameController.text = settings.companion.name;
    _userNameController.text = settings.companion.userName;
    _maxTokensController.text = settings.model.maxTokens.toString();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    if (_isLoading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
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
            onPressed: _isSaving ? null : _save,
            icon: const Icon(Icons.save_outlined),
          ),
        ],
      ),
      body: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Theme.of(context).colorScheme.primary.withValues(alpha: 0.08),
              colors.background,
            ],
          ),
        ),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
          children: [
            _SettingsHero(settings: _settings, backendStatus: _backendStatus),
            const SizedBox(height: 14),
            _CollapsiblePanel(
              icon: Icons.face_retouching_natural_outlined,
              title: '伴侣与头像',
              subtitle: '名称、双方头像和本地头像缓存。',
              initiallyExpanded: true,
              child: Column(
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _companionNameController,
                          decoration: const InputDecoration(labelText: 'AI 名字'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: TextField(
                          controller: _userNameController,
                          decoration: const InputDecoration(labelText: '你的称呼'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      Expanded(
                        child: _AvatarPicker(
                          label: 'AI 头像',
                          path: _settings.companion.aiAvatarPath,
                          fallback: _settings.companion.name,
                          onTap: () => _pickAvatar(isUser: false),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: _AvatarPicker(
                          label: '用户头像',
                          path: _settings.companion.userAvatarPath,
                          fallback: _settings.companion.userName,
                          onTap: () => _pickAvatar(isUser: true),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            _CollapsiblePanel(
              icon: Icons.auto_awesome_outlined,
              title: '提示词模块',
              subtitle: '酒馆式模块化 Prompt，角色描述和性格特质都在这里编辑。',
              initiallyExpanded: true,
              trailing: FilledButton.icon(
                onPressed: _showPromptPreview,
                icon: const Icon(Icons.code_rounded, size: 18),
                label: const Text('预览'),
              ),
              child: Column(
                children: [
                  for (final module in _settings.promptModules)
                    _PromptModuleRow(
                      module: module,
                      onToggle:
                          (value) => _updateModule(
                            module.id,
                            module.copyWith(enabled: value),
                          ),
                      onEdit: () => _editModule(module),
                    ),
                ],
              ),
            ),
            _CollapsiblePanel(
              icon: Icons.public_rounded,
              title: '环境感知',
              subtitle: '时间、地点、天气直接来自手机当前信息。',
              child: Column(
                children: [
                  _SwitchRow(
                    icon: Icons.schedule_outlined,
                    title: '当前时间',
                    subtitle: '注入手机当前日期和时段。',
                    value: _settings.environment.time,
                    onChanged:
                        (value) => _setEnvironment(
                          _settings.environment.copyWith(time: value),
                        ),
                  ),
                  _SwitchRow(
                    icon: Icons.place_outlined,
                    title: '当前位置',
                    subtitle: '按需申请系统定位权限，不手动编辑。',
                    value: _settings.environment.location,
                    onChanged:
                        (value) => _setEnvironment(
                          _settings.environment.copyWith(location: value),
                        ),
                  ),
                  _SwitchRow(
                    icon: Icons.cloud_outlined,
                    title: '天气',
                    subtitle: '手机传坐标，后端按坐标补当天气。',
                    value: _settings.environment.weather,
                    onChanged:
                        (value) => _setEnvironment(
                          _settings.environment.copyWith(weather: value),
                        ),
                  ),
                  _SwitchRow(
                    icon: Icons.favorite_border_rounded,
                    title: '纪念日',
                    subtitle: '预留给关系里程碑和特殊日期。',
                    value: _settings.environment.anniversary,
                    onChanged:
                        (value) => _setEnvironment(
                          _settings.environment.copyWith(anniversary: value),
                        ),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(child: Text(_environmentStatus)),
                      TextButton.icon(
                        onPressed: _probeEnvironment,
                        icon: const Icon(Icons.my_location_rounded, size: 18),
                        label: const Text('读取一次'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            _CollapsiblePanel(
              icon: Icons.memory_rounded,
              title: '记忆',
              subtitle: '短期连续性优先本地缓存，长期记忆由后端沉淀。',
              child: Column(
                children: [
                  _SwitchRow(
                    icon: Icons.short_text_outlined,
                    title: '短期记忆',
                    subtitle: '最近聊天与当前话题。',
                    value: _settings.memory.shortTerm,
                    onChanged:
                        (value) => _setMemory(
                          _settings.memory.copyWith(shortTerm: value),
                        ),
                  ),
                  _SwitchRow(
                    icon: Icons.auto_stories_outlined,
                    title: '长期记忆',
                    subtitle: '稳定事实、偏好和重要回忆。',
                    value: _settings.memory.longTerm,
                    onChanged:
                        (value) => _setMemory(
                          _settings.memory.copyWith(longTerm: value),
                        ),
                  ),
                  _SwitchRow(
                    icon: Icons.auto_fix_high_outlined,
                    title: '自动提取',
                    subtitle: '后端异步提取候选记忆。',
                    value: _settings.memory.autoExtract,
                    onChanged:
                        (value) => _setMemory(
                          _settings.memory.copyWith(autoExtract: value),
                        ),
                  ),
                  _SwitchRow(
                    icon: Icons.fact_check_outlined,
                    title: '写入前审核',
                    subtitle: '候选长期记忆确认后再保存。',
                    value: _settings.memory.reviewBeforeSave,
                    onChanged:
                        (value) => _setMemory(
                          _settings.memory.copyWith(reviewBeforeSave: value),
                        ),
                  ),
                ],
              ),
            ),
            _CollapsiblePanel(
              icon: Icons.hub_outlined,
              title: '后端与模型',
              subtitle: 'Alicer 后端、DeepSeek 模型和生成参数。',
              child: Column(
                children: [
                  TextField(
                    controller: _apiBaseController,
                    decoration: const InputDecoration(labelText: '后端地址'),
                  ),
                  const SizedBox(height: 12),
                  _ModelSelector(
                    value: _settings.model.model,
                    onChanged: _setModel,
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _maxTokensController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: '最大输出 Token'),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(child: Text(_backendStatus)),
                      TextButton.icon(
                        onPressed: _checkBackend,
                        icon: const Icon(
                          Icons.health_and_safety_outlined,
                          size: 18,
                        ),
                        label: const Text('检测'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            _CollapsiblePanel(
              icon: Icons.system_update_alt_rounded,
              title: '应用',
              subtitle: 'GitHub Actions 构建、COS 更新和安装器。',
              child: _ActionRow(
                icon: Icons.system_update_alt_rounded,
                title: '应用更新',
                subtitle: '检查 GitHub Actions 发布到 COS 的 Android 安装包。',
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
      ),
    );
  }

  Future<void> _save() async {
    final apiBaseUrl = _apiBaseController.text.trim().replaceAll(
      RegExp(r'/$'),
      '',
    );
    final maxTokens =
        int.tryParse(_maxTokensController.text.trim()) ??
        _settings.model.maxTokens;
    final next = _settings.copyWith(
      apiBaseUrl: apiBaseUrl.isEmpty ? _settings.apiBaseUrl : apiBaseUrl,
      companion: _settings.companion.copyWith(
        name:
            _companionNameController.text.trim().isEmpty
                ? 'Alice'
                : _companionNameController.text.trim(),
        userName:
            _userNameController.text.trim().isEmpty
                ? '你'
                : _userNameController.text.trim(),
      ),
      model: _settings.model.copyWith(maxTokens: maxTokens),
    );
    setState(() {
      _isSaving = true;
      _settings = next;
    });
    try {
      await SettingsStore.save(next);
      await ChatRepository(settings: next).syncSettings();
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('配置已保存并同步到后端')));
      await _checkBackend();
    } catch (error) {
      await SettingsStore.save(next);
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('已保存到本机，后端同步稍后再试：$error')));
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  void _updateModule(String id, PromptModule next) {
    setState(() {
      _settings = _settings.copyWith(
        promptModules: [
          for (final module in _settings.promptModules)
            if (module.id == id) next else module,
        ],
      );
    });
    unawaited(SettingsStore.save(_settings));
  }

  void _setEnvironment(EnvironmentToggles environment) {
    setState(() => _settings = _settings.copyWith(environment: environment));
    unawaited(SettingsStore.save(_settings));
  }

  void _setMemory(MemoryToggles memory) {
    setState(() => _settings = _settings.copyWith(memory: memory));
    unawaited(SettingsStore.save(_settings));
  }

  void _setModel(String model) {
    final option = deepSeekModelOptionFor(model);
    setState(() {
      _settings = _settings.copyWith(
        model: _settings.model.copyWith(
          model: option.id,
          maxTokens: option.maxTokens,
        ),
      );
      _maxTokensController.text = option.maxTokens.toString();
    });
    unawaited(SettingsStore.save(_settings));
  }

  Future<void> _editModule(PromptModule module) async {
    final controller = TextEditingController(text: module.content);
    final result = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) {
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
                    module.title,
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    module.description,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 12),
                  Expanded(
                    child: TextField(
                      controller: controller,
                      expands: true,
                      minLines: null,
                      maxLines: null,
                      textAlignVertical: TextAlignVertical.top,
                      decoration: const InputDecoration(labelText: '模块内容'),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      TextButton(
                        onPressed: () => Navigator.of(context).pop(),
                        child: const Text('取消'),
                      ),
                      const Spacer(),
                      FilledButton.icon(
                        onPressed:
                            () => Navigator.of(
                              context,
                            ).pop(controller.text.trim()),
                        icon: const Icon(Icons.check_rounded, size: 18),
                        label: const Text('保存模块'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
    controller.dispose();
    if (result == null) return;
    _updateModule(module.id, module.copyWith(content: result));
  }

  Future<void> _showPromptPreview() async {
    String preview = _localPromptPreview();
    try {
      final env = await _environmentService.collect(_settings.environment);
      final response = await ChatRepository(
        settings: _settings,
      ).previewPrompt(environment: env.payload);
      final messages = (response['messages'] as List?) ?? const <dynamic>[];
      preview = messages
          .whereType<Map>()
          .map((item) => '[${item['role']}]\n${item['content']}')
          .join('\n\n---\n\n');
    } catch (_) {}
    if (!mounted) return;
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
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
                    '按当前启用模块、手机环境和记忆开关渲染。',
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

  String _localPromptPreview() {
    final modules = [..._settings.promptModules.where((item) => item.enabled)]
      ..sort((a, b) => a.order.compareTo(b.order));
    return modules
        .map((item) => '# ${item.title}\n${item.content}')
        .join('\n\n');
  }

  Future<void> _pickAvatar({required bool isUser}) async {
    final picked = await _imagePicker.pickImage(
      source: ImageSource.gallery,
      maxWidth: 1024,
      imageQuality: 88,
    );
    if (picked == null) return;
    final dir = await getApplicationSupportDirectory();
    final avatarDir = Directory(p.join(dir.path, 'avatars'));
    await avatarDir.create(recursive: true);
    final ext =
        p.extension(picked.path).isEmpty ? '.jpg' : p.extension(picked.path);
    final target = File(p.join(avatarDir.path, isUser ? 'user$ext' : 'ai$ext'));
    await File(picked.path).copy(target.path);
    final companion =
        isUser
            ? _settings.companion.copyWith(userAvatarPath: target.path)
            : _settings.companion.copyWith(aiAvatarPath: target.path);
    setState(() => _settings = _settings.copyWith(companion: companion));
    await SettingsStore.save(_settings);
  }

  Future<void> _probeEnvironment() async {
    setState(() => _environmentStatus = '读取中...');
    final snapshot = await _environmentService.collect(_settings.environment);
    if (!mounted) return;
    setState(() => _environmentStatus = snapshot.label);
  }

  Future<void> _checkBackend() async {
    final base =
        _apiBaseController.text.trim().isEmpty
            ? _settings.apiBaseUrl
            : _apiBaseController.text.trim();
    setState(() => _backendStatus = '检测中...');
    try {
      final response = await ApiClient(baseUrl: base).getJson('/api/health');
      if (!mounted) return;
      final configured =
          response['deepseekConfigured'] == true
              ? 'DeepSeek 已配置'
              : 'DeepSeek Key 未配置';
      setState(() => _backendStatus = '后端在线 · $configured');
    } catch (error) {
      if (!mounted) return;
      setState(() => _backendStatus = '后端未连接：$error');
    }
  }
}

class _SettingsHero extends StatelessWidget {
  const _SettingsHero({required this.settings, required this.backendStatus});

  final AlicerSettings settings;
  final String backendStatus;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Container(
      decoration: BoxDecoration(
        color: colors.surface.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: colors.border),
      ),
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          _AvatarPreview(
            path: settings.companion.aiAvatarPath,
            label: settings.companion.name,
            size: 58,
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  settings.companion.name,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 4),
                Text(
                  '提示词、记忆、环境和模型都在这里集中管理。',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 6),
                Text(
                  backendStatus,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ModelSelector extends StatelessWidget {
  const _ModelSelector({required this.value, required this.onChanged});

  final String value;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final selected = normalizeDeepSeekModelId(value);
    return InputDecorator(
      decoration: const InputDecoration(labelText: 'DeepSeek 模型'),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: selected,
          isExpanded: true,
          borderRadius: BorderRadius.circular(8),
          items: [
            for (final item in deepSeekModelOptions)
              DropdownMenuItem<String>(
                value: item.id,
                child: _ModelOptionLabel(option: item),
              ),
          ],
          selectedItemBuilder: (context) {
            return [
              for (final item in deepSeekModelOptions)
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    item.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ];
          },
          onChanged: (next) {
            if (next != null) onChanged(next);
          },
        ),
      ),
    );
  }
}

class _ModelOptionLabel extends StatelessWidget {
  const _ModelOptionLabel({required this.option});

  final DeepSeekModelOption option;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(option.name, maxLines: 1, overflow: TextOverflow.ellipsis),
        const SizedBox(height: 2),
        Text(
          option.description,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ],
    );
  }
}

class _CollapsiblePanel extends StatelessWidget {
  const _CollapsiblePanel({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.child,
    this.initiallyExpanded = false,
    this.trailing,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final Widget child;
  final bool initiallyExpanded;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: colors.surface,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: colors.border),
        ),
        child: ExpansionTile(
          initiallyExpanded: initiallyExpanded,
          leading: Icon(icon),
          title: Text(title, style: Theme.of(context).textTheme.titleMedium),
          subtitle: Text(
            subtitle,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          trailing: trailing,
          childrenPadding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
          children: [child],
        ),
      ),
    );
  }
}

class _PromptModuleRow extends StatelessWidget {
  const _PromptModuleRow({
    required this.module,
    required this.onToggle,
    required this.onEdit,
  });

  final PromptModule module;
  final ValueChanged<bool> onToggle;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onEdit,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
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
                          ).colorScheme.primary.withValues(alpha: 0.10)
                          : colors.surfaceSoft,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(module.icon, size: 20),
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
                    const SizedBox(height: 3),
                    Text(
                      module.description,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              Switch(value: module.enabled, onChanged: onToggle),
              const Icon(Icons.chevron_right_rounded),
            ],
          ),
        ),
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

class _AvatarPicker extends StatelessWidget {
  const _AvatarPicker({
    required this.label,
    required this.path,
    required this.fallback,
    required this.onTap,
  });

  final String label;
  final String path;
  final String fallback;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(8),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: context.alicerColors.border),
        ),
        child: Column(
          children: [
            _AvatarPreview(path: path, label: fallback, size: 64),
            const SizedBox(height: 8),
            Text(label),
            const SizedBox(height: 2),
            Text('本地缓存', style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}

class _AvatarPreview extends StatelessWidget {
  const _AvatarPreview({
    required this.path,
    required this.label,
    required this.size,
  });

  final String path;
  final String label;
  final double size;

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    final file = path.isEmpty ? null : File(path);
    return ClipOval(
      child: Container(
        width: size,
        height: size,
        color: color.withValues(alpha: 0.12),
        child:
            file != null && file.existsSync()
                ? Image.file(file, fit: BoxFit.cover)
                : Center(
                  child: Text(
                    label.isEmpty ? 'A' : label.substring(0, 1),
                    style: TextStyle(
                      color: color,
                      fontWeight: FontWeight.w800,
                      fontSize: size * 0.34,
                    ),
                  ),
                ),
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
    return InkWell(
      borderRadius: BorderRadius.circular(8),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          children: [
            Icon(icon, color: context.alicerColors.textMuted, size: 22),
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
