import 'package:alicer/app/app.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Alicer shell shows the primary tabs', (tester) async {
    await tester.pumpWidget(const AlicerApp());

    expect(find.text('聊天'), findsOneWidget);
    expect(find.text('发现'), findsOneWidget);
    expect(find.text('配置'), findsOneWidget);
    expect(find.text('Alice'), findsWidgets);

    await tester.tap(find.text('发现'));
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('朋友圈'), findsOneWidget);
    expect(find.text('时空裂隙'), findsOneWidget);
    expect(find.text('时光轮'), findsOneWidget);
  });
}
