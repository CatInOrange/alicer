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
    if (cached.isEmpty || !(await _cacheStore.isFresh())) {
      unawaited(_refreshFromServer(settings));
    }
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
      if (_isNearBottom()) _scrollToBottom(animated: false);
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
      content: '正在回复…',
      createdAt: DateTime.now(),
      isPending: true,
    );
    setState(() {
      _isSending = true;
      _statusText = '正在回复';
      _messages = [..._messages, userMessage, pending];
      _error = null;
    });
    _scrollToBottom(animated: false);
    await _cacheStore.saveMessages(_messages, markSynced: false);
    try {
      final environment = await _environmentService.collect(
        _settings.environment,
      );
      ChatMessage? reply;
      var visibleText = '';
      var streamedMessage = pending;
      await for (final event in ChatRepository(
        settings: _settings,
      ).streamMessage(text: text, environment: environment.payload)) {
        if (!mounted) return;
        if (event.type == 'start') {
          final rawUser = event.payload['userMessage'];
          if (rawUser is Map) {
            _replaceMessage(
              userMessage.id,
              ChatMessage.fromJson(Map<String, dynamic>.from(rawUser)),
            );
          }
          final rawAssistant = event.payload['assistantMessage'];
          if (rawAssistant is Map) {
            streamedMessage = ChatMessage.fromJson(
              Map<String, dynamic>.from(rawAssistant),
            ).copyWith(
              content: visibleText.isEmpty ? '正在回复…' : visibleText,
              isPending: true,
            );
            _replaceMessage(pending.id, streamedMessage);
            await _cacheStore.saveMessages(_messages, markSynced: false);
          }
        } else if (event.type == 'chunk') {
          visibleText += (event.payload['delta'] ?? '').toString();
          streamedMessage = streamedMessage.copyWith(content: visibleText);
          _replaceMessage(streamedMessage.id, streamedMessage);
          await _cacheStore.saveMessage(streamedMessage);
          _followStreamIfNeeded();
        } else if (event.type == 'final') {
          final raw = event.payload['assistantMessage'];
          if (raw is Map) {
            reply = ChatMessage.fromJson(Map<String, dynamic>.from(raw));
          }
        } else if (event.type == 'error') {
          throw Exception(event.payload['error'] ?? 'stream error');
        }
      }
      reply ??= streamedMessage.copyWith(
        content: visibleText.isEmpty ? '我刚刚走神了一下，再和我说一遍好不好。' : visibleText,
        isPending: false,
      );
      if (!mounted) return;
      final next = [
        ..._messages.where((message) => message.id != streamedMessage.id),
        reply,
      ];
      setState(() {
        _messages = next;
        _isSending = false;
        _statusText = environment.label;
      });
      await _cacheStore.saveMessages(next);
      _scrollToBottom(animated: true);
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
      await _cacheStore.saveMessages(next, markSynced: false);
      _scrollToBottom(animated: true);
    }
  }

  void _replaceMessage(String id, ChatMessage next) {
    setState(() {
      _messages = [
        for (final message in _messages)
          if (message.id == id) next else message,
      ];
    });
  }

  bool _isNearBottom() {
    if (!_scrollController.hasClients) return true;
    final position = _scrollController.position;
    return position.pixels < 120;
  }

  void _followStreamIfNeeded() {
    if (_isNearBottom()) _scrollToBottom(animated: false);
  }

  void _scrollToBottom({required bool animated}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      if (animated) {
        _scrollController.animateTo(
          0,
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
        );
      } else {
        _scrollController.jumpTo(0);
      }
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
                          reverse: true,
                          padding: const EdgeInsets.fromLTRB(14, 16, 14, 18),
                          itemCount: _messages.length,
                          itemBuilder: (context, index) {
                            final message =
                                _messages[_messages.length - 1 - index];
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
                      Text.rich(
                        _renderMessageContent(message.content, textColor),
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

TextSpan _renderMessageContent(String text, Color color) {
  final spans = <TextSpan>[];
  final pattern = RegExp(r'(\([^()\n]{1,80}\)|（[^（）\n]{1,80}）)');
  var cursor = 0;
  for (final match in pattern.allMatches(text)) {
    if (match.start > cursor) {
      spans.add(TextSpan(text: text.substring(cursor, match.start)));
    }
    spans.add(
      TextSpan(
        text: text.substring(match.start, match.end),
        style: TextStyle(
          color: color.withValues(alpha: 0.58),
          fontStyle: FontStyle.italic,
        ),
      ),
    );
    cursor = match.end;
  }
  if (cursor < text.length) {
    spans.add(TextSpan(text: text.substring(cursor)));
  }
  return TextSpan(children: spans.isEmpty ? [TextSpan(text: text)] : spans);
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

  static const List<String> _quickEmojis = [
    '😀',
    '😁',
    '😂',
    '😊',
    '🥰',
    '😘',
    '🤔',
    '🥺',
    '😎',
    '😭',
    '😡',
    '👍',
    '👏',
    '🙏',
    '💪',
    '❤️',
    '💕',
    '✨',
    '🌸',
    '🌙',
    '☀️',
    '🎉',
    '🍜',
    '🍵',
  ];

  void _insertEmoji(String emoji) {
    final value = controller.value;
    final selection = value.selection;
    final start =
        selection.isValid
            ? selection.start.clamp(0, value.text.length).toInt()
            : value.text.length;
    final end =
        selection.isValid
            ? selection.end.clamp(0, value.text.length).toInt()
            : value.text.length;
    final nextText = value.text.replaceRange(start, end, emoji);
    final nextOffset = start + emoji.length;
    controller.value = value.copyWith(
      text: nextText,
      selection: TextSelection.collapsed(offset: nextOffset),
      composing: TextRange.empty,
    );
  }

  Future<void> _showEmojiPicker(BuildContext context) async {
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (context) {
        final colors = context.alicerColors;
        return SafeArea(
          child: Container(
            margin: const EdgeInsets.fromLTRB(12, 0, 12, 10),
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 16),
            decoration: BoxDecoration(
              color: colors.surface,
              borderRadius: BorderRadius.circular(22),
              border: Border.all(color: colors.border),
              boxShadow: [
                BoxShadow(
                  color: colors.shadow,
                  blurRadius: 24,
                  offset: const Offset(0, 10),
                ),
              ],
            ),
            child: GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: _quickEmojis.length,
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 8,
                mainAxisSpacing: 8,
                crossAxisSpacing: 8,
              ),
              itemBuilder: (context, index) {
                final emoji = _quickEmojis[index];
                return InkWell(
                  borderRadius: BorderRadius.circular(18),
                  onTap: () {
                    _insertEmoji(emoji);
                    Navigator.of(context).pop();
                  },
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: colors.surfaceSoft.withValues(alpha: 0.62),
                      borderRadius: BorderRadius.circular(18),
                    ),
                    child: Center(
                      child: Text(emoji, style: const TextStyle(fontSize: 22)),
                    ),
                  ),
                );
              },
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    final theme = Theme.of(context);
    return Container(
      decoration: BoxDecoration(
        color: colors.surface.withValues(alpha: 0.96),
        border: Border(top: BorderSide(color: colors.border)),
      ),
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: colors.surfaceSoft,
              borderRadius: BorderRadius.circular(19),
            ),
            child: IconButton(
              tooltip: '表情',
              padding: EdgeInsets.zero,
              iconSize: 21,
              onPressed:
                  isSending ? null : () => unawaited(_showEmojiPicker(context)),
              color: isSending ? colors.textMuted : theme.colorScheme.primary,
              icon: const Icon(Icons.emoji_emotions_outlined),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: colors.inputBackground,
                borderRadius: BorderRadius.circular(20),
                boxShadow: [
                  BoxShadow(
                    color: colors.shadow,
                    blurRadius: 14,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: TextField(
                controller: controller,
                minLines: 1,
                maxLines: 4,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => onSend(),
                decoration: const InputDecoration(
                  hintText: '和她说点什么',
                  isDense: true,
                ),
              ),
            ),
          ),
          const SizedBox(width: 6),
          AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color:
                  isSending
                      ? theme.colorScheme.primary.withValues(alpha: 0.38)
                      : theme.colorScheme.primary,
              borderRadius: BorderRadius.circular(19),
              boxShadow: [
                BoxShadow(
                  color: theme.colorScheme.primary.withValues(alpha: 0.22),
                  blurRadius: 16,
                  offset: const Offset(0, 6),
                ),
              ],
            ),
            child: IconButton(
              tooltip: '发送',
              padding: EdgeInsets.zero,
              iconSize: 20,
              onPressed: isSending ? null : onSend,
              color: Colors.white,
              icon:
                  isSending
                      ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                      : const Icon(Icons.arrow_upward_rounded),
            ),
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
