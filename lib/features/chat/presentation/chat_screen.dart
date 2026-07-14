import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../app/theme.dart';
import '../../environment/application/environment_service.dart';
import '../../settings/data/settings_store.dart';
import '../../settings/domain/app_settings.dart';
import '../data/chat_cache_store.dart';
import '../data/chat_repository.dart';
import '../domain/chat_models.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _textController = TextEditingController();
  final _scrollController = ScrollController();
  final _cacheStore = ChatCacheStore.instance;
  final _environmentService = EnvironmentService();

  AlicerSettings _settings = const AlicerSettings();
  List<ChatMessage> _messages = const <ChatMessage>[];
  bool _isLoading = true;
  bool _isSending = false;
  String _statusText = '正在整理今天的心情';
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final settings = await SettingsStore.load();
    final cached = await _cacheStore.loadMessages();
    if (!mounted) return;
    setState(() {
      _settings = settings;
      _messages = cached.isEmpty ? _starterMessages(settings) : cached;
      _isLoading = false;
    });
    unawaited(_refreshFromServer(settings));
  }

  Future<void> _refreshFromServer(AlicerSettings settings) async {
    try {
      final remote = await ChatRepository(settings: settings).fetchMessages();
      if (!mounted || remote.isEmpty) return;
      setState(() {
        _messages = remote;
        _error = null;
      });
      await _cacheStore.saveMessages(remote);
      _jumpToBottom();
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = '后端暂时连不上，正在使用本地缓存');
    }
  }

  Future<void> _send() async {
    final text = _textController.text.trim();
    if (text.isEmpty || _isSending) return;
    _textController.clear();
    final userMessage = ChatMessage(
      id: 'local_user_${DateTime.now().microsecondsSinceEpoch}',
      role: 'user',
      content: text,
      createdAt: DateTime.now(),
    );
    final pending = ChatMessage(
      id: 'local_pending_${DateTime.now().microsecondsSinceEpoch}',
      role: 'assistant',
      content: '我在想怎么认真回应你...',
      createdAt: DateTime.now(),
      isPending: true,
    );
    setState(() {
      _isSending = true;
      _statusText = '正在回复';
      _messages = [..._messages, userMessage, pending];
      _error = null;
    });
    _jumpToBottom();
    await _cacheStore.saveMessages(
      _messages.where((m) => !m.isPending).toList(),
    );
    try {
      final environment = await _environmentService.collect(
        _settings.environment,
      );
      final reply = await ChatRepository(
        settings: _settings,
      ).sendMessage(text: text, environment: environment.payload);
      if (!mounted) return;
      final next = [
        ..._messages.where((message) => message.id != pending.id),
        reply,
      ];
      setState(() {
        _messages = next;
        _isSending = false;
        _statusText = environment.label;
      });
      await _cacheStore.saveMessages(next);
      _jumpToBottom();
    } catch (error) {
      if (!mounted) return;
      final failed = pending.copyWith(
        content: '刚刚没连上后端。你说的话我已经先存在本地了，等网络恢复再继续。',
        isPending: false,
        isError: true,
      );
      final next = [
        ..._messages.where((message) => message.id != pending.id),
        failed,
      ];
      setState(() {
        _messages = next;
        _isSending = false;
        _statusText = '本地缓存中';
        _error = error.toString();
      });
      await _cacheStore.saveMessages(next);
      _jumpToBottom();
    }
  }

  void _jumpToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 260),
        curve: Curves.easeOutCubic,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    final companion = _settings.companion;

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        titleSpacing: 16,
        backgroundColor: colors.background.withValues(alpha: 0.9),
        title: Row(
          children: [
            _Avatar(path: companion.aiAvatarPath, label: companion.name),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(companion.name),
                  const SizedBox(height: 2),
                  Text(
                    _statusText,
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: '同步消息',
            onPressed: () => unawaited(_refreshFromServer(_settings)),
            icon: const Icon(Icons.sync_rounded),
          ),
        ],
      ),
      body: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Theme.of(context).colorScheme.primary.withValues(alpha: 0.10),
              colors.background,
              colors.background,
            ],
          ),
        ),
        child: SafeArea(
          child: Column(
            children: [
              if (_error != null)
                _OfflineBanner(
                  text: _error!.contains('本地缓存') ? _error! : '网络不稳定，消息已缓存在本机',
                ),
              Expanded(
                child:
                    _isLoading
                        ? const Center(child: CircularProgressIndicator())
                        : ListView.builder(
                          controller: _scrollController,
                          padding: const EdgeInsets.fromLTRB(14, 16, 14, 18),
                          itemCount: _messages.length,
                          itemBuilder: (context, index) {
                            final message = _messages[index];
                            return _MessageBubble(
                              message: message,
                              companion: companion,
                            );
                          },
                        ),
              ),
              _Composer(
                controller: _textController,
                isSending: _isSending,
                onSend: _send,
              ),
            ],
          ),
        ),
      ),
    );
  }

  List<ChatMessage> _starterMessages(AlicerSettings settings) {
    final now = DateTime.now();
    return [
      ChatMessage(
        id: 'starter_1',
        role: 'assistant',
        content: '我在这里。先把你想说的告诉我，我会记住重要的事，也会把该留在本地的东西先留在本地。',
        createdAt: now,
      ),
    ];
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message, required this.companion});

  final ChatMessage message;
  final CompanionProfile companion;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    final isUser = message.isUser;
    final bubbleColor =
        message.isError
            ? Theme.of(context).colorScheme.errorContainer
            : isUser
            ? colors.userBubble
            : colors.companionBubble;
    final textColor =
        message.isError
            ? Theme.of(context).colorScheme.onErrorContainer
            : isUser
            ? colors.userBubbleText
            : colors.text;
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisAlignment:
            isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (!isUser) ...[
            _Avatar(
              path: companion.aiAvatarPath,
              label: companion.name,
              size: 34,
            ),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 560),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: bubbleColor,
                  borderRadius: BorderRadius.circular(18).copyWith(
                    bottomLeft: Radius.circular(isUser ? 18 : 6),
                    bottomRight: Radius.circular(isUser ? 6 : 18),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: colors.shadow,
                      blurRadius: 18,
                      offset: const Offset(0, 8),
                    ),
                  ],
                ),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            isUser ? companion.userName : companion.name,
                            style: TextStyle(
                              color: textColor.withValues(alpha: 0.72),
                              fontSize: 12,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            DateFormat('HH:mm').format(message.createdAt),
                            style: TextStyle(
                              color: textColor.withValues(alpha: 0.48),
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(
                        message.content,
                        style: TextStyle(color: textColor, height: 1.48),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          if (isUser) ...[
            const SizedBox(width: 8),
            _Avatar(
              path: companion.userAvatarPath,
              label: companion.userName,
              size: 34,
            ),
          ],
        ],
      ),
    );
  }
}

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.isSending,
    required this.onSend,
  });

  final TextEditingController controller;
  final bool isSending;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Container(
      decoration: BoxDecoration(
        color: colors.surface.withValues(alpha: 0.96),
        border: Border(top: BorderSide(color: colors.border)),
      ),
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
      child: Row(
        children: [
          IconButton(
            tooltip: '更多',
            onPressed: () {},
            icon: const Icon(Icons.add_circle_outline),
          ),
          Expanded(
            child: TextField(
              controller: controller,
              minLines: 1,
              maxLines: 4,
              textInputAction: TextInputAction.send,
              onSubmitted: (_) => onSend(),
              decoration: const InputDecoration(hintText: '和她说点什么'),
            ),
          ),
          const SizedBox(width: 8),
          FilledButton(
            onPressed: isSending ? null : onSend,
            style: FilledButton.styleFrom(
              fixedSize: const Size(48, 48),
              padding: EdgeInsets.zero,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
            ),
            child:
                isSending
                    ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                    : const Icon(Icons.arrow_upward_rounded),
          ),
        ],
      ),
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.path, required this.label, this.size = 38});

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
                    label.isEmpty ? 'A' : label.characters.first,
                    style: TextStyle(
                      color: color,
                      fontWeight: FontWeight.w800,
                      fontSize: size * 0.38,
                    ),
                  ),
                ),
      ),
    );
  }
}

class _OfflineBanner extends StatelessWidget {
  const _OfflineBanner({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: Theme.of(context).colorScheme.secondaryContainer,
      child: Text(
        text,
        style: TextStyle(
          color: Theme.of(context).colorScheme.onSecondaryContainer,
        ),
      ),
    );
  }
}
