import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        width: double.infinity,
        height: double.infinity,
        decoration: const BoxDecoration(
          gradient: AppTheme.warmGradient,
        ),
        child: SafeArea(
          child: LayoutBuilder(
            builder: (context, constraints) {
              return SingleChildScrollView(
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    minHeight: constraints.maxHeight,
                  ),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Logo and Title Section
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Container(
                                  width: 42,
                                  height: 42,
                                  decoration: BoxDecoration(
                                    color: AppTheme.primary,
                                    borderRadius: BorderRadius.circular(12),
                                    boxShadow: [
                                      BoxShadow(
                                        color: AppTheme.primary.withValues(alpha: 0.2),
                                        blurRadius: 8,
                                        offset: const Offset(0, 4),
                                      ),
                                    ],
                                  ),
                                  child: const Icon(
                                    Icons.restaurant_menu_rounded,
                                    color: Colors.white,
                                    size: 22,
                                  ),
                                ),
                                const SizedBox(width: 10),
                                const Text(
                                  'BiteRight',
                                  style: TextStyle(
                                    fontSize: 18,
                                    fontWeight: FontWeight.w800,
                                    color: AppTheme.text,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 32),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                              decoration: BoxDecoration(
                                color: Colors.white.withValues(alpha: 0.58),
                                borderRadius: BorderRadius.circular(99),
                                border: Border.all(color: Colors.white),
                              ),
                              child: const Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(
                                    Icons.verified_rounded,
                                    size: 15,
                                    color: AppTheme.teal,
                                  ),
                                  SizedBox(width: 6),
                                  Text(
                                    'Profile-aware label scanning',
                                    style: TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.w700,
                                      color: AppTheme.text,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(height: 12),
                            const Text(
                              'Scan food labels with confidence',
                              style: TextStyle(
                                fontSize: 36,
                                height: 1.1,
                                fontWeight: FontWeight.w900,
                                color: AppTheme.text,
                              ),
                            ),
                            const SizedBox(height: 10),
                            const Text(
                              'BiteRight checks ingredients against your allergy and dietary profile, then explains the risk in plain language.',
                              style: TextStyle(
                                fontSize: 14,
                                height: 1.45,
                                color: AppTheme.textMuted,
                              ),
                            ),
                          ],
                        ),

                        // Interactive Scan Simulation Section
                        Center(
                          child: Padding(
                            padding: const EdgeInsets.symmetric(vertical: 24.0),
                            child: Stack(
                              alignment: Alignment.center,
                              children: [
                                // Viewfinder corners/brackets
                                Container(
                                  width: 315,
                                  height: 265,
                                  decoration: BoxDecoration(
                                    borderRadius: BorderRadius.circular(28),
                                  ),
                                  child: const _ScannerViewfinder(),
                                ),
                                // Simulated Animated Product Card
                                const _AnimatedScanCard(),
                              ],
                            ),
                          ),
                        ),

                        // Action Buttons Section
                        Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            ElevatedButton.icon(
                              onPressed: () => Navigator.pushNamed(context, '/register'),
                              icon: const Icon(Icons.arrow_forward_rounded, size: 18),
                              label: const Text('Create safety profile'),
                              style: ElevatedButton.styleFrom(
                                minimumSize: const Size.fromHeight(54),
                                elevation: 2,
                                shadowColor: AppTheme.primary.withValues(alpha: 0.3),
                              ),
                            ),
                            const SizedBox(height: 12),
                            OutlinedButton(
                              onPressed: () => Navigator.pushNamed(context, '/login'),
                              style: OutlinedButton.styleFrom(
                                minimumSize: const Size.fromHeight(50),
                                backgroundColor: Colors.white.withValues(alpha: 0.4),
                              ),
                              child: const Text('I already have an account'),
                            ),
                            const SizedBox(height: 18),
                            const Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(
                                  Icons.lock_outline_rounded,
                                  size: 13,
                                  color: AppTheme.textMuted,
                                ),
                                SizedBox(width: 6),
                                Text(
                                  'Your preferences stay editable anytime',
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w500,
                                    color: AppTheme.textMuted,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 8),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

class _ScannerViewfinder extends StatelessWidget {
  const _ScannerViewfinder();

  @override
  Widget build(BuildContext context) {
    const bracketSize = 16.0;
    const bracketColor = AppTheme.primary;
    const bracketThickness = 3.0;

    return Stack(
      children: [
        // Top-left bracket
        Positioned(
          top: 0,
          left: 0,
          child: Container(
            width: bracketSize,
            height: bracketSize,
            decoration: const BoxDecoration(
              border: Border(
                top: BorderSide(color: bracketColor, width: bracketThickness),
                left: BorderSide(color: bracketColor, width: bracketThickness),
              ),
            ),
          ),
        ),
        // Top-right bracket
        Positioned(
          top: 0,
          right: 0,
          child: Container(
            width: bracketSize,
            height: bracketSize,
            decoration: const BoxDecoration(
              border: Border(
                top: BorderSide(color: bracketColor, width: bracketThickness),
                right: BorderSide(color: bracketColor, width: bracketThickness),
              ),
            ),
          ),
        ),
        // Bottom-left bracket
        Positioned(
          bottom: 0,
          left: 0,
          child: Container(
            width: bracketSize,
            height: bracketSize,
            decoration: const BoxDecoration(
              border: Border(
                bottom: BorderSide(color: bracketColor, width: bracketThickness),
                left: BorderSide(color: bracketColor, width: bracketThickness),
              ),
            ),
          ),
        ),
        // Bottom-right bracket
        Positioned(
          bottom: 0,
          right: 0,
          child: Container(
            width: bracketSize,
            height: bracketSize,
            decoration: const BoxDecoration(
              border: Border(
                bottom: BorderSide(color: bracketColor, width: bracketThickness),
                right: BorderSide(color: bracketColor, width: bracketThickness),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _AnimatedScanCard extends StatefulWidget {
  const _AnimatedScanCard();

  @override
  State<_AnimatedScanCard> createState() => _AnimatedScanCardState();
}

class _AnimatedScanCardState extends State<_AnimatedScanCard> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _animation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 4),
    );
    _animation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
    _controller.repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const double cardHeight = 230.0;

    return Container(
      width: 280,
      height: cardHeight,
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.75),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white, width: 1.5),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 16,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(20),
        child: Stack(
          children: [
            // Card Content
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'INGREDIENT LABEL',
                        style: TextStyle(
                          fontSize: 9,
                          fontWeight: FontWeight.w700,
                          color: AppTheme.textMuted,
                          letterSpacing: 0.6,
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2.5),
                        decoration: BoxDecoration(
                          color: AppTheme.teal.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: const Row(
                          children: [
                            Icon(Icons.wifi, size: 8, color: AppTheme.teal),
                            SizedBox(width: 4),
                            Text(
                              'ANALYZING',
                              style: TextStyle(
                                fontSize: 7,
                                fontWeight: FontWeight.w800,
                                color: AppTheme.teal,
                                letterSpacing: 0.3,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  const Text(
                    'Almond Butter Cookies',
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w800,
                      color: AppTheme.text,
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Ingredients:',
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.textMuted,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Wrap(
                    spacing: 4,
                    runSpacing: 4,
                    children: [
                      _buildIngredientChip('Wheat Flour'),
                      _buildIngredientChip('Sugar'),
                      _buildAllergenChip('Almonds'),
                      _buildIngredientChip('Butter'),
                      _buildIngredientChip('Salt'),
                    ],
                  ),
                  const Spacer(),
                  // Alert Badge
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    decoration: BoxDecoration(
                      color: AppTheme.cautionBg,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Row(
                      children: [
                        Icon(
                          Icons.warning_amber_rounded,
                          size: 14,
                          color: AppTheme.caution,
                        ),
                        SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            'Contains Almonds (Match: Allergy Profile)',
                            style: TextStyle(
                              fontSize: 9,
                              fontWeight: FontWeight.w700,
                              color: AppTheme.caution,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),

            // Scanning Laser Line
            AnimatedBuilder(
              animation: _animation,
              builder: (context, child) {
                final topPosition = _animation.value * cardHeight;
                return Positioned(
                  top: topPosition - 10,
                  left: 0,
                  right: 0,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // Top laser glow
                      Container(
                        height: 10,
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [
                              AppTheme.primary.withValues(alpha: 0.0),
                              AppTheme.primary.withValues(alpha: 0.12),
                            ],
                          ),
                        ),
                      ),
                      // Main laser line
                      Container(
                        height: 2.2,
                        color: AppTheme.primary,
                      ),
                      // Bottom laser glow
                      Container(
                        height: 10,
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [
                              AppTheme.primary.withValues(alpha: 0.12),
                              AppTheme.primary.withValues(alpha: 0.0),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildIngredientChip(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppTheme.border.withValues(alpha: 0.5)),
      ),
      child: Text(
        label,
        style: const TextStyle(
          fontSize: 9,
          fontWeight: FontWeight.w500,
          color: AppTheme.text,
        ),
      ),
    );
  }

  Widget _buildAllergenChip(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
      decoration: BoxDecoration(
        color: AppTheme.unsafeBg,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppTheme.unsafe.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 9,
              fontWeight: FontWeight.w700,
              color: AppTheme.unsafe,
            ),
          ),
          const SizedBox(width: 2),
          const Icon(
            Icons.close,
            size: 8,
            color: AppTheme.unsafe,
          ),
        ],
      ),
    );
  }
}