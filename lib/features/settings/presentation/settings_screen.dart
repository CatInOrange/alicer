import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

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
import '../../user_timeline/application/user_timeline_service.dart';
import 'app_update_screen.dart';
import 'memory_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _imagePicker = ImagePicker();
  final _environmentService = EnvironmentService();
  final _userTimelineService = UserTimelineService();
  final _apiBaseController = TextEditingController();
  final _adminTokenController = TextEditingController();
  final _companionNameController = TextEditingController();
  final _userNameController = TextEditingController();
  final _maxTokensController = TextEditingController();

  AlicerSettings _settings = const AlicerSettings();
  bool _isLoading = true;
  bool _isSaving = false;
  bool _isRestartingBackend = false;
  bool _isLoadingLife = false;
  bool _isAdvancingLife = false;
  bool _isLoadingUserTimeline = false;
  bool _isSyncingUserTimeline = false;
  String _environmentStatus = '尚未读取';
  String _backendStatus = '未检测';
  String _lifeStatus = '尚未读取';
  String _userTimelineStatus = '尚未读取';
  Map<String, dynamic>? _lifeContext;
  List<Map<String, dynamic>> _lifeEvents = const [];
  Map<String, dynamic>? _userTimelineContext;
  List<Map<String, dynamic>> _userTimelineEvents = const [];

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _apiBaseController.dispose();
    _adminTokenController.dispose();
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
    unawaited(_loadLifeRecords());
    unawaited(_loadUserTimeline());
    unawaited(_userTimelineService.configureBackground(settings));
  }

  void _applySettings(AlicerSettings settings) {
    _settings = settings;
    _apiBaseController.text = settings.apiBaseUrl;
    _adminTokenController.text = settings.adminToken;
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
              subtitle: '长期记忆由后端沉淀；短期上下文只作为聊天历史使用。',
              child: Column(
                children: [
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
                  _ActionRow(
                    icon: Icons.library_books_outlined,
                    title: '记忆管理',
                    subtitle: '查看、确认、编辑、归档她记住的事情。',
                    onTap: () {
                      Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (context) => const MemoryScreen(),
                        ),
                      );
                    },
                  ),
                  _HistoryModeRow(
                    value: _settings.chatContext.historyMode,
                    onChanged:
                        (value) => _setChatContext(
                          _settings.chatContext.copyWith(historyMode: value),
                        ),
                  ),
                  _IntSliderRow(
                    icon: Icons.format_list_numbered_outlined,
                    title: '最近条数',
                    subtitle:
                        '按最近条数模式时取 ${_settings.chatContext.recentMessages} 条消息。',
                    value: _settings.chatContext.recentMessages,
                    min: 10,
                    max: 300,
                    divisions: 29,
                    onChanged:
                        (value) => _setChatContext(
                          _settings.chatContext.copyWith(recentMessages: value),
                        ),
                  ),
                  _IntSliderRow(
                    icon: Icons.history_edu_outlined,
                    title: '上下文上限',
                    subtitle:
                        '没超过窗口时尽量保留历史，最多 ${_settings.chatContext.maxHistoryMessages} 条。',
                    value: _settings.chatContext.maxHistoryMessages,
                    min: 20,
                    max: 300,
                    divisions: 28,
                    onChanged:
                        (value) => _setChatContext(
                          _settings.chatContext.copyWith(
                            maxHistoryMessages: value,
                          ),
                        ),
                  ),
                ],
              ),
            ),
            _CollapsiblePanel(
              icon: Icons.phone_android_outlined,
              title: '我的轨迹',
              subtitle: 'Android 后台归纳地点变化、城市变化、音乐和可打扰程度，让她更懂你。',
              child: Column(
                children: [
                  _SwitchRow(
                    icon: Icons.route_outlined,
                    title: '启用用户生活轨迹',
                    subtitle: '开启后手机端会同步授权的状态事件到后端。',
                    value: _settings.userTimeline.enabled,
                    onChanged:
                        (value) => _setUserTimeline(
                          _settings.userTimeline.copyWith(enabled: value),
                        ),
                  ),
                  _SwitchRow(
                    icon: Icons.sync_rounded,
                    title: '后台低频同步',
                    subtitle: 'Android 会用系统 Worker 低频唤醒，不需要一直打开 App。',
                    value: _settings.userTimeline.backgroundSync,
                    onChanged:
                        (value) => _setUserTimeline(
                          _settings.userTimeline.copyWith(
                            backgroundSync: value,
                          ),
                        ),
                  ),
                  _SwitchRow(
                    icon: Icons.place_outlined,
                    title: '位置变化',
                    subtitle: '默认只用于语义状态，不在聊天里暴露精确坐标。',
                    value: _settings.userTimeline.location,
                    onChanged:
                        (value) => _setUserTimeline(
                          _settings.userTimeline.copyWith(location: value),
                        ),
                  ),
                  _SwitchRow(
                    icon: Icons.music_note_outlined,
                    title: '音乐状态',
                    subtitle: '记录正在听歌、暂停和切换等线索；需要通知访问权限。',
                    value: _settings.userTimeline.music,
                    onChanged:
                        (value) => _setUserTimeline(
                          _settings.userTimeline.copyWith(music: value),
                        ),
                  ),
                  _SwitchRow(
                    icon: Icons.directions_walk_outlined,
                    title: '运动/通勤状态',
                    subtitle: '预留 Activity Recognition 权限，用于步行、静止、通勤判断。',
                    value: _settings.userTimeline.motion,
                    onChanged:
                        (value) => _setUserTimeline(
                          _settings.userTimeline.copyWith(motion: value),
                        ),
                  ),
                  _SwitchRow(
                    icon: Icons.headphones_outlined,
                    title: '设备状态',
                    subtitle: '耳机连接等低敏上下文，不采集电量。',
                    value: _settings.userTimeline.device,
                    onChanged:
                        (value) => _setUserTimeline(
                          _settings.userTimeline.copyWith(device: value),
                        ),
                  ),
                  _SwitchRow(
                    icon: Icons.apps_rounded,
                    title: 'App 使用行为',
                    subtitle: '权限敏感，默认关闭；后续只做类别，不采集内容。',
                    value: _settings.userTimeline.appUsage,
                    onChanged:
                        (value) => _setUserTimeline(
                          _settings.userTimeline.copyWith(appUsage: value),
                        ),
                  ),
                  _IntSliderRow(
                    icon: Icons.timer_outlined,
                    title: '后台同步间隔',
                    subtitle:
                        '${_settings.userTimeline.syncIntervalMinutes} 分钟 · Android 实际执行时间会受系统调度影响。',
                    value: _settings.userTimeline.syncIntervalMinutes,
                    min: 15,
                    max: 180,
                    divisions: 11,
                    onChanged:
                        (value) => _setUserTimeline(
                          _settings.userTimeline.copyWith(
                            syncIntervalMinutes: value,
                          ),
                        ),
                  ),
                  _IntSliderRow(
                    icon: Icons.delete_sweep_outlined,
                    title: '事件保留',
                    subtitle:
                        '仅保留最近 ${_settings.userTimeline.retentionDays} 天内的原始轨迹。',
                    value: _settings.userTimeline.retentionDays,
                    min: 1,
                    max: 2,
                    divisions: 1,
                    onChanged:
                        (value) => _setUserTimeline(
                          _settings.userTimeline.copyWith(retentionDays: value),
                        ),
                  ),
                  const Divider(height: 26),
                  _UserTimelinePanel(
                    contextData: _userTimelineContext,
                    events: _userTimelineEvents,
                    status: _userTimelineStatus,
                    isLoading: _isLoadingUserTimeline,
                    isSyncing: _isSyncingUserTimeline,
                    onRefresh: _loadUserTimeline,
                    onSyncNow: _syncUserTimelineNow,
                    onRequestPermissions: _requestUserTimelinePermissions,
                  ),
                ],
              ),
            ),
            _CollapsiblePanel(
              icon: Icons.timeline_outlined,
              title: '生活模拟',
              subtitle: '后台按小时推进她自己的生活轨迹，聊天和朋友圈共享同一状态。',
              child: Column(
                children: [
                  _SwitchRow(
                    icon: Icons.play_circle_outline_rounded,
                    title: '启用生活模拟',
                    subtitle: '开启后后端会定时生成当前活动、地点、心情和事件。',
                    value: _settings.life.enabled,
                    onChanged:
                        (value) =>
                            _setLife(_settings.life.copyWith(enabled: value)),
                  ),
                  _IntSliderRow(
                    icon: Icons.update_rounded,
                    title: '更新间隔',
                    subtitle:
                        '每 ${_settings.life.updateIntervalHours} 小时推进一次生活状态。',
                    value: _settings.life.updateIntervalHours,
                    min: 1,
                    max: 6,
                    divisions: 5,
                    onChanged:
                        (value) => _setLife(
                          _settings.life.copyWith(updateIntervalHours: value),
                        ),
                  ),
                  _SliderRow(
                    icon: Icons.casino_outlined,
                    title: '生活随机性',
                    subtitle:
                        '${(_settings.life.randomness * 100).round()}% · 越高越容易出现临时事件，但仍受记忆和生活画像约束。',
                    value: _settings.life.randomness,
                    onChanged:
                        (value) => _setLife(
                          _settings.life.copyWith(randomness: value),
                        ),
                  ),
                  _SwitchRow(
                    icon: Icons.photo_camera_back_outlined,
                    title: '朋友圈使用生活事件',
                    subtitle: '生成朋友圈时优先围绕最近生活轨迹，而不是凭空写日常。',
                    value: _settings.life.autoMomentsFromLife,
                    onChanged:
                        (value) => _setLife(
                          _settings.life.copyWith(autoMomentsFromLife: value),
                        ),
                  ),
                  _IntSliderRow(
                    icon: Icons.manage_history_outlined,
                    title: '画像刷新周期',
                    subtitle:
                        '${_settings.life.profileRefreshHours} 小时 · 从长期记忆重新归纳职业、作息和常去地点。',
                    value: _settings.life.profileRefreshHours,
                    min: 6,
                    max: 168,
                    divisions: 27,
                    onChanged:
                        (value) => _setLife(
                          _settings.life.copyWith(profileRefreshHours: value),
                        ),
                  ),
                  const Divider(height: 26),
                  _LifeRecordsPanel(
                    contextData: _lifeContext,
                    events: _lifeEvents,
                    status: _lifeStatus,
                    isLoading: _isLoadingLife,
                    isAdvancing: _isAdvancingLife,
                    onRefresh: _loadLifeRecords,
                    onAdvance: _advanceLifeOnce,
                  ),
                ],
              ),
            ),
            _CollapsiblePanel(
              icon: Icons.photo_camera_back_outlined,
              title: '朋友圈',
              subtitle: '伴侣自动发朋友圈的频率和真实感。',
              child: Column(
                children: [
                  _SliderRow(
                    icon: Icons.auto_awesome_motion_outlined,
                    title: '每天发朋友圈概率',
                    subtitle:
                        '${(_settings.moments.dailyPostProbability * 100).round()}% · 后端会按这个概率生成每日动态。',
                    value: _settings.moments.dailyPostProbability,
                    onChanged: (value) {
                      setState(() {
                        _settings = _settings.copyWith(
                          moments: _settings.moments.copyWith(
                            dailyPostProbability: value,
                          ),
                        );
                      });
                      unawaited(SettingsStore.save(_settings));
                    },
                  ),
                  _SliderRow(
                    icon: Icons.image_outlined,
                    title: '朋友圈带照片概率',
                    subtitle:
                        '${(_settings.moments.photoProbability * 100).round()}% · 命中时用人物参考图保持身份一致。',
                    value: _settings.moments.photoProbability,
                    onChanged: (value) {
                      setState(() {
                        _settings = _settings.copyWith(
                          moments: _settings.moments.copyWith(
                            photoProbability: value,
                          ),
                        );
                      });
                      unawaited(SettingsStore.save(_settings));
                    },
                  ),
                  const SizedBox(height: 8),
                  _ReferenceImagePicker(
                    apiBaseUrl: _settings.apiBaseUrl,
                    imageUrl: _settings.moments.referenceImageUrl,
                    isUploading: false,
                    onTap: null,
                  ),
                  const SizedBox(height: 8),
                  _ActionRow(
                    icon: Icons.tune_rounded,
                    title: '照片公共提示词',
                    subtitle: _settings.moments.identityPromptPrefix,
                    onTap: _editMomentIdentityPrompt,
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
                  TextField(
                    controller: _adminTokenController,
                    obscureText: true,
                    decoration: const InputDecoration(
                      labelText: '后端管理口令',
                      helperText: '仅保存在本机，用于重启后端。',
                    ),
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
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: _isRestartingBackend ? null : _restartBackend,
                      icon:
                          _isRestartingBackend
                              ? const SizedBox.square(
                                dimension: 16,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                              : const Icon(Icons.restart_alt_rounded),
                      label: Text(_isRestartingBackend ? '后端重启中…' : '重启后端'),
                    ),
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
      adminToken: _adminTokenController.text.trim(),
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
      await _userTimelineService.configureBackground(next);
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

  void _setChatContext(ChatContextSettings chatContext) {
    setState(() => _settings = _settings.copyWith(chatContext: chatContext));
    unawaited(SettingsStore.save(_settings));
  }

  void _setLife(LifeSettings life) {
    setState(() => _settings = _settings.copyWith(life: life));
    unawaited(SettingsStore.save(_settings));
  }

  void _setUserTimeline(UserTimelineSettings userTimeline) {
    setState(() => _settings = _settings.copyWith(userTimeline: userTimeline));
    unawaited(SettingsStore.save(_settings));
    unawaited(_userTimelineService.configureBackground(_settings));
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

  Future<void> _editMomentIdentityPrompt() async {
    final controller = TextEditingController(
      text: _settings.moments.identityPromptPrefix,
    );
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
                    '照片公共提示词',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    '会拼在每次朋友圈照片场景前面。可用 {{companion.name}} 和 {{user.name}}。',
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
                      decoration: const InputDecoration(labelText: '公共提示词'),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      TextButton(
                        onPressed:
                            () =>
                                controller.text =
                                    defaultMomentIdentityPromptPrefix,
                        child: const Text('恢复默认'),
                      ),
                      const Spacer(),
                      TextButton(
                        onPressed: () => Navigator.of(context).pop(),
                        child: const Text('取消'),
                      ),
                      const SizedBox(width: 8),
                      FilledButton.icon(
                        onPressed:
                            () => Navigator.of(
                              context,
                            ).pop(controller.text.trim()),
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
      },
    );
    controller.dispose();
    if (result == null) return;
    final next = _settings.copyWith(
      moments: _settings.moments.copyWith(
        identityPromptPrefix:
            result.isEmpty ? defaultMomentIdentityPromptPrefix : result,
      ),
    );
    setState(() => _settings = next);
    await SettingsStore.save(next);
  }

  Future<void> _probeEnvironment() async {
    setState(() => _environmentStatus = '读取中...');
    final snapshot = await _environmentService.collect(_settings.environment);
    if (!mounted) return;
    setState(() => _environmentStatus = snapshot.label);
  }

  String _currentApiBaseUrl() {
    final raw =
        _apiBaseController.text.trim().isEmpty
            ? _settings.apiBaseUrl
            : _apiBaseController.text.trim();
    return raw.replaceAll(RegExp(r'/$'), '');
  }

  Future<void> _loadLifeRecords() async {
    if (!mounted) return;
    setState(() {
      _isLoadingLife = true;
      _lifeStatus = '读取中...';
    });
    try {
      final client = ApiClient(baseUrl: _currentApiBaseUrl());
      final stateResponse = await client.getJson('/api/life/state');
      final eventsResponse = await client.getJson('/api/life/events', {
        'limit': '24',
      });
      final life = Map<String, dynamic>.from(
        (stateResponse['life'] as Map?) ?? const {},
      );
      final events = ((eventsResponse['events'] as List?) ?? const <dynamic>[])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false);
      if (!mounted) return;
      setState(() {
        _lifeContext = life;
        _lifeEvents = events;
        _lifeStatus =
            life['enabled'] == false ? '生活模拟未启用' : '已读取 ${events.length} 条轨迹';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _lifeStatus = '读取失败：$error');
    } finally {
      if (mounted) setState(() => _isLoadingLife = false);
    }
  }

  Future<void> _advanceLifeOnce() async {
    if (_isAdvancingLife) return;
    setState(() {
      _isAdvancingLife = true;
      _lifeStatus = '正在推进生活轨迹...';
    });
    try {
      final client = ApiClient(baseUrl: _currentApiBaseUrl());
      await client.postJson('/api/life/advance', {
        'force': true,
        'settings': _settings.toBackendJson(),
      }, timeout: const Duration(seconds: 75));
      await _loadLifeRecords();
    } catch (error) {
      if (!mounted) return;
      setState(() => _lifeStatus = '推进失败：$error');
    } finally {
      if (mounted) setState(() => _isAdvancingLife = false);
    }
  }

  Future<void> _loadUserTimeline() async {
    if (!mounted) return;
    setState(() {
      _isLoadingUserTimeline = true;
      _userTimelineStatus = '读取中...';
    });
    try {
      final client = ApiClient(baseUrl: _currentApiBaseUrl());
      final stateResponse = await client.getJson('/api/user/timeline/state');
      final eventsResponse = await client.getJson('/api/user/timeline/events', {
        'limit': '36',
      });
      final timeline = Map<String, dynamic>.from(
        (stateResponse['userTimeline'] as Map?) ?? const {},
      );
      final events = ((eventsResponse['events'] as List?) ?? const <dynamic>[])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false);
      if (!mounted) return;
      setState(() {
        _userTimelineContext = timeline;
        _userTimelineEvents = events;
        _userTimelineStatus =
            timeline['enabled'] == false
                ? '用户轨迹未启用'
                : '已读取 ${events.length} 条轨迹';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _userTimelineStatus = '读取失败：$error');
    } finally {
      if (mounted) setState(() => _isLoadingUserTimeline = false);
    }
  }

  Future<void> _syncUserTimelineNow() async {
    if (_isSyncingUserTimeline) return;
    setState(() {
      _isSyncingUserTimeline = true;
      _userTimelineStatus = '正在同步手机轨迹...';
    });
    try {
      final result = await _userTimelineService.syncNow(_settings);
      await _userTimelineService.configureBackground(_settings);
      await _loadUserTimeline();
      if (!mounted) return;
      setState(() => _userTimelineStatus = result.label);
    } catch (error) {
      if (!mounted) return;
      setState(() => _userTimelineStatus = '同步失败：$error');
    } finally {
      if (mounted) setState(() => _isSyncingUserTimeline = false);
    }
  }

  Future<void> _requestUserTimelinePermissions() async {
    try {
      final message = await _userTimelineService.requestAndroidPermissions(
        _settings.userTimeline,
      );
      await _userTimelineService.configureBackground(_settings);
      if (!mounted) return;
      setState(() => _userTimelineStatus = message);
    } catch (error) {
      if (!mounted) return;
      setState(() => _userTimelineStatus = '权限处理失败：$error');
    }
  }

  Future<void> _checkBackend() async {
    setState(() => _backendStatus = '检测中...');
    try {
      final response = await ApiClient(
        baseUrl: _currentApiBaseUrl(),
      ).getJson('/api/health');
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

  Future<void> _restartBackend() async {
    final token = _adminTokenController.text.trim();
    if (token.isEmpty) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('请先填写后端管理口令')));
      return;
    }
    final confirmed = await showDialog<bool>(
      context: context,
      builder:
          (context) => AlertDialog(
            title: const Text('重启后端'),
            content: const Text('重启期间聊天和朋友圈会短暂断连，确认现在执行吗？'),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('取消'),
              ),
              FilledButton.icon(
                onPressed: () => Navigator.of(context).pop(true),
                icon: const Icon(Icons.restart_alt_rounded, size: 18),
                label: const Text('确认重启'),
              ),
            ],
          ),
    );
    if (confirmed != true || !mounted) return;
    final base =
        _apiBaseController.text.trim().isEmpty
            ? _settings.apiBaseUrl
            : _apiBaseController.text.trim().replaceAll(RegExp(r'/$'), '');
    final next = _settings.copyWith(apiBaseUrl: base, adminToken: token);
    setState(() {
      _settings = next;
      _isRestartingBackend = true;
      _backendStatus = '重启请求已提交…';
    });
    await SettingsStore.save(next);
    try {
      await ApiClient(baseUrl: base).postJson(
        '/api/admin/restart',
        const {},
        headers: {'X-Alicer-Admin-Token': token},
      );
      if (!mounted) return;
      setState(() => _backendStatus = '后端正在重启，稍后自动检测…');
      await Future<void>.delayed(const Duration(seconds: 3));
      if (mounted) await _checkBackend();
    } catch (error) {
      if (!mounted) return;
      setState(() => _backendStatus = '重启失败：$error');
    } finally {
      if (mounted) setState(() => _isRestartingBackend = false);
    }
  }
}

class _LifeRecordsPanel extends StatelessWidget {
  const _LifeRecordsPanel({
    required this.contextData,
    required this.events,
    required this.status,
    required this.isLoading,
    required this.isAdvancing,
    required this.onRefresh,
    required this.onAdvance,
  });

  final Map<String, dynamic>? contextData;
  final List<Map<String, dynamic>> events;
  final String status;
  final bool isLoading;
  final bool isAdvancing;
  final VoidCallback onRefresh;
  final VoidCallback onAdvance;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    final life = contextData ?? const <String, dynamic>{};
    final state = Map<String, dynamic>.from(
      (life['state'] as Map?) ?? const {},
    );
    final profile = Map<String, dynamic>.from(
      (life['profile'] as Map?) ?? const {},
    );
    final plan = Map<String, dynamic>.from((life['plan'] as Map?) ?? const {});
    final isEnabled = life['enabled'] != false;
    final summary = _joinFilled([
      _readString(state, 'location'),
      _readString(state, 'activity'),
      _readString(state, 'summary'),
    ], separator: ' · ');
    final occupation = _readString(profile, 'occupation', fallback: '未归纳');
    final workStyle = _readString(profile, 'workStyle', fallback: '未归纳');
    final homeBase = _readString(profile, 'homeBase', fallback: '未归纳');

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                '生活轨迹记录',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            IconButton(
              tooltip: '刷新',
              onPressed: isLoading ? null : onRefresh,
              icon:
                  isLoading
                      ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                      : const Icon(Icons.refresh_rounded),
            ),
            IconButton(
              tooltip: '推进一次',
              onPressed: isAdvancing ? null : onAdvance,
              icon:
                  isAdvancing
                      ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                      : const Icon(Icons.skip_next_rounded),
            ),
          ],
        ),
        Text(status, style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 10),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: colors.surfaceSoft,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: colors.border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                isEnabled ? '当前状态' : '当前状态 · 未启用',
                style: Theme.of(context).textTheme.titleSmall,
              ),
              const SizedBox(height: 6),
              Text(
                summary.isEmpty ? '还没有生活状态记录。' : summary,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _LifeFactChip(label: '职业', value: occupation),
                  _LifeFactChip(label: '作息', value: workStyle),
                  _LifeFactChip(label: '住处', value: homeBase),
                  _LifeFactChip(
                    label: '精力',
                    value: _formatEnergy(state['energy']),
                  ),
                  _LifeFactChip(
                    label: '心情',
                    value: _readString(state, 'mood', fallback: '未记录'),
                  ),
                ],
              ),
            ],
          ),
        ),
        if (_readString(plan, 'dayTheme').isNotEmpty) ...[
          const SizedBox(height: 10),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: colors.surfaceSoft,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: colors.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('今日计划', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 6),
                Text(
                  _readString(plan, 'dayTheme'),
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 8),
                for (final item in ((plan['plannedEvents'] as List?) ??
                        const [])
                    .whereType<Map>()
                    .take(5))
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                      _joinFilled([
                        (item['timeRange'] ?? '').toString(),
                        (item['location'] ?? '').toString(),
                        (item['activity'] ?? '').toString(),
                      ], separator: ' · '),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
              ],
            ),
          ),
        ],
        const SizedBox(height: 10),
        if (events.isEmpty)
          Text('暂无轨迹事件。', style: Theme.of(context).textTheme.bodySmall)
        else
          Column(
            children: [
              for (final event in events.take(24)) _LifeEventRow(event: event),
            ],
          ),
      ],
    );
  }
}

class _UserTimelinePanel extends StatelessWidget {
  const _UserTimelinePanel({
    required this.contextData,
    required this.events,
    required this.status,
    required this.isLoading,
    required this.isSyncing,
    required this.onRefresh,
    required this.onSyncNow,
    required this.onRequestPermissions,
  });

  final Map<String, dynamic>? contextData;
  final List<Map<String, dynamic>> events;
  final String status;
  final bool isLoading;
  final bool isSyncing;
  final VoidCallback onRefresh;
  final VoidCallback onSyncNow;
  final VoidCallback onRequestPermissions;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    final timeline = contextData ?? const <String, dynamic>{};
    final state = Map<String, dynamic>.from(
      (timeline['state'] as Map?) ?? const {},
    );
    final summary = _joinFilled([
      _readString(state, 'scene'),
      _readString(state, 'activity'),
      _joinFilled([
        _readString(state, 'city'),
        _readString(state, 'district'),
        _readString(state, 'locationLabel'),
      ], separator: ' · '),
      _readString(state, 'music'),
    ], separator: ' · ');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                '我的轨迹记录',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            IconButton(
              tooltip: '申请权限',
              onPressed: onRequestPermissions,
              icon: const Icon(Icons.verified_user_outlined),
            ),
            IconButton(
              tooltip: '同步一次',
              onPressed: isSyncing ? null : onSyncNow,
              icon:
                  isSyncing
                      ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                      : const Icon(Icons.cloud_sync_outlined),
            ),
            IconButton(
              tooltip: '刷新',
              onPressed: isLoading ? null : onRefresh,
              icon:
                  isLoading
                      ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                      : const Icon(Icons.refresh_rounded),
            ),
          ],
        ),
        Text(status, style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 10),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: colors.surfaceSoft,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: colors.border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('当前用户状态', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 6),
              Text(
                summary.isEmpty ? '还没有手机轨迹状态。' : summary,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _LifeFactChip(
                    label: '可打扰',
                    value: _readString(state, 'availability', fallback: '未知'),
                  ),
                  _LifeFactChip(
                    label: '地点更新',
                    value:
                        state['locationAgeMinutes'] == null
                            ? '未记录'
                            : '${state['locationAgeMinutes']} 分钟前',
                  ),
                  _LifeFactChip(
                    label: '地点变化',
                    value:
                        state['cityChanged'] == true
                            ? '城市变化'
                            : state['placeChanged'] == true
                            ? '地点切换'
                            : '无明显变化',
                  ),
                  _LifeFactChip(
                    label: '运动',
                    value: _readString(state, 'motion', fallback: '未记录'),
                  ),
                  if (_readString(state, 'addressHint').isNotEmpty)
                    _LifeFactChip(
                      label: '地点线索',
                      value: _readString(state, 'addressHint'),
                    ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 10),
        if (events.isEmpty)
          Text('暂无用户轨迹事件。', style: Theme.of(context).textTheme.bodySmall)
        else
          Column(
            children: [
              for (final event in events.take(36))
                _UserTimelineEventRow(event: event),
            ],
          ),
      ],
    );
  }
}

class _UserTimelineEventRow extends StatelessWidget {
  const _UserTimelineEventRow({required this.event});

  final Map<String, dynamic> event;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    final title = _joinFilled([
      _readString(event, 'timeLabel'),
      _readString(event, 'title'),
    ], separator: ' · ');
    final summary = _readString(event, 'summary', fallback: '无摘要');
    final eventType = _readString(event, 'eventType');
    final source = _readString(event, 'source', fallback: 'unknown');
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 3),
            child: Icon(
              _userTimelineIcon(eventType),
              size: 18,
              color: Theme.of(context).colorScheme.primary,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title.isEmpty ? '未标记事件' : title,
                  style: Theme.of(context).textTheme.titleSmall,
                ),
                const SizedBox(height: 2),
                Text(summary, style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 2),
                Text(
                  '$eventType · $source · 置信度 ${_formatEnergy(event['confidence'])}',
                  style: Theme.of(
                    context,
                  ).textTheme.bodySmall?.copyWith(color: colors.textMuted),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

IconData _userTimelineIcon(String eventType) {
  if (eventType.startsWith('location')) return Icons.place_outlined;
  if (eventType.startsWith('music')) return Icons.music_note_outlined;
  if (eventType.startsWith('motion')) return Icons.directions_walk_outlined;
  if (eventType.startsWith('device_headset')) return Icons.headphones_outlined;
  return Icons.phone_android_outlined;
}

class _LifeFactChip extends StatelessWidget {
  const _LifeFactChip({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: context.alicerColors.border),
      ),
      child: Text(
        '$label：$value',
        style: Theme.of(context).textTheme.bodySmall,
      ),
    );
  }
}

class _LifeEventRow extends StatelessWidget {
  const _LifeEventRow({required this.event});

  final Map<String, dynamic> event;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    final title = _joinFilled([
      _readString(event, 'timeLabel'),
      _readString(event, 'location'),
      _readString(event, 'activity'),
    ], separator: ' · ');
    final summary = _readString(event, 'summary', fallback: '无摘要');
    final mood = _readString(event, 'mood');
    final canPost = event['canPostMoment'] == true;
    final usedMomentId = _readString(event, 'usedMomentId');
    final metadata = Map<String, dynamic>.from(
      (event['metadata'] as Map?) ?? const {},
    );
    final source = _readString(metadata, 'source', fallback: 'unknown');
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 3),
            child: Icon(
              usedMomentId.isNotEmpty
                  ? Icons.check_circle_outline_rounded
                  : canPost
                  ? Icons.photo_camera_back_outlined
                  : Icons.circle,
              size: usedMomentId.isNotEmpty || canPost ? 18 : 8,
              color:
                  usedMomentId.isNotEmpty
                      ? colors.userBubble
                      : canPost
                      ? Theme.of(context).colorScheme.primary
                      : colors.textMuted,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title.isEmpty ? '未标记时间' : title,
                  style: Theme.of(context).textTheme.titleSmall,
                ),
                const SizedBox(height: 2),
                Text(summary, style: Theme.of(context).textTheme.bodySmall),
                if (mood.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(
                    '心情：$mood · 精力：${_formatEnergy(event['energy'])} · 来源：$source'
                    '${usedMomentId.isEmpty ? '' : ' · 已发朋友圈'}',
                    style: Theme.of(
                      context,
                    ).textTheme.bodySmall?.copyWith(color: colors.textMuted),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

String _readString(
  Map<String, dynamic> map,
  String key, {
  String fallback = '',
}) {
  final value = map[key]?.toString().trim() ?? '';
  return value.isEmpty ? fallback : value;
}

String _joinFilled(List<String> items, {required String separator}) {
  return items.where((item) => item.trim().isNotEmpty).join(separator);
}

String _formatEnergy(Object? value) {
  final number =
      value is num
          ? value.toDouble()
          : double.tryParse(value?.toString() ?? '');
  if (number == null) return '未记录';
  return '${(number.clamp(0.0, 1.0) * 100).round()}%';
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

class _SliderRow extends StatelessWidget {
  const _SliderRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final double value;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Icon(icon, color: colors.textMuted, size: 22),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 3),
                Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
                Slider(
                  value: value,
                  divisions: 20,
                  label: '${(value * 100).round()}%',
                  onChanged: onChanged,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _IntSliderRow extends StatelessWidget {
  const _IntSliderRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.min,
    required this.max,
    required this.divisions,
    required this.onChanged,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final int value;
  final int min;
  final int max;
  final int divisions;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Icon(icon, color: colors.textMuted, size: 22),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 3),
                Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
                Slider(
                  value: value.toDouble().clamp(min.toDouble(), max.toDouble()),
                  min: min.toDouble(),
                  max: max.toDouble(),
                  divisions: divisions,
                  label: '$value',
                  onChanged: (next) => onChanged(next.round()),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _HistoryModeRow extends StatelessWidget {
  const _HistoryModeRow({required this.value, required this.onChanged});

  final String value;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Icon(
              Icons.history_outlined,
              color: colors.textMuted,
              size: 22,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: DropdownButtonFormField<String>(
              value: normalizeHistoryMode(value),
              decoration: const InputDecoration(
                labelText: '聊天历史范围',
                helperText: '控制 prompt 中带入哪些历史消息。',
              ),
              items: const [
                DropdownMenuItem(value: 'all', child: Text('尽量不裁剪')),
                DropdownMenuItem(value: 'recent', child: Text('最近若干条')),
                DropdownMenuItem(value: 'day', child: Text('最近一天')),
                DropdownMenuItem(value: 'month', child: Text('最近一个月')),
              ],
              onChanged: (next) {
                if (next != null) onChanged(next);
              },
            ),
          ),
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

class _ReferenceImagePicker extends StatelessWidget {
  const _ReferenceImagePicker({
    required this.apiBaseUrl,
    required this.imageUrl,
    required this.isUploading,
    required this.onTap,
  });

  final String apiBaseUrl;
  final String imageUrl;
  final bool isUploading;
  final VoidCallback? onTap;

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
        child: Row(
          children: [
            _ReferenceImagePreview(
              apiBaseUrl: apiBaseUrl,
              imageUrl: imageUrl,
              size: 72,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '固定人物参考图',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 3),
                  Text(
                    imageUrl.isEmpty
                        ? '后端会使用固定参考图生成照片。'
                        : '后端会直接把这个 URL 作为 Grok image edit 参考图。',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  if (imageUrl.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(
                      imageUrl,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 8),
            isUploading
                ? const SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
                : const Icon(Icons.lock_outline_rounded),
          ],
        ),
      ),
    );
  }
}

class _ReferenceImagePreview extends StatefulWidget {
  const _ReferenceImagePreview({
    required this.apiBaseUrl,
    required this.imageUrl,
    required this.size,
  });

  final String apiBaseUrl;
  final String imageUrl;
  final double size;

  @override
  State<_ReferenceImagePreview> createState() => _ReferenceImagePreviewState();
}

class _ReferenceImagePreviewState extends State<_ReferenceImagePreview> {
  late Future<Uint8List> _imageBytes;

  @override
  void initState() {
    super.initState();
    _imageBytes = _load();
  }

  @override
  void didUpdateWidget(covariant _ReferenceImagePreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.apiBaseUrl != widget.apiBaseUrl ||
        oldWidget.imageUrl != widget.imageUrl) {
      _imageBytes = _load();
    }
  }

  Future<Uint8List> _load() {
    if (widget.imageUrl.isEmpty) {
      return Future<Uint8List>.error('empty image url');
    }
    return ApiClient(baseUrl: widget.apiBaseUrl).getBytes(widget.imageUrl);
  }

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: Container(
        width: widget.size,
        height: widget.size,
        color: color.withValues(alpha: 0.12),
        child:
            widget.imageUrl.isEmpty
                ? Icon(Icons.person_search_rounded, color: color)
                : FutureBuilder<Uint8List>(
                  future: _imageBytes,
                  builder: (context, snapshot) {
                    if (snapshot.hasData) {
                      return Image.memory(
                        snapshot.data!,
                        fit: BoxFit.cover,
                        gaplessPlayback: true,
                      );
                    }
                    if (snapshot.hasError) {
                      return Icon(Icons.broken_image_outlined, color: color);
                    }
                    return const Center(
                      child: SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                    );
                  },
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
                  Text(
                    subtitle,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
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
