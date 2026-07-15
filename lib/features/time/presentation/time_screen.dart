import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../app/theme.dart';
import '../../settings/data/settings_store.dart';
import '../../settings/domain/app_settings.dart';
import '../data/moment_cache_store.dart';
import '../data/moment_image_cache_store.dart';
import '../data/time_repository.dart';
import '../domain/time_models.dart';

class TimeScreen extends StatefulWidget {
  const TimeScreen({super.key});

  @override
  State<TimeScreen> createState() => _TimeScreenState();
}

class _TimeScreenState extends State<TimeScreen>
    with SingleTickerProviderStateMixin {
  AlicerSettings _settings = const AlicerSettings();
  final _dayKey = GlobalKey<_DiaryListState>();
  final _weekKey = GlobalKey<_DiaryListState>();
  final _monthKey = GlobalKey<_DiaryListState>();
  late final TabController _tabController;
  bool _loaded = false;

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this)..addListener(() {
      if (!_tabController.indexIsChanging && mounted) setState(() {});
    });
    unawaited(_loadSettings());
  }

  Future<void> _loadSettings() async {
    final settings = await SettingsStore.load();
    if (!mounted) return;
    setState(() {
      _settings = settings;
      _loaded = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!_loaded) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return Scaffold(
      appBar: AppBar(
        title: const Text('时光'),
        actions: [
          IconButton(
            tooltip: '生成',
            onPressed: _generateCurrent,
            icon: const Icon(Icons.add_rounded),
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          tabs: const [Tab(text: '日记'), Tab(text: '周记'), Tab(text: '月记')],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          DiaryList(key: _dayKey, settings: _settings, kind: 'day'),
          DiaryList(key: _weekKey, settings: _settings, kind: 'week'),
          DiaryList(key: _monthKey, settings: _settings, kind: 'month'),
        ],
      ),
    );
  }

  void _generateCurrent() {
    switch (_tabController.index) {
      case 1:
        _weekKey.currentState?._generateCurrent();
        return;
      case 2:
        _monthKey.currentState?._generateCurrent();
        return;
      default:
        _dayKey.currentState?._generateCurrent();
    }
  }
}

class MomentsScreen extends StatefulWidget {
  const MomentsScreen({super.key});

  @override
  State<MomentsScreen> createState() => _MomentsScreenState();
}

class _MomentsScreenState extends State<MomentsScreen> {
  final _feedKey = GlobalKey<_MomentsFeedState>();
  AlicerSettings _settings = const AlicerSettings();
  bool _loaded = false;

  @override
  void initState() {
    super.initState();
    unawaited(_loadSettings());
  }

  Future<void> _loadSettings() async {
    final settings = await SettingsStore.load();
    if (!mounted) return;
    setState(() {
      _settings = settings;
      _loaded = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!_loaded) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return Scaffold(
      appBar: AppBar(
        title: const Text('朋友圈'),
        actions: [
          IconButton(
            tooltip: '生成朋友圈',
            onPressed: () => _feedKey.currentState?._generate(),
            icon: const Icon(Icons.add_rounded),
          ),
        ],
      ),
      body: MomentsFeed(key: _feedKey, settings: _settings),
    );
  }
}

class MomentsFeed extends StatefulWidget {
  const MomentsFeed({super.key, required this.settings});

  final AlicerSettings settings;

  @override
  State<MomentsFeed> createState() => _MomentsFeedState();
}

class _MomentsFeedState extends State<MomentsFeed> {
  late final TimeRepository _repo = TimeRepository(settings: widget.settings);
  final _cacheStore = MomentCacheStore.instance;
  final _commentController = TextEditingController();
  List<MomentPost> _moments = const [];
  String? _replyingTo;
  bool _loading = true;
  bool _generating = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _commentController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final cached = await _cacheStore.loadMoments();
    if (!mounted) return;
    if (cached.isNotEmpty) {
      setState(() {
        _moments = cached;
        _loading = false;
        _error = null;
      });
      if (await _cacheStore.isFresh()) return;
    }
    await _refreshFromServer(showLoading: cached.isEmpty);
  }

  Future<void> _refreshFromServer({bool showLoading = false}) async {
    if (showLoading && mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final moments = await _repo.listMoments();
      if (!mounted) return;
      setState(() {
        _moments = moments;
        _loading = false;
        _error = null;
      });
      await _cacheStore.saveMoments(moments);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        if (_moments.isEmpty) _error = '$error';
        _loading = false;
      });
    }
  }

  Future<void> _generate() async {
    setState(() => _generating = true);
    try {
      await _repo.generateMoment();
      await _refreshFromServer();
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }

  Future<void> _toggleLike(MomentPost post) async {
    final userName = widget.settings.companion.userName;
    final liked = !post.likes.contains(userName);
    final next = await _repo.setLike(post.id, userName, liked);
    if (next != null && mounted) _replace(next);
  }

  Future<void> _sendComment(MomentPost post) async {
    final text = _commentController.text.trim();
    if (text.isEmpty) return;
    _commentController.clear();
    final next = await _repo.comment(
      post.id,
      widget.settings.companion.userName,
      text,
    );
    if (next != null && mounted) {
      _replace(next);
      setState(() => _replyingTo = null);
    }
  }

  void _replace(MomentPost next) {
    setState(() {
      _moments = [
        for (final item in _moments)
          if (item.id == next.id) next else item,
      ];
    });
    unawaited(_cacheStore.upsertMoment(next));
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return _EmptyState(icon: Icons.wifi_off_rounded, text: _error!);
    }
    return RefreshIndicator(
      onRefresh: () => _refreshFromServer(),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 28),
        children: [
          if (_generating) ...[
            const LinearProgressIndicator(minHeight: 2),
            const SizedBox(height: 12),
          ],
          for (final post in _moments)
            _MomentCard(
              post: post,
              settings: widget.settings,
              replying: _replyingTo == post.id,
              controller: _commentController,
              onLike: () => _toggleLike(post),
              onComment:
                  () => setState(
                    () => _replyingTo = _replyingTo == post.id ? null : post.id,
                  ),
              onSendComment: () => _sendComment(post),
            ),
        ],
      ),
    );
  }
}

class DiaryList extends StatefulWidget {
  const DiaryList({super.key, required this.settings, required this.kind});

  final AlicerSettings settings;
  final String kind;

  @override
  State<DiaryList> createState() => _DiaryListState();
}

class _DiaryListState extends State<DiaryList> {
  late final TimeRepository _repo = TimeRepository(settings: widget.settings);
  List<TimeEntry> _entries = const [];
  bool _loading = true;
  bool _generating = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final entries = await _repo.listDiary(widget.kind);
      if (!mounted) return;
      setState(() {
        _entries = entries;
        _loading = false;
        _error = null;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = '$error';
        _loading = false;
      });
    }
  }

  Future<void> _generateCurrent() async {
    setState(() => _generating = true);
    try {
      await _repo.generateDiary(widget.kind, _currentPeriodKey(widget.kind));
      await _load();
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return _EmptyState(icon: Icons.wifi_off_rounded, text: _error!);
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 28),
        itemCount: _entries.length + (_generating ? 1 : 0),
        separatorBuilder: (_, _) => const SizedBox(height: 12),
        itemBuilder: (context, index) {
          if (_generating && index == 0) {
            return const LinearProgressIndicator(minHeight: 2);
          }
          final entryIndex = _generating ? index - 1 : index;
          return _DiaryCard(entry: _entries[entryIndex]);
        },
      ),
    );
  }
}

class _MomentCard extends StatelessWidget {
  const _MomentCard({
    required this.post,
    required this.settings,
    required this.replying,
    required this.controller,
    required this.onLike,
    required this.onComment,
    required this.onSendComment,
  });

  final MomentPost post;
  final AlicerSettings settings;
  final bool replying;
  final TextEditingController controller;
  final VoidCallback onLike;
  final VoidCallback onComment;
  final VoidCallback onSendComment;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    final userLiked = post.likes.contains(settings.companion.userName);
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.border),
        borderRadius: BorderRadius.circular(8),
      ),
      padding: const EdgeInsets.fromLTRB(12, 14, 12, 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Avatar(path: settings.companion.aiAvatarPath, label: post.author),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  post.author,
                  style: const TextStyle(
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF46669C),
                  ),
                ),
                const SizedBox(height: 6),
                Text(post.content, style: const TextStyle(height: 1.45)),
                if (post.imageUrl.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: AspectRatio(
                      aspectRatio: 1,
                      child: _MomentImage(
                        apiBaseUrl: settings.apiBaseUrl,
                        imageUrl: post.imageUrl,
                      ),
                    ),
                  ),
                ],
                const SizedBox(height: 8),
                Row(
                  children: [
                    Text(
                      DateFormat('MM-dd HH:mm').format(post.createdAt),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const Spacer(),
                    IconButton(
                      tooltip: userLiked ? '取消点赞' : '点赞',
                      onPressed: onLike,
                      icon: Icon(
                        userLiked
                            ? Icons.favorite_rounded
                            : Icons.favorite_border_rounded,
                        size: 20,
                      ),
                    ),
                    IconButton(
                      tooltip: '评论',
                      onPressed: onComment,
                      icon: const Icon(Icons.mode_comment_outlined, size: 20),
                    ),
                  ],
                ),
                if (post.likes.isNotEmpty || post.comments.isNotEmpty)
                  _MomentSocialBox(likes: post.likes, comments: post.comments),
                if (replying) ...[
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: controller,
                          minLines: 1,
                          maxLines: 3,
                          decoration: const InputDecoration(hintText: '评论一句'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      IconButton.filled(
                        tooltip: '发送评论',
                        onPressed: onSendComment,
                        icon: const Icon(Icons.send_rounded),
                      ),
                    ],
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

class _MomentImage extends StatefulWidget {
  const _MomentImage({required this.apiBaseUrl, required this.imageUrl});

  final String apiBaseUrl;
  final String imageUrl;

  @override
  State<_MomentImage> createState() => _MomentImageState();
}

class _MomentImageState extends State<_MomentImage> {
  late Future<Uint8List> _imageBytes;

  @override
  void initState() {
    super.initState();
    _imageBytes = _loadImage();
  }

  @override
  void didUpdateWidget(covariant _MomentImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.apiBaseUrl != widget.apiBaseUrl ||
        oldWidget.imageUrl != widget.imageUrl) {
      _imageBytes = _loadImage();
    }
  }

  Future<Uint8List> _loadImage() {
    return MomentImageCacheStore.instance.loadImage(
      apiBaseUrl: widget.apiBaseUrl,
      imageUrl: widget.imageUrl,
    );
  }

  @override
  Widget build(BuildContext context) {
    final fallbackColor = Theme.of(context).colorScheme.surfaceContainerHighest;
    return FutureBuilder<Uint8List>(
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
          return Container(
            color: fallbackColor,
            child: const Icon(Icons.broken_image_outlined),
          );
        }
        return Container(
          color: fallbackColor,
          child: const Center(
            child: SizedBox.square(
              dimension: 22,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          ),
        );
      },
    );
  }
}

class _MomentSocialBox extends StatelessWidget {
  const _MomentSocialBox({required this.likes, required this.comments});

  final List<String> likes;
  final List<MomentComment> comments;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: Theme.of(
          context,
        ).colorScheme.surfaceContainerHighest.withValues(alpha: 0.55),
        borderRadius: BorderRadius.circular(6),
      ),
      padding: const EdgeInsets.all(8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (likes.isNotEmpty)
            Text(
              '❤ ${likes.join('、')}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          for (final comment in comments)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text.rich(
                TextSpan(
                  children: [
                    TextSpan(
                      text: comment.author,
                      style: const TextStyle(
                        fontWeight: FontWeight.w800,
                        color: Color(0xFF46669C),
                      ),
                    ),
                    const TextSpan(text: '：'),
                    TextSpan(text: comment.content),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _DiaryCard extends StatelessWidget {
  const _DiaryCard({required this.entry});

  final TimeEntry entry;

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
      padding: const EdgeInsets.all(15),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(entry.periodKey, style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 6),
          Text(
            entry.title.isEmpty ? entry.periodKey : entry.title,
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 10),
          Text(
            entry.content.isEmpty
                ? entry.status == 'generating'
                    ? '正在写...'
                    : entry.error.isEmpty
                    ? '还没有内容'
                    : entry.error
                : entry.content.replaceAll(
                  RegExp(r'^#+\\s*', multiLine: true),
                  '',
                ),
            style: const TextStyle(height: 1.56),
          ),
        ],
      ),
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.path, required this.label});

  final String path;
  final String label;

  @override
  Widget build(BuildContext context) {
    final file = path.isEmpty ? null : File(path);
    return ClipRRect(
      borderRadius: BorderRadius.circular(6),
      child: Container(
        width: 42,
        height: 42,
        color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.12),
        child:
            file != null && file.existsSync()
                ? Image.file(file, fit: BoxFit.cover)
                : Center(
                  child: Text(label.isEmpty ? 'A' : label.characters.first),
                ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 38),
            const SizedBox(height: 12),
            Text(text, textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}

String _currentPeriodKey(String kind) {
  final now = DateTime.now();
  if (kind == 'month') return DateFormat('yyyy-MM').format(now);
  if (kind == 'week') {
    final dayOfYear = int.parse(DateFormat('D').format(now));
    final week = ((dayOfYear - now.weekday + 10) / 7).floor();
    return '${now.year}-W${week.toString().padLeft(2, '0')}';
  }
  return DateFormat('yyyy-MM-dd').format(now);
}
