import 'package:flutter/material.dart';

import '../../../app/theme.dart';

class ChatScreen extends StatelessWidget {
  const ChatScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 16,
        title: Row(
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: Theme.of(
                  context,
                ).colorScheme.primary.withValues(alpha: 0.12),
                shape: BoxShape.circle,
              ),
              child: Icon(
                Icons.favorite,
                size: 20,
                color: Theme.of(context).colorScheme.primary,
              ),
            ),
            const SizedBox(width: 12),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Alice'),
                  SizedBox(height: 2),
                  Text(
                    '正在想你今天过得怎么样',
                    style: TextStyle(fontSize: 12, fontWeight: FontWeight.w500),
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: '生成日记',
            onPressed: () {},
            icon: const Icon(Icons.edit_note_outlined),
          ),
          IconButton(
            tooltip: '聊天设置',
            onPressed: () {},
            icon: const Icon(Icons.more_horiz),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                children: const [
                  _MessageBubble(
                    author: 'Alice',
                    text: '早呀。今天我会先记住两件事：你要写 Alicer，还有你想让配置页像酒馆一样可控。',
                  ),
                  _MessageBubble(
                    author: '你',
                    text: '第一版先别太复杂，但配置页要能看到提示词怎么拼。',
                    isUser: true,
                  ),
                  _MessageBubble(
                    author: 'Alice',
                    text:
                        '嗯，我会把角色、性格、时间、地点、天气、长期记忆和短期记忆都拆成模块。你可以开关，也可以预览最终提示词。',
                  ),
                ],
              ),
            ),
            Container(
              decoration: BoxDecoration(
                color: colors.surface,
                border: Border(top: BorderSide(color: colors.border)),
              ),
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
              child: Row(
                children: [
                  IconButton(
                    tooltip: '添加',
                    onPressed: () {},
                    icon: const Icon(Icons.add_circle_outline),
                  ),
                  Expanded(
                    child: TextField(
                      minLines: 1,
                      maxLines: 4,
                      decoration: InputDecoration(
                        hintText: '和 Alice 说点什么',
                        suffixIcon: IconButton(
                          tooltip: '语音',
                          onPressed: () {},
                          icon: const Icon(Icons.mic_none),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: () {},
                    style: FilledButton.styleFrom(
                      fixedSize: const Size(48, 48),
                      padding: EdgeInsets.zero,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                    ),
                    child: const Icon(Icons.arrow_upward),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({
    required this.author,
    required this.text,
    this.isUser = false,
  });

  final String author;
  final String text;
  final bool isUser;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    final bubbleColor = isUser ? colors.userBubble : colors.companionBubble;
    final textColor = isUser ? colors.userBubbleText : colors.text;

    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Align(
        alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
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
                  Text(
                    author,
                    style: TextStyle(
                      color: textColor.withValues(alpha: 0.72),
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 5),
                  Text(text, style: TextStyle(color: textColor, height: 1.45)),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
