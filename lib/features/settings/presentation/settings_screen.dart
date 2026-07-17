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
  bool _isRefreshingLifePlan = false;
  bool _isLoadingLifeFacts = false;
  bool _isCleaningLifeFacts = false;
  bool _isRefreshingLifeFacts = false;
  bool _isLoadingUserTimeline = false;
  bool _isSyncingUserTimeline = false;
  String _environmentStatus = '尚未读取';
  String _backendStatus = '未检测';
  String _lifeStatus = '尚未读取';
  String _lifeFactsStatus = '尚未读取';
  String _userTimelineStatus = '尚未读取';
  Map<String, dynamic>? _lifeContext;
  List<Map<String, dynamic>> _lifeEvents = const [];
  List<Map<String, dynamic>> _lifeFacts = const [];
  Map<String, dynamic>? _lifeFactAudit;
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
    unawaited(_loadLifeFacts());
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
              title: '称呼与头像',
              subtitle: '她怎么称呼你、双方头像和本地头像缓存。',
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
              icon: Icons.fact_check_outlined,
              title: '01 Fact Ledger Engine · 事实账本引擎',
              subtitle: '消息先沉淀成硬事实、承诺和冲突；后面的上下文、生活计划和未来时间线都以它为准。',
              child: Column(
                children: [
                  _LifeFactsPanel(
                    facts: _lifeFacts,
                    audit: _lifeFactAudit,
                    status: _lifeFactsStatus,
                    isLoading: _isLoadingLifeFacts,
                    isCleaning: _isCleaningLifeFacts,
                    isRefreshingFacts: _isRefreshingLifeFacts,
                    onRefresh: _loadLifeFacts,
                    onCleanup: _cleanupLifeFacts,
                    onRefreshFacts: _refreshLifeFactsFromChat,
                    onCreate: _createLifeFact,
                    onEdit: _editLifeFact,
                    onComplete: _completeLifeFact,
                    onCancel: _cancelLifeFact,
                  ),
                ],
              ),
            ),
            _CollapsiblePanel(
              icon: Icons.public_rounded,
              title: '02 Environment Engine · 环境引擎',
              subtitle: '采集当前时间、地点和天气，提供给上下文引擎做运行态输入。',
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
              icon: Icons.phone_android_outlined,
              title: '03 User Timeline Engine · 用户轨迹引擎',
              subtitle: 'Android 后台归纳地点、音乐、运动和设备状态，作为用户侧上下文输入。',
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
              title: '04 Life Simulation Engine · 生活模拟引擎',
              subtitle: '后台推进她自己的活动、地点、心情和日计划；聊天、朋友圈和主动行为共享同一生活状态。',
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
                    isRefreshingPlan: _isRefreshingLifePlan,
                    onRefresh: _loadLifeRecords,
                    onAdvance: _advanceLifeOnce,
                    onRefreshPlan: _refreshLifePlan,
                  ),
                ],
              ),
            ),
            _CollapsiblePanel(
              icon: Icons.memory_rounded,
              title: '05 Context Engine · 上下文引擎',
              subtitle: '汇总事实账本、生活状态、用户轨迹、环境、记忆和聊天历史，决定每次生成能看到什么。',
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
                        '选择“最近”模式时，运行上下文最多取 ${_settings.chatContext.recentMessages} 条消息。',
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
                        '统一运行上下文最多读取 ${_settings.chatContext.maxHistoryMessages} 条历史，再压缩成最近 20 条和更早摘要。',
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
              icon: Icons.auto_awesome_outlined,
              title: '06 Prompt Engine · 提示词引擎',
              subtitle: '在 Context Engine 之后渲染人设、风格和运行上下文模板；不负责自行判断事实。',
              trailing: FilledButton.icon(
                onPressed: _showPromptPreview,
                icon: const Icon(Icons.code_rounded, size: 18),
                label: const Text('预览'),
              ),
              child: Column(
                children: [
                  ReorderableListView.builder(
                    buildDefaultDragHandles: false,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: _orderedPromptModules.length,
                    onReorder: _reorderPromptModules,
                    itemBuilder: (context, index) {
                      final module = _orderedPromptModules[index];
                      return _PromptModuleRow(
                        key: ValueKey(module.id),
                        index: index,
                        module: module,
                        onToggle:
                            (value) => _updateModule(
                              module.id,
                              module.copyWith(enabled: value),
                            ),
                        onEdit: () => _editModule(module),
                      );
                    },
                  ),
                ],
              ),
            ),
            _CollapsiblePanel(
              icon: Icons.volunteer_activism_outlined,
              title: '07 Proactive Engine · 主动引擎',
              subtitle: '基于生活模拟、事实账本和用户轨迹打分，决定是否主动聊天或发布朋友圈。',
              child: Column(
                children: [
                  _SwitchRow(
                    icon: Icons.waving_hand_outlined,
                    title: '启用主动行为',
                    subtitle: '允许后端定期评估候选动作，并按分数、冷却和静默时间决定是否执行。',
                    value: _settings.proactive.enabled,
                    onChanged:
                        (value) => _setProactive(
                          _settings.proactive.copyWith(enabled: value),
                        ),
                  ),
                  _IntSliderRow(
                    icon: Icons.update_rounded,
                    title: '评估间隔',
                    subtitle:
                        '每 ${_settings.proactive.intervalMinutes} 分钟评估一次候选动作。',
                    value: _settings.proactive.intervalMinutes,
                    min: 5,
                    max: 180,
                    divisions: 35,
                    onChanged:
                        (value) => _setProactive(
                          _settings.proactive.copyWith(intervalMinutes: value),
                        ),
                  ),
                  _ActionRow(
                    icon: Icons.nightlight_round,
                    title: '静默窗口',
                    subtitle:
                        '${_settings.proactive.quietHours.start} - ${_settings.proactive.quietHours.end} · 静默时不主动打扰。',
                    onTap: null,
                  ),
                  _IntSliderRow(
                    icon: Icons.hourglass_bottom_outlined,
                    title: '聊天前空窗',
                    subtitle:
                        '用户最后发言后至少 ${_settings.proactive.minIdleHoursBeforeChat} 小时，才考虑主动关心。',
                    value: _settings.proactive.minIdleHoursBeforeChat,
                    min: 1,
                    max: 72,
                    divisions: 71,
                    onChanged:
                        (value) => _setProactive(
                          _settings.proactive.copyWith(
                            minIdleHoursBeforeChat: value,
                          ),
                        ),
                  ),
                  _IntSliderRow(
                    icon: Icons.chat_bubble_outline_rounded,
                    title: '聊天冷却',
                    subtitle:
                        '两次主动聊天至少间隔 ${_settings.proactive.minHoursBetweenChat} 小时。',
                    value: _settings.proactive.minHoursBetweenChat,
                    min: 1,
                    max: 24,
                    divisions: 23,
                    onChanged:
                        (value) => _setProactive(
                          _settings.proactive.copyWith(
                            minHoursBetweenChat: value,
                          ),
                        ),
                  ),
                  _IntSliderRow(
                    icon: Icons.auto_awesome_motion_outlined,
                    title: '朋友圈冷却',
                    subtitle:
                        '两次主动朋友圈至少间隔 ${_settings.proactive.minHoursBetweenMoments} 小时。',
                    value: _settings.proactive.minHoursBetweenMoments,
                    min: 1,
                    max: 48,
                    divisions: 47,
                    onChanged:
                        (value) => _setProactive(
                          _settings.proactive.copyWith(
                            minHoursBetweenMoments: value,
                          ),
                        ),
                  ),
                  _IntSliderRow(
                    icon: Icons.today_outlined,
                    title: '每日主动聊天上限',
                    subtitle: '每天最多 ${_settings.proactive.maxChatPerDay} 次。',
                    value: _settings.proactive.maxChatPerDay,
                    min: 0,
                    max: 12,
                    divisions: 12,
                    onChanged:
                        (value) => _setProactive(
                          _settings.proactive.copyWith(maxChatPerDay: value),
                        ),
                  ),
                  _IntSliderRow(
                    icon: Icons.photo_camera_back_outlined,
                    title: '每日主动朋友圈上限',
                    subtitle: '每天最多 ${_settings.proactive.maxMomentsPerDay} 条。',
                    value: _settings.proactive.maxMomentsPerDay,
                    min: 0,
                    max: 6,
                    divisions: 6,
                    onChanged:
                        (value) => _setProactive(
                          _settings.proactive.copyWith(maxMomentsPerDay: value),
                        ),
                  ),
                  _SliderRow(
                    icon: Icons.speed_outlined,
                    title: '聊天触发阈值',
                    subtitle:
                        '${(_settings.proactive.chatThreshold * 100).round()}% · 越高越克制。',
                    value: _settings.proactive.chatThreshold,
                    onChanged:
                        (value) => _setProactive(
                          _settings.proactive.copyWith(chatThreshold: value),
                        ),
                  ),
                  _SliderRow(
                    icon: Icons.filter_alt_outlined,
                    title: '朋友圈触发阈值',
                    subtitle:
                        '${(_settings.proactive.momentThreshold * 100).round()}% · 越高越少发。',
                    value: _settings.proactive.momentThreshold,
                    onChanged:
                        (value) => _setProactive(
                          _settings.proactive.copyWith(momentThreshold: value),
                        ),
                  ),
                ],
              ),
            ),
            _CollapsiblePanel(
              icon: Icons.photo_camera_back_outlined,
              title: '08 Chat Photo Engine · 聊天照片引擎',
              subtitle: '处理聊天里的照片请求、主动生活照和每日生成额度。',
              child: Column(
                children: [
                  _SwitchRow(
                    icon: Icons.add_a_photo_outlined,
                    title: '启用聊天照片',
                    subtitle: '允许伴侣在聊天中自然发送自拍或生活照。',
                    value: _settings.chatPhotos.enabled,
                    onChanged:
                        (value) => _setChatPhotos(
                          _settings.chatPhotos.copyWith(enabled: value),
                        ),
                  ),
                  _SwitchRow(
                    icon: Icons.person_search_outlined,
                    title: '响应用户要照片',
                    subtitle: '用户明确要自拍、穿搭照或生活照时，允许消耗额度生成。',
                    value: _settings.chatPhotos.allowRequested,
                    onChanged:
                        (value) => _setChatPhotos(
                          _settings.chatPhotos.copyWith(allowRequested: value),
                        ),
                  ),
                  _SwitchRow(
                    icon: Icons.auto_awesome_outlined,
                    title: '允许主动发照片',
                    subtitle: '只有氛围和生活状态都合适时才会主动，仍受每日额度限制。',
                    value: _settings.chatPhotos.allowProactive,
                    onChanged:
                        (value) => _setChatPhotos(
                          _settings.chatPhotos.copyWith(allowProactive: value),
                        ),
                  ),
                  _IntSliderRow(
                    icon: Icons.today_outlined,
                    title: '每日成功发送上限',
                    subtitle:
                        '${_settings.chatPhotos.dailySuccessfulLimit} 张 · 生成前检查，避免图片成本失控。',
                    value: _settings.chatPhotos.dailySuccessfulLimit,
                    min: 0,
                    max: 5,
                    divisions: 5,
                    onChanged:
                        (value) => _setChatPhotos(
                          _settings.chatPhotos.copyWith(
                            dailySuccessfulLimit: value,
                          ),
                        ),
                  ),
                  _IntSliderRow(
                    icon: Icons.timelapse_outlined,
                    title: '最小发送间隔',
                    subtitle:
                        '${_settings.chatPhotos.minHoursBetweenPhotos} 小时 · 防止一天内连续刷照片。',
                    value: _settings.chatPhotos.minHoursBetweenPhotos,
                    min: 0,
                    max: 72,
                    divisions: 24,
                    onChanged:
                        (value) => _setChatPhotos(
                          _settings.chatPhotos.copyWith(
                            minHoursBetweenPhotos: value,
                          ),
                        ),
                  ),
                ],
              ),
            ),
            _CollapsiblePanel(
              icon: Icons.photo_camera_back_outlined,
              title: '09 Moment Engine · 朋友圈引擎',
              subtitle: '生成朋友圈正文、评论回复和配图；主动发布由 Proactive Engine 触发。',
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
              title: '10 Runtime & Model · 运行时与模型',
              subtitle: 'Alicer 后端地址、管理口令、DeepSeek 模型和生成参数。',
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

  List<PromptModule> get _orderedPromptModules {
    return [..._settings.promptModules]..sort((a, b) {
      final order = a.order.compareTo(b.order);
      if (order != 0) return order;
      return a.title.compareTo(b.title);
    });
  }

  void _reorderPromptModules(int oldIndex, int newIndex) {
    final modules = _orderedPromptModules;
    if (newIndex > oldIndex) newIndex -= 1;
    final moved = modules.removeAt(oldIndex);
    modules.insert(newIndex, moved);
    final reordered = [
      for (var i = 0; i < modules.length; i++)
        modules[i].copyWith(order: (i + 1) * 10),
    ];
    setState(() => _settings = _settings.copyWith(promptModules: reordered));
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

  void _setChatPhotos(ChatPhotoSettings chatPhotos) {
    setState(() => _settings = _settings.copyWith(chatPhotos: chatPhotos));
    unawaited(SettingsStore.save(_settings));
  }

  void _setProactive(ProactiveSettings proactive) {
    setState(() => _settings = _settings.copyWith(proactive: proactive));
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
    final result = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (context) => _PromptModuleEditorScreen(module: module),
      ),
    );
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

  Future<void> _loadLifeFacts() async {
    if (!mounted) return;
    setState(() {
      _isLoadingLifeFacts = true;
      _lifeFactsStatus = '读取中...';
    });
    try {
      final response = await ApiClient(
        baseUrl: _currentApiBaseUrl(),
      ).getJson('/api/life/facts', {'status': 'all', 'limit': '80'});
      final facts = ((response['facts'] as List?) ?? const <dynamic>[])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false);
      final audit = Map<String, dynamic>.from(
        (response['audit'] as Map?) ?? const {},
      );
      if (!mounted) return;
      setState(() {
        _lifeFacts = facts;
        _lifeFactAudit = audit;
        _lifeFactsStatus = '已读取 ${facts.length} 条事实';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _lifeFactsStatus = '读取失败：$error');
    } finally {
      if (mounted) setState(() => _isLoadingLifeFacts = false);
    }
  }

  Future<void> _cleanupLifeFacts() async {
    if (_isCleaningLifeFacts) return;
    setState(() {
      _isCleaningLifeFacts = true;
      _lifeFactsStatus = '正在清理事实账本...';
    });
    try {
      await ApiClient(
        baseUrl: _currentApiBaseUrl(),
      ).postJson('/api/life/facts/cleanup', const {});
      await _loadLifeFacts();
    } catch (error) {
      if (!mounted) return;
      setState(() => _lifeFactsStatus = '清理失败：$error');
    } finally {
      if (mounted) setState(() => _isCleaningLifeFacts = false);
    }
  }

  Future<void> _refreshLifeFactsFromChat() async {
    if (_isRefreshingLifeFacts) return;
    setState(() {
      _isRefreshingLifeFacts = true;
      _lifeFactsStatus = '正在从最近聊天重抽生活事实...';
    });
    try {
      final response = await ApiClient(baseUrl: _currentApiBaseUrl()).postJson(
        '/api/life/facts/refresh',
        {'limit': 60, 'settings': _settings.toBackendJson()},
        timeout: const Duration(seconds: 90),
      );
      final savedCount = ((response['savedFacts'] as List?) ?? const []).length;
      await _loadLifeFacts();
      if (!mounted) return;
      setState(() => _lifeFactsStatus = '重抽完成，新增/更新 $savedCount 条事实');
    } catch (error) {
      if (!mounted) return;
      setState(() => _lifeFactsStatus = '重抽失败：$error');
    } finally {
      if (mounted) setState(() => _isRefreshingLifeFacts = false);
    }
  }

  Future<void> _createLifeFact() async {
    final payload = await _showLifeFactEditor();
    if (payload == null) return;
    try {
      await ApiClient(baseUrl: _currentApiBaseUrl()).postJson(
        '/api/life/facts',
        payload,
        timeout: const Duration(seconds: 30),
      );
      await _loadLifeFacts();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('创建事实失败：$error')));
    }
  }

  Future<void> _editLifeFact(Map<String, dynamic> fact) async {
    final id = _readString(fact, 'id');
    if (id.isEmpty) return;
    final payload = await _showLifeFactEditor(fact: fact);
    if (payload == null) return;
    try {
      await ApiClient(
        baseUrl: _currentApiBaseUrl(),
      ).patchJson('/api/life/facts/$id', payload);
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('更新事实失败：$error')));
      return;
    }
    await _loadLifeFacts();
  }

  Future<void> _completeLifeFact(Map<String, dynamic> fact) async {
    await _setLifeFactTerminalStatus(fact, action: 'complete', label: '完成');
  }

  Future<void> _cancelLifeFact(Map<String, dynamic> fact) async {
    await _setLifeFactTerminalStatus(fact, action: 'cancel', label: '取消');
  }

  Future<void> _setLifeFactTerminalStatus(
    Map<String, dynamic> fact, {
    required String action,
    required String label,
  }) async {
    final id = _readString(fact, 'id');
    if (id.isEmpty) return;
    try {
      await ApiClient(
        baseUrl: _currentApiBaseUrl(),
      ).postJson('/api/life/facts/$id/$action', const {});
      await _loadLifeFacts();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('$label事实失败：$error')));
    }
  }

  Future<Map<String, dynamic>?> _showLifeFactEditor({
    Map<String, dynamic>? fact,
  }) async {
    final titleController = TextEditingController(
      text: _readString(fact ?? const {}, 'title'),
    );
    final summaryController = TextEditingController(
      text: _readString(fact ?? const {}, 'summary'),
    );
    final startController = TextEditingController(
      text: _formatFactTimeInput((fact ?? const {})['startsAt']),
    );
    final endController = TextEditingController(
      text: _formatFactTimeInput((fact ?? const {})['endsAt']),
    );
    var type = _normalizeFactType(_readString(fact ?? const {}, 'type'));
    var status = _normalizeFactStatus(_readString(fact ?? const {}, 'status'));
    final result = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
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
                        fact == null ? '新增生活事实' : '编辑生活事实',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(
                            child: DropdownButtonFormField<String>(
                              value: type,
                              decoration: const InputDecoration(
                                labelText: '类型',
                              ),
                              items: const [
                                DropdownMenuItem(
                                  value: 'schedule_commitment',
                                  child: Text('日程/计划'),
                                ),
                                DropdownMenuItem(
                                  value: 'relationship_commitment',
                                  child: Text('关系承诺'),
                                ),
                                DropdownMenuItem(
                                  value: 'current_state',
                                  child: Text('当前状态'),
                                ),
                                DropdownMenuItem(
                                  value: 'profile_fact',
                                  child: Text('稳定设定'),
                                ),
                                DropdownMenuItem(
                                  value: 'life_event_hint',
                                  child: Text('生活线索'),
                                ),
                                DropdownMenuItem(
                                  value: 'moment_posted',
                                  child: Text('朋友圈已发'),
                                ),
                              ],
                              onChanged:
                                  (value) =>
                                      setSheetState(() => type = value ?? type),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: DropdownButtonFormField<String>(
                              value: status,
                              decoration: const InputDecoration(
                                labelText: '状态',
                              ),
                              items: const [
                                DropdownMenuItem(
                                  value: 'candidate',
                                  child: Text('候选'),
                                ),
                                DropdownMenuItem(
                                  value: 'planned',
                                  child: Text('计划中'),
                                ),
                                DropdownMenuItem(
                                  value: 'active',
                                  child: Text('正在发生'),
                                ),
                                DropdownMenuItem(
                                  value: 'completed',
                                  child: Text('已完成'),
                                ),
                                DropdownMenuItem(
                                  value: 'cancelled',
                                  child: Text('已取消'),
                                ),
                              ],
                              onChanged:
                                  (value) => setSheetState(
                                    () => status = value ?? status,
                                  ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: titleController,
                        decoration: const InputDecoration(labelText: '标题'),
                      ),
                      const SizedBox(height: 12),
                      Expanded(
                        child: TextField(
                          controller: summaryController,
                          expands: true,
                          minLines: null,
                          maxLines: null,
                          textAlignVertical: TextAlignVertical.top,
                          decoration: const InputDecoration(labelText: '摘要'),
                        ),
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: startController,
                              decoration: const InputDecoration(
                                labelText: '开始时间',
                                helperText: '例：2026-07-17T18:30',
                              ),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: TextField(
                              controller: endController,
                              decoration: const InputDecoration(
                                labelText: '结束时间',
                                helperText: '可留空',
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          TextButton.icon(
                            onPressed: () => Navigator.of(context).pop(),
                            icon: const Icon(Icons.close_rounded, size: 18),
                            label: const Text('取消'),
                          ),
                          const Spacer(),
                          FilledButton.icon(
                            onPressed: () {
                              final title = titleController.text.trim();
                              final summary = summaryController.text.trim();
                              if (title.isEmpty && summary.isEmpty) return;
                              Navigator.of(context).pop({
                                'type': type,
                                'status': status,
                                'title': title,
                                'summary': summary,
                                if (startController.text.trim().isNotEmpty)
                                  'startsAt': startController.text.trim(),
                                if (endController.text.trim().isNotEmpty)
                                  'endsAt': endController.text.trim(),
                                'confidence': 0.88,
                                'importance': 0.72,
                              });
                            },
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
      },
    );
    titleController.dispose();
    summaryController.dispose();
    startController.dispose();
    endController.dispose();
    return result;
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
      unawaited(_loadLifeFacts());
    } catch (error) {
      if (!mounted) return;
      setState(() => _lifeStatus = '推进失败：$error');
    } finally {
      if (mounted) setState(() => _isAdvancingLife = false);
    }
  }

  Future<void> _refreshLifePlan() async {
    if (_isRefreshingLifePlan) return;
    setState(() {
      _isRefreshingLifePlan = true;
      _lifeStatus = '正在重编今日生活计划...';
    });
    try {
      await ApiClient(baseUrl: _currentApiBaseUrl()).postJson(
        '/api/life/plan/refresh',
        {'settings': _settings.toBackendJson(), 'forceProfile': true},
        timeout: const Duration(seconds: 90),
      );
      await _loadLifeRecords();
      unawaited(_loadLifeFacts());
    } catch (error) {
      if (!mounted) return;
      setState(() => _lifeStatus = '重编计划失败：$error');
    } finally {
      if (mounted) setState(() => _isRefreshingLifePlan = false);
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
    required this.isRefreshingPlan,
    required this.onRefresh,
    required this.onAdvance,
    required this.onRefreshPlan,
  });

  final Map<String, dynamic>? contextData;
  final List<Map<String, dynamic>> events;
  final String status;
  final bool isLoading;
  final bool isAdvancing;
  final bool isRefreshingPlan;
  final VoidCallback onRefresh;
  final VoidCallback onAdvance;
  final VoidCallback onRefreshPlan;

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
    final lifeConstraints = Map<String, dynamic>.from(
      (life['lifeConstraints'] as Map?) ?? const {},
    );
    final routine = Map<String, dynamic>.from(
      (life['routine'] as Map?) ?? (profile['routine'] as Map?) ?? const {},
    );
    final hardBlocks =
        ((lifeConstraints['hardBlocks'] as List?) ?? const <dynamic>[])
            .whereType<Map>()
            .toList();
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
              tooltip: '重编今日计划',
              onPressed: isRefreshingPlan ? null : onRefreshPlan,
              icon:
                  isRefreshingPlan
                      ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                      : const Icon(Icons.event_repeat_outlined),
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
                    label: '节律',
                    value: _readString(routine, 'type', fallback: '未归纳'),
                  ),
                  _LifeFactChip(label: '硬日程', value: '${hardBlocks.length}'),
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
                if (hardBlocks.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Text('锁定日程', style: Theme.of(context).textTheme.labelMedium),
                  for (final item in hardBlocks.take(4))
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

class _LifeFactsPanel extends StatelessWidget {
  const _LifeFactsPanel({
    required this.facts,
    required this.audit,
    required this.status,
    required this.isLoading,
    required this.isCleaning,
    required this.isRefreshingFacts,
    required this.onRefresh,
    required this.onCleanup,
    required this.onRefreshFacts,
    required this.onCreate,
    required this.onEdit,
    required this.onComplete,
    required this.onCancel,
  });

  final List<Map<String, dynamic>> facts;
  final Map<String, dynamic>? audit;
  final String status;
  final bool isLoading;
  final bool isCleaning;
  final bool isRefreshingFacts;
  final VoidCallback onRefresh;
  final VoidCallback onCleanup;
  final VoidCallback onRefreshFacts;
  final VoidCallback onCreate;
  final ValueChanged<Map<String, dynamic>> onEdit;
  final ValueChanged<Map<String, dynamic>> onComplete;
  final ValueChanged<Map<String, dynamic>> onCancel;

  @override
  Widget build(BuildContext context) {
    final warnings = ((audit?['warnings'] as List?) ?? const <dynamic>[])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
    final counts = Map<String, dynamic>.from(
      (audit?['counts'] as Map?) ?? const {},
    );
    final activeFacts = facts
        .where((item) {
          final status = _readString(item, 'status');
          return status == 'candidate' ||
              status == 'planned' ||
              status == 'active';
        })
        .toList(growable: false);
    final historyFacts = facts.where((item) => !activeFacts.contains(item));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                '生活事实账本',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            IconButton(
              tooltip: '新增事实',
              onPressed: onCreate,
              icon: const Icon(Icons.add_rounded),
            ),
            IconButton(
              tooltip: '从最近聊天重抽事实',
              onPressed: isRefreshingFacts ? null : onRefreshFacts,
              icon:
                  isRefreshingFacts
                      ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                      : const Icon(Icons.psychology_alt_outlined),
            ),
            IconButton(
              tooltip: '清理过期事实',
              onPressed: isCleaning ? null : onCleanup,
              icon:
                  isCleaning
                      ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                      : const Icon(Icons.cleaning_services_outlined),
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
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final entry in counts.entries)
              _LifeFactChip(
                label: _factStatusLabel(entry.key),
                value: '${entry.value}',
              ),
            if (warnings.isNotEmpty)
              _LifeFactChip(label: '审计提醒', value: '${warnings.length}'),
          ],
        ),
        if (warnings.isNotEmpty) ...[
          const SizedBox(height: 8),
          for (final warning in warnings.take(3))
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                _readString(warning, 'message', fallback: '有事实需要检查。'),
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(context).colorScheme.error,
                ),
              ),
            ),
        ],
        const SizedBox(height: 10),
        if (facts.isEmpty)
          Text('暂无生活事实。', style: Theme.of(context).textTheme.bodySmall)
        else
          Column(
            children: [
              for (final fact in activeFacts.take(40))
                _LifeFactRow(
                  fact: fact,
                  onEdit: () => onEdit(fact),
                  onComplete: () => onComplete(fact),
                  onCancel: () => onCancel(fact),
                ),
              if (historyFacts.isNotEmpty) ...[
                const SizedBox(height: 12),
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    '历史事实',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                ),
                for (final fact in historyFacts.take(24))
                  _LifeFactRow(
                    fact: fact,
                    muted: true,
                    onEdit: () => onEdit(fact),
                    onComplete: () => onComplete(fact),
                    onCancel: () => onCancel(fact),
                  ),
              ],
            ],
          ),
      ],
    );
  }
}

class _LifeFactRow extends StatelessWidget {
  const _LifeFactRow({
    required this.fact,
    required this.onEdit,
    required this.onComplete,
    required this.onCancel,
    this.muted = false,
  });

  final Map<String, dynamic> fact;
  final VoidCallback onEdit;
  final VoidCallback onComplete;
  final VoidCallback onCancel;
  final bool muted;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    final status = _readString(fact, 'status', fallback: 'candidate');
    final type = _readString(fact, 'type');
    final title = _readString(fact, 'title', fallback: '未命名事实');
    final summary = _readString(fact, 'summary');
    final timeWindow = _readString(fact, 'timeWindow');
    final isTerminal =
        status == 'completed' ||
        status == 'cancelled' ||
        status == 'superseded' ||
        status == 'expired' ||
        status == 'archived';
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onEdit,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(top: 3),
                child: Icon(
                  _lifeFactIcon(type),
                  size: 18,
                  color:
                      muted
                          ? colors.textMuted
                          : Theme.of(context).colorScheme.primary,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        color: muted ? colors.textMuted : null,
                      ),
                    ),
                    if (summary.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(
                        summary,
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: muted ? colors.textMuted : null,
                        ),
                      ),
                    ],
                    const SizedBox(height: 3),
                    Text(
                      _joinFilled([
                        _factTypeLabel(type),
                        _factStatusLabel(status),
                        timeWindow,
                        '置信度 ${_formatEnergy(fact['confidence'])}',
                      ], separator: ' · '),
                      style: Theme.of(
                        context,
                      ).textTheme.bodySmall?.copyWith(color: colors.textMuted),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 6),
              PopupMenuButton<String>(
                tooltip: '事实操作',
                icon: const Icon(Icons.more_horiz_rounded),
                onSelected: (value) {
                  if (value == 'edit') onEdit();
                  if (value == 'complete') onComplete();
                  if (value == 'cancel') onCancel();
                },
                itemBuilder:
                    (context) => [
                      const PopupMenuItem(value: 'edit', child: Text('编辑')),
                      if (!isTerminal)
                        const PopupMenuItem(
                          value: 'complete',
                          child: Text('标记完成'),
                        ),
                      if (!isTerminal)
                        const PopupMenuItem(
                          value: 'cancel',
                          child: Text('取消事实'),
                        ),
                    ],
              ),
            ],
          ),
        ),
      ),
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

IconData _lifeFactIcon(String factType) {
  switch (factType) {
    case 'schedule_commitment':
      return Icons.event_available_outlined;
    case 'relationship_commitment':
      return Icons.favorite_border_rounded;
    case 'current_state':
      return Icons.my_location_outlined;
    case 'profile_fact':
      return Icons.badge_outlined;
    case 'life_event_hint':
      return Icons.lightbulb_outline_rounded;
    case 'moment_posted':
      return Icons.photo_camera_back_outlined;
  }
  return Icons.account_tree_outlined;
}

String _factTypeLabel(String factType) {
  switch (factType) {
    case 'schedule_commitment':
      return '日程/计划';
    case 'relationship_commitment':
      return '关系承诺';
    case 'current_state':
      return '当前状态';
    case 'profile_fact':
      return '稳定设定';
    case 'life_event_hint':
      return '生活线索';
    case 'moment_posted':
      return '朋友圈已发';
  }
  return factType.isEmpty ? '事实' : factType;
}

String _factStatusLabel(String status) {
  switch (status) {
    case 'candidate':
      return '候选';
    case 'planned':
      return '计划中';
    case 'active':
      return '正在发生';
    case 'completed':
      return '已完成';
    case 'cancelled':
      return '已取消';
    case 'superseded':
      return '已替代';
    case 'expired':
      return '已过期';
    case 'archived':
      return '已归档';
  }
  return status.isEmpty ? '未知' : status;
}

String _normalizeFactType(String value) {
  const allowed = {
    'schedule_commitment',
    'relationship_commitment',
    'current_state',
    'profile_fact',
    'life_event_hint',
    'moment_posted',
  };
  return allowed.contains(value) ? value : 'schedule_commitment';
}

String _normalizeFactStatus(String value) {
  const allowed = {'candidate', 'planned', 'active', 'completed', 'cancelled'};
  return allowed.contains(value) ? value : 'candidate';
}

String _formatFactTimeInput(Object? value) {
  final number =
      value is num
          ? value.toDouble()
          : double.tryParse(value?.toString() ?? '');
  if (number == null || number <= 0) return '';
  final date =
      DateTime.fromMillisecondsSinceEpoch((number * 1000).round()).toLocal();
  String two(int value) => value.toString().padLeft(2, '0');
  return '${date.year}-${two(date.month)}-${two(date.day)}T'
      '${two(date.hour)}:${two(date.minute)}';
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
    this.trailing,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final Widget child;
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
    super.key,
    required this.index,
    required this.module,
    required this.onToggle,
    required this.onEdit,
  });

  final int index;
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
              ReorderableDragStartListener(
                index: index,
                child: Tooltip(
                  message: '拖动排序',
                  child: SizedBox(
                    width: 34,
                    height: 42,
                    child: Icon(
                      Icons.drag_indicator_rounded,
                      color: colors.textMuted,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 4),
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
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Switch(value: module.enabled, onChanged: onToggle),
              const Icon(Icons.chevron_right_rounded),
            ],
          ),
        ),
      ),
    );
  }
}

class _PromptModuleEditorScreen extends StatefulWidget {
  const _PromptModuleEditorScreen({required this.module});

  final PromptModule module;

  @override
  State<_PromptModuleEditorScreen> createState() =>
      _PromptModuleEditorScreenState();
}

class _PromptModuleEditorScreenState extends State<_PromptModuleEditorScreen> {
  late final TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.module.content);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.module.title),
        actions: [
          IconButton(
            tooltip: '保存',
            onPressed: () => Navigator.of(context).pop(_controller.text.trim()),
            icon: const Icon(Icons.check_rounded),
          ),
        ],
      ),
      body: DecoratedBox(
        decoration: BoxDecoration(color: colors.background),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      width: 42,
                      height: 42,
                      decoration: BoxDecoration(
                        color: Theme.of(
                          context,
                        ).colorScheme.primary.withValues(alpha: 0.10),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Icon(widget.module.icon, size: 22),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        widget.module.description,
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Expanded(
                  child: TextField(
                    controller: _controller,
                    expands: true,
                    minLines: null,
                    maxLines: null,
                    textAlignVertical: TextAlignVertical.top,
                    decoration: const InputDecoration(labelText: '模块提示词'),
                    style: const TextStyle(height: 1.45),
                  ),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    TextButton.icon(
                      onPressed: () => Navigator.of(context).pop(),
                      icon: const Icon(Icons.close_rounded, size: 18),
                      label: const Text('取消'),
                    ),
                    const Spacer(),
                    FilledButton.icon(
                      onPressed:
                          () => Navigator.of(
                            context,
                          ).pop(_controller.text.trim()),
                      icon: const Icon(Icons.check_rounded, size: 18),
                      label: const Text('保存'),
                    ),
                  ],
                ),
              ],
            ),
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
  final VoidCallback? onTap;

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
            if (onTap != null) const Icon(Icons.chevron_right_rounded),
          ],
        ),
      ),
    );
  }
}
