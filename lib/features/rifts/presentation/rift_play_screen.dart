import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../core/network/api_client.dart';
import '../../settings/domain/app_settings.dart';
import '../data/rift_repository.dart';
import '../domain/rift_models.dart';

class RiftPlayScreen extends StatefulWidget {
  const RiftPlayScreen({
    super.key,
    required this.settings,
    this.scenarioId,
    this.initialDetail,
  });

  final AlicerSettings settings;
  final String? scenarioId;
  final RiftDetail? initialDetail;

  @override
  State<RiftPlayScreen> createState() => _RiftPlayScreenState();
}

class _RiftPlayScreenState extends State<RiftPlayScreen> {
  late final RiftRepository _repository;
  RiftDetail? _detail;
  bool _loading = true;
  bool _choosing = false;
  String _error = '';

  @override
  void initState() {
    super.initState();
    _repository = RiftRepository(settings: widget.settings);
    final initial = widget.initialDetail;
    if (initial != null) {
      _detail = initial;
      _loading = false;
    } else {
      _load();
    }
  }

  Future<void> _load() async {
    final id = widget.scenarioId;
    if (id == null) return;
    setState(() {
      _loading = true;
      _error = '';
    });
    try {
      final detail = await _repository.getRift(id);
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString();
        _loading = false;
      });
    }
  }

  Future<void> _choose(RiftChoice choice) async {
    final scenario = _detail?.scenario;
    if (scenario == null) return;
    setState(() => _choosing = true);
    try {
      final detail = await _repository.choose(scenario.id, choice.id);
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _choosing = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _choosing = false);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('裂隙推进失败：$error')));
    }
  }

  void _showScenarioInfo() {
    final scenario = _detail?.scenario;
    if (scenario == null) return;
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => _ScenarioInfoSheet(scenario: scenario),
    );
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    return Scaffold(
      extendBodyBehindAppBar: detail != null,
      appBar: AppBar(
        title: Text(detail?.scenario.title ?? '时空裂隙'),
        backgroundColor:
            detail == null ? null : Colors.black.withValues(alpha: 0.16),
        foregroundColor: detail == null ? null : Colors.white,
        actions: [
          if (detail != null)
            IconButton(
              tooltip: '剧本信息',
              onPressed: _showScenarioInfo,
              icon: const Icon(Icons.badge_outlined),
            ),
        ],
      ),
      body:
          _loading
              ? const Center(child: CircularProgressIndicator())
              : _error.isNotEmpty
              ? Center(child: Text(_error))
              : detail == null
              ? const Center(child: Text('裂隙不存在'))
              : _RiftBody(
                settings: widget.settings,
                detail: detail,
                choosing: _choosing,
                onChoose: _choose,
              ),
    );
  }
}

class _RiftBody extends StatefulWidget {
  const _RiftBody({
    required this.settings,
    required this.detail,
    required this.choosing,
    required this.onChoose,
  });

  final AlicerSettings settings;
  final RiftDetail detail;
  final bool choosing;
  final ValueChanged<RiftChoice> onChoose;

  @override
  State<_RiftBody> createState() => _RiftBodyState();
}

class _RiftBodyState extends State<_RiftBody> {
  late final PageController _pageController;
  int _pageIndex = 0;

  @override
  void initState() {
    super.initState();
    _pageIndex = _lastIndex;
    _pageController = PageController(initialPage: _pageIndex);
  }

  @override
  void didUpdateWidget(covariant _RiftBody oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.detail.events.length != oldWidget.detail.events.length) {
      _pageIndex = _lastIndex;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || !_pageController.hasClients) return;
        _pageController.animateToPage(
          _pageIndex,
          duration: const Duration(milliseconds: 260),
          curve: Curves.easeOutCubic,
        );
      });
    }
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  int get _lastIndex => (widget.detail.events.length - 1).clamp(0, 9999);

  @override
  Widget build(BuildContext context) {
    final scenario = widget.detail.scenario;
    final colors = context.alicerColors;
    final bottomPadding = MediaQuery.paddingOf(context).bottom;
    return Stack(
      children: [
        Positioned.fill(
          child: _RiftBackground(
            settings: widget.settings,
            imageUrl: scenario.imageUrl,
          ),
        ),
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.black.withValues(alpha: 0.16),
                  Colors.black.withValues(alpha: 0.28),
                  Colors.black.withValues(alpha: 0.66),
                ],
              ),
            ),
          ),
        ),
        SafeArea(
          child: Column(
            children: [
              const SizedBox(height: 42),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Row(
                  children: [
                    _GlassPill(label: '第 ${scenario.turnCount} 轮'),
                    const SizedBox(width: 8),
                    _GlassPill(label: scenario.intensity),
                    const SizedBox(width: 8),
                    _GlassPill(label: '共 ${scenario.targetTurns} 轮'),
                    const Spacer(),
                    if (widget.detail.events.length > 1)
                      _GlassPill(
                        label:
                            '${_pageIndex + 1}/${widget.detail.events.length}',
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 10),
              Expanded(
                child: PageView.builder(
                  controller: _pageController,
                  itemCount: widget.detail.events.length,
                  onPageChanged: (index) => setState(() => _pageIndex = index),
                  itemBuilder:
                      (context, index) =>
                          _EventPage(event: widget.detail.events[index]),
                ),
              ),
              DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.34),
                  border: Border(
                    top: BorderSide(color: Colors.white.withValues(alpha: 0.1)),
                  ),
                ),
                child: Padding(
                  padding: EdgeInsets.fromLTRB(14, 10, 14, bottomPadding + 12),
                  child:
                      scenario.isEnded
                          ? _EndingSummary(scenario: scenario)
                          : Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              if (widget.choosing)
                                const Padding(
                                  padding: EdgeInsets.only(bottom: 10),
                                  child: LinearProgressIndicator(),
                                ),
                              for (final choice in scenario.currentChoices.take(
                                3,
                              )) ...[
                                SizedBox(
                                  width: double.infinity,
                                  child: FilledButton.tonal(
                                    onPressed:
                                        widget.choosing
                                            ? null
                                            : () => widget.onChoose(choice),
                                    style: FilledButton.styleFrom(
                                      alignment: Alignment.centerLeft,
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 14,
                                        vertical: 12,
                                      ),
                                      backgroundColor: Colors.white.withValues(
                                        alpha: 0.88,
                                      ),
                                      foregroundColor: colors.text,
                                    ),
                                    child: Text(
                                      '${choice.id}. ${choice.text}',
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(
                                        height: 1.2,
                                        fontSize: 14,
                                        fontWeight: FontWeight.w700,
                                      ),
                                    ),
                                  ),
                                ),
                                const SizedBox(height: 8),
                              ],
                            ],
                          ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _RiftBackground extends StatefulWidget {
  const _RiftBackground({required this.settings, required this.imageUrl});

  final AlicerSettings settings;
  final String imageUrl;

  @override
  State<_RiftBackground> createState() => _RiftBackgroundState();
}

class _RiftBackgroundState extends State<_RiftBackground> {
  Future<Uint8List>? _imageBytes;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(covariant _RiftBackground oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.imageUrl != widget.imageUrl ||
        oldWidget.settings.apiBaseUrl != widget.settings.apiBaseUrl) {
      _load();
    }
  }

  void _load() {
    final url = widget.imageUrl.trim();
    _imageBytes =
        url.isEmpty
            ? null
            : ApiClient(baseUrl: widget.settings.apiBaseUrl).getBytes(url);
  }

  @override
  Widget build(BuildContext context) {
    final future = _imageBytes;
    if (future == null) return const _FallbackBackground();
    return FutureBuilder<Uint8List>(
      future: future,
      builder: (context, snapshot) {
        final bytes = snapshot.data;
        if (bytes == null) return const _FallbackBackground();
        return Image.memory(
          bytes,
          fit: BoxFit.cover,
          width: double.infinity,
          height: double.infinity,
          gaplessPlayback: true,
        );
      },
    );
  }
}

class _FallbackBackground extends StatelessWidget {
  const _FallbackBackground();

  @override
  Widget build(BuildContext context) {
    return const DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0F766E), Color(0xFF082F49), Color(0xFF111827)],
        ),
      ),
    );
  }
}

class _EventPage extends StatelessWidget {
  const _EventPage({required this.event});

  final RiftEvent event;

  @override
  Widget build(BuildContext context) {
    final quoteColor = Theme.of(context).colorScheme.primaryContainer;
    return LayoutBuilder(
      builder: (context, constraints) {
        return Padding(
          padding: const EdgeInsets.fromLTRB(18, 0, 18, 14),
          child: Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: BoxConstraints(
                maxWidth: 560,
                maxHeight: constraints.maxHeight,
              ),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.46),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.12),
                  ),
                ),
                child: Scrollbar(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (event.choiceText.isNotEmpty) ...[
                          Text(
                            '你选择：${event.choiceText}',
                            style: TextStyle(
                              color: quoteColor,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                          const SizedBox(height: 12),
                        ],
                        if (event.sceneText.isNotEmpty)
                          Text.rich(
                            _renderStoryText(
                              event.sceneText,
                              baseColor: Colors.white.withValues(alpha: 0.94),
                              quoteColor: quoteColor,
                            ),
                            style: const TextStyle(height: 1.58, fontSize: 16),
                          ),
                        if (event.aiDialogue.isNotEmpty) ...[
                          const SizedBox(height: 12),
                          Text.rich(
                            _renderStoryText(
                              '“${event.aiDialogue}”',
                              baseColor: Colors.white.withValues(alpha: 0.86),
                              quoteColor: quoteColor,
                            ),
                            style: const TextStyle(
                              height: 1.52,
                              fontSize: 16,
                              fontStyle: FontStyle.italic,
                            ),
                          ),
                        ],
                        if (event.isEnding) ...[
                          const SizedBox(height: 12),
                          _GlassPill(label: '终局'),
                        ],
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

TextSpan _renderStoryText(
  String text, {
  required Color baseColor,
  required Color quoteColor,
}) {
  final pattern = RegExp(r'([“"][^”"\n]{1,160}[”"])');
  final spans = <TextSpan>[];
  var cursor = 0;
  for (final match in pattern.allMatches(text)) {
    if (match.start > cursor) {
      spans.add(
        TextSpan(
          text: text.substring(cursor, match.start),
          style: TextStyle(color: baseColor),
        ),
      );
    }
    spans.add(
      TextSpan(
        text: match.group(0),
        style: TextStyle(color: quoteColor, fontWeight: FontWeight.w800),
      ),
    );
    cursor = match.end;
  }
  if (cursor < text.length) {
    spans.add(
      TextSpan(
        text: text.substring(cursor),
        style: TextStyle(color: baseColor),
      ),
    );
  }
  return TextSpan(children: spans);
}

class _ScenarioInfoSheet extends StatelessWidget {
  const _ScenarioInfoSheet({required this.scenario});

  final RiftScenario scenario;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return SafeArea(
      child: ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.fromLTRB(18, 0, 18, 22),
        children: [
          Text(
            scenario.title,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _InfoChip(scenario.genre),
              _InfoChip(scenario.surfaceRelation),
              _InfoChip(scenario.intensity),
              _InfoChip('${scenario.targetTurns} 轮'),
              _InfoChip('第 ${scenario.turnCount} 轮'),
            ],
          ),
          const SizedBox(height: 18),
          _InfoLine(label: '你的身份', value: scenario.userRole),
          _InfoLine(label: '她的身份', value: scenario.aiRole),
          _InfoLine(label: '世界', value: scenario.worldSetting),
          _InfoLine(label: '核心冲突', value: scenario.coreConflict),
          if (scenario.summary.isNotEmpty)
            _InfoLine(label: '进展', value: scenario.summary),
          if (scenario.endingType.isNotEmpty)
            _InfoLine(label: '结局', value: scenario.endingType),
          const SizedBox(height: 8),
          Text(
            '隐藏关系、秘密和终局走向不会在这里剧透。',
            style: TextStyle(color: colors.textSubtle),
          ),
        ],
      ),
    );
  }
}

class _EndingSummary extends StatelessWidget {
  const _EndingSummary({required this.scenario});

  final RiftScenario scenario;

  @override
  Widget build(BuildContext context) {
    final ending = _endingName(scenario.endingType);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          ending,
          textAlign: TextAlign.center,
          style: TextStyle(
            color: Theme.of(context).colorScheme.primaryContainer,
            fontWeight: FontWeight.w900,
            fontSize: 16,
          ),
        ),
        if (scenario.summary.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(
            scenario.summary,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.white.withValues(alpha: 0.82)),
          ),
        ],
      ],
    );
  }
}

String _endingName(String endingType) {
  return switch (endingType) {
    'romance_happy_ending' => '圆满恋爱结局',
    'true_ending' => '真相相守结局',
    'sweet_ending' => '甜蜜相守结局',
    'tragic_ending' => '悲剧诀别结局',
    'betrayal_ending' => '背离破局结局',
    'collapse_ending' => '裂隙崩塌结局',
    'bittersweet_ending' => '苦甜告别结局',
    'escape_ending' => '携手逃亡结局',
    _ => '终局',
  };
}

class _InfoLine extends StatelessWidget {
  const _InfoLine({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: TextStyle(
              color: colors.textSubtle,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 4),
          Text(value, style: TextStyle(color: colors.text, height: 1.42)),
        ],
      ),
    );
  }
}

class _InfoChip extends StatelessWidget {
  const _InfoChip(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = context.alicerColors;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surfaceSoft,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        child: Text(
          label,
          style: TextStyle(color: colors.textSubtle, fontSize: 12),
        ),
      ),
    );
  }
}

class _GlassPill extends StatelessWidget {
  const _GlassPill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.32),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        child: Text(
          label,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 12,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }
}
