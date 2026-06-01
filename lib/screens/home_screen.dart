// lib/screens/home_screen.dart
import 'package:biteright_mobile/screens/scan_details_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import 'edit_account_screen.dart';
import 'profile_setup_screen.dart';
import 'scan_screen.dart';
import 'scan_history_screen.dart';

class HomeScreen extends StatefulWidget {
  final String userId;
  final String username;

  const HomeScreen({
    super.key,
    required this.userId,
    required this.username,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ApiService _apiService = ApiService();
  bool _isLoading = false;
  Map<String, dynamic>? _userProfile;
  List<Map<String, dynamic>> _allScans = [];
  List<Map<String, dynamic>> _recentScans = [];
  int _selectedIndex = 0;

  @override
  void initState() {
    super.initState();
    _loadUserData();
    _loadAllScans();
  }

  Future<void> _loadUserData() async {
    setState(() => _isLoading = true);
    try {
      final profile = await _apiService.getUserProfile(widget.userId);
      if (mounted) {
        setState(() {
          _userProfile = profile?['profile'];
          _isLoading = false;
        });
      }
    } catch (e) {
      if (kDebugMode) print('Error loading user data: $e');
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _loadAllScans() async {
    try {
      final scans = await _apiService.getScanHistory(widget.userId);
      if (mounted) {
        setState(() {
          _allScans = scans;
          _recentScans = scans.take(3).toList();
        });
      }
    } catch (e) {
      if (kDebugMode) print('Error loading scans: $e');
      if (mounted) {
        setState(() {
          _allScans = [];
          _recentScans = [];
        });
      }
    }
  }

  void _navigateToScanHistory() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => ScanHistoryScreen(userId: widget.userId),
      ),
    ).then((_) => _loadAllScans());
  }

  void _navigateToScanDetails(Map<String, dynamic> scan) {
    final normalized = _apiService.normalizeScanAnalysis(Map.from(scan));
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => ScanDetailsScreen(
          userId: widget.userId,
          scanId: normalized['id']?.toString() ?? '',
          scanData: normalized,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF7F4F0),
      body: IndexedStack(
        index: _selectedIndex,
        children: [
          _HomePage(
            username: widget.username,
            userId: widget.userId,
            isLoading: _isLoading,
            userProfile: _userProfile,
            totalScans: _allScans.length,
            recentScans: _recentScans,
            onScanTap: _navigateToScanDetails,
            onViewAllTap: _navigateToScanHistory,
            onScanButtonTap: () => setState(() => _selectedIndex = 1),
            onProfileButtonTap: () => setState(() => _selectedIndex = 2),
            onRefresh: () async {
              await _loadUserData();
              await _loadAllScans();
            },
          ),
          ScanScreen(
            userId: widget.userId,
            onBack: () => setState(() => _selectedIndex = 0),
          ),
          _ProfilePage(
            userId: widget.userId,
            username: widget.username,
            apiService: _apiService,
            userProfile: _userProfile,
            onNavigateToScanHistory: _navigateToScanHistory,
            onProfileUpdated: _loadUserData,
          ),
        ],
      ),
      bottomNavigationBar: _BottomNav(
        selectedIndex: _selectedIndex,
        onTap: (i) => setState(() => _selectedIndex = i),
      ),
    );
  }
}

// â”€â”€â”€ Bottom Nav â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _BottomNav extends StatelessWidget {
  final int selectedIndex;
  final ValueChanged<int> onTap;

  const _BottomNav({required this.selectedIndex, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        border: const Border(top: BorderSide(color: Color(0x0F000000))),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.06),
            blurRadius: 18,
            offset: const Offset(0, -6),
          ),
        ],
      ),
      child: SafeArea(
        top: false,
        child: BottomNavigationBar(
          currentIndex: selectedIndex,
          onTap: onTap,
          type: BottomNavigationBarType.fixed,
          backgroundColor: Colors.transparent,
          elevation: 0,
          selectedItemColor: AppTheme.primary,
          unselectedItemColor: const Color(0xFF9A9790),
          selectedLabelStyle: const TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w700,
          ),
          unselectedLabelStyle: const TextStyle(fontSize: 12),
          items: const [
            BottomNavigationBarItem(
              icon: Icon(Icons.home_outlined),
              activeIcon: Icon(Icons.home_rounded),
              label: 'Home',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.document_scanner_outlined),
              activeIcon: Icon(Icons.document_scanner_rounded),
              label: 'Scan',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.person_outline_rounded),
              activeIcon: Icon(Icons.person_rounded),
              label: 'Profile',
            ),
          ],
        ),
      ),
    );
  }
}

// â”€â”€â”€ Home Page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _HomePage extends StatelessWidget {
  final String username;
  final String userId;
  final bool isLoading;
  final Map<String, dynamic>? userProfile;
  final int totalScans;
  final List<Map<String, dynamic>> recentScans;
  final void Function(Map<String, dynamic>) onScanTap;
  final VoidCallback onViewAllTap;
  final VoidCallback onScanButtonTap;
  final VoidCallback onProfileButtonTap;
  final Future<void> Function() onRefresh;

  const _HomePage({
    required this.username,
    required this.userId,
    required this.isLoading,
    required this.userProfile,
    required this.totalScans,
    required this.recentScans,
    required this.onScanTap,
    required this.onViewAllTap,
    required this.onScanButtonTap,
    required this.onProfileButtonTap,
    required this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: isLoading
            ? const Center(
                child: CircularProgressIndicator(
                  valueColor: AlwaysStoppedAnimation<Color>(AppTheme.primary),
                ),
              )
            : RefreshIndicator(
                onRefresh: onRefresh,
                color: AppTheme.primary,
                child: SingleChildScrollView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // â”€â”€ Welcome Header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Welcome back,',
                                  style: TextStyle(
                                    fontSize: 14,
                                    fontWeight: FontWeight.w500,
                                    color: Color(0xFF9A9790),
                                    letterSpacing: 0.3,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  username,
                                  style: const TextStyle(
                                    fontSize: 28,
                                    height: 1.1,
                                    fontWeight: FontWeight.w700,
                                    color: Color(0xFF1A1814),
                                  ),
                                ),
                                const SizedBox(height: 4),
                                const Text(
                                  'Ready to check your food safety?',
                                  style: TextStyle(
                                    fontSize: 13,
                                    color: Color(0xFF9A9790),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          _ProfileShortcut(onTap: onProfileButtonTap),
                        ],
                      ),

                      const SizedBox(height: 24),

                      // â”€â”€ Hero Card â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                      _HeroCard(
                        userProfile: userProfile,
                        totalScans: totalScans,
                        onScanTap: onScanButtonTap,
                      ),

                      const SizedBox(height: 24),

                      // â”€â”€ Preferences chips â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                      if (userProfile != null &&
                          (userProfile!['allergies']?.isNotEmpty == true ||
                              userProfile!['dietary_restrictions']
                                      ?.isNotEmpty ==
                                  true)) ...[
                        _PreferencesRow(userProfile: userProfile!),
                        const SizedBox(height: 24),
                      ] else ...[
                        _ProfileReminder(onTap: onProfileButtonTap),
                        const SizedBox(height: 24),
                      ],

                      // â”€â”€ Recent Scans Section â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          const _SectionLabel(label: 'Recent scans'),
                          GestureDetector(
                            onTap: onViewAllTap,
                            child: Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 10, vertical: 4),
                              child: const Row(
                                children: [
                                  Text(
                                    'View all',
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: AppTheme.primary,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                  SizedBox(width: 4),
                                  Icon(
                                    Icons.arrow_forward_rounded,
                                    size: 14,
                                    color: AppTheme.primary,
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),

                      recentScans.isEmpty
                          ? _EmptyScans(onScanTap: onScanButtonTap)
                          : _RecentScansList(
                              scans: recentScans,
                              onTap: onScanTap,
                            ),
                    ],
                  ),
                ),
              ),
      ),
    );
  }
}

// â”€â”€â”€ Notification Bell â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _ProfileShortcut extends StatelessWidget {
  final VoidCallback onTap;

  const _ProfileShortcut({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 46,
        height: 46,
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.02),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: const Icon(
          Icons.person_outline_rounded,
          size: 22,
          color: Color(0xFF3A3835),
        ),
      ),
    );
  }
}

// â”€â”€â”€ Hero Card â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _HeroCard extends StatelessWidget {
  final Map<String, dynamic>? userProfile;
  final int totalScans;
  final VoidCallback onScanTap;

  const _HeroCard({
    required this.userProfile,
    required this.totalScans,
    required this.onScanTap,
  });

  @override
  Widget build(BuildContext context) {
    final allergyCount = (userProfile?['allergies'] as List?)?.length ?? 0;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: AppTheme.cardGradient,
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: AppTheme.primaryDark.withValues(alpha: 0.15),
            blurRadius: 24,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Label pill
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.5),
              borderRadius: BorderRadius.circular(99),
            ),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.auto_awesome_rounded,
                    size: 14, color: AppTheme.primaryDark),
                SizedBox(width: 6),
                Text(
                  'AI Food Assistant',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: AppTheme.primaryDark,
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 16),

          // Main content
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Personalised\nAllergen Check',
                      style: TextStyle(
                        fontSize: 22,
                        height: 1.2,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF1A1814),
                      ),
                    ),
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.4),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.shield_rounded,
                              size: 14, color: AppTheme.primaryDark),
                          SizedBox(width: 4),
                          Text(
                            'Real-time detection',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w500,
                              color: AppTheme.primaryDark,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              Container(
                width: 86,
                height: 86,
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.45),
                  borderRadius: BorderRadius.circular(22),
                  border: Border.all(color: Colors.white),
                ),
                child: const Icon(
                  Icons.document_scanner_rounded,
                  size: 42,
                  color: AppTheme.primaryDark,
                ),
              ),
            ],
          ),

          const SizedBox(height: 20),

          // Stats row
          Row(
            children: [
              Expanded(
                child: _StatPill(
                  icon: Icons.warning_amber_rounded,
                  iconColor: const Color(0xFFA32D2D),
                  iconBg: const Color(0xFFFDECEA),
                  label: 'Active allergies',
                  value: allergyCount.toString(),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _StatPill(
                  icon: Icons.history_rounded,
                  iconColor: const Color(0xFF2A6E54),
                  iconBg: const Color(0xFFE9F5EE),
                  label: 'Total scans',
                  value: totalScans.toString(),
                ),
              ),
            ],
          ),

          const SizedBox(height: 18),

          // CTA button
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: onScanTap,
              icon: const Icon(Icons.document_scanner_outlined, size: 18),
              label: const Text('Scan a food label'),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.primaryDark,
                foregroundColor: Colors.white,
                elevation: 0,
                padding: const EdgeInsets.symmetric(vertical: 15),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
                textStyle: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// â”€â”€â”€ Stat Pill â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _StatPill extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final Color iconBg;
  final String label;
  final String value;

  const _StatPill({
    required this.icon,
    required this.iconColor,
    required this.iconBg,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.7),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          Container(
            width: 34,
            height: 34,
            decoration: BoxDecoration(
              color: iconBg,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, size: 16, color: iconColor),
          ),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                value,
                style: const TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF1A1814),
                ),
              ),
              Text(
                label,
                style: const TextStyle(
                  fontSize: 9,
                  fontWeight: FontWeight.w500,
                  color: Color(0xFF6B6866),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// â”€â”€â”€ Preferences Row â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _PreferencesRow extends StatelessWidget {
  final Map<String, dynamic> userProfile;

  const _PreferencesRow({required this.userProfile});

  @override
  Widget build(BuildContext context) {
    final allergies = List.from(userProfile['allergies'] ?? []);
    final restrictions = List.from(userProfile['dietary_restrictions'] ?? []);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _SectionLabel(label: 'Your safety profile'),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            ...allergies.map((a) {
              final label = a is Map
                  ? (a['id']?.toString() ?? a.toString())
                  : a.toString();
              return _PreferenceChip(
                label: label,
                bg: const Color(0xFFFDECEA),
                textColor: const Color(0xFFA32D2D),
                icon: Icons.warning_amber_rounded,
              );
            }),
            ...restrictions.map((r) => _PreferenceChip(
                  label: r.toString(),
                  bg: const Color(0xFFE6F1FB),
                  textColor: const Color(0xFF185FA5),
                  icon: Icons.eco_outlined,
                )),
          ],
        ),
      ],
    );
  }
}

class _PreferenceChip extends StatelessWidget {
  final String label;
  final Color bg;
  final Color textColor;
  final IconData icon;

  const _PreferenceChip({
    required this.label,
    required this.bg,
    required this.textColor,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(99),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 13, color: textColor),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: textColor,
            ),
          ),
        ],
      ),
    );
  }
}

// â”€â”€â”€ Recent Scans List â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _ProfileReminder extends StatelessWidget {
  final VoidCallback onTap;

  const _ProfileReminder({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppTheme.primary.withValues(alpha: 0.18)),
        ),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: AppTheme.primary.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.tune_rounded,
                  color: AppTheme.primary, size: 20),
            ),
            const SizedBox(width: 12),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Complete your safety profile',
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      color: AppTheme.text,
                    ),
                  ),
                  SizedBox(height: 2),
                  Text(
                    'Add allergies and dietary rules for personalised alerts.',
                    style: TextStyle(fontSize: 12, color: AppTheme.textMuted),
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right_rounded, color: AppTheme.textMuted),
          ],
        ),
      ),
    );
  }
}

class _RecentScansList extends StatelessWidget {
  final List<Map<String, dynamic>> scans;
  final void Function(Map<String, dynamic>) onTap;

  const _RecentScansList({required this.scans, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
      ),
      child: Column(
        children: List.generate(scans.length, (i) {
          final scan = scans[i];
          // Keep full scan payload for navigation so details match scan history.
          final displayScan = {
            ...scan,
            'risk_level': scan['risk_level'] ?? 'unknown',
            'product_name': scan['product_name'] ?? 'Unknown product',
            'ingredients': scan['ingredients'] ?? [],
          };
          return _ScanTile(
            scan: displayScan,
            isLast: i == scans.length - 1,
            onTap: onTap,
          );
        }),
      ),
    );
  }
}

// â”€â”€â”€ Scan Tile â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _ScanTile extends StatelessWidget {
  final Map<String, dynamic> scan;
  final bool isLast;
  final void Function(Map<String, dynamic>) onTap;

  const _ScanTile({
    required this.scan,
    required this.isLast,
    required this.onTap,
  });

  Color _riskColor(String level) {
    switch (level) {
      case 'safe':
        return const Color(0xFF0F6E56);
      case 'caution':
        return const Color(0xFF854F0B);
      case 'unsafe':
        return const Color(0xFFA32D2D);
      default:
        return const Color(0xFF9A9790);
    }
  }

  Color _riskBg(String level) {
    switch (level) {
      case 'safe':
        return const Color(0xFFE9F5EE);
      case 'caution':
        return const Color(0xFFFEF7E6);
      case 'unsafe':
        return const Color(0xFFFDECEA);
      default:
        return const Color(0xFFF2EFE9);
    }
  }

  IconData _riskIcon(String level) {
    switch (level) {
      case 'safe':
        return Icons.check_circle_outline_rounded;
      case 'caution':
        return Icons.warning_amber_rounded;
      case 'unsafe':
        return Icons.dangerous_rounded;
      default:
        return Icons.help_outline_rounded;
    }
  }

  String _timeAgo(dynamic dateValue) {
    try {
      DateTime dt;
      if (dateValue is DateTime) {
        dt = dateValue;
      } else if (dateValue is String) {
        dt = DateTime.parse(dateValue);
      } else {
        dt = DateTime.now();
      }

      final diff = DateTime.now().difference(dt);
      if (diff.inMinutes < 1) return 'Just now';
      if (diff.inHours < 1) return '${diff.inMinutes}m ago';
      if (diff.inDays < 1) return '${diff.inHours}h ago';
      if (diff.inDays == 1) return 'Yesterday';
      if (diff.inDays < 7) return '${diff.inDays}d ago';
      return '${dt.day}/${dt.month}/${dt.year}';
    } catch (e) {
      return 'Recently';
    }
  }

  @override
  Widget build(BuildContext context) {
    final riskLevel = (scan['risk_level'] ?? 'unknown') as String;
    final productName = (scan['product_name'] ?? 'Unknown product') as String;
    final ingredients = List<String>.from(scan['ingredients'] ?? []);
    final scannedAt = scan['scanned_at'];

    return GestureDetector(
      onTap: () => onTap(scan),
      child: Container(
        decoration: BoxDecoration(
          border: isLast
              ? null
              : const Border(
                  bottom: BorderSide(color: Color(0x0A000000)),
                ),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          children: [
            // Risk icon
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: _riskBg(riskLevel),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(
                _riskIcon(riskLevel),
                size: 22,
                color: _riskColor(riskLevel),
              ),
            ),
            const SizedBox(width: 14),

            // Name + ingredients
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    productName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF1A1814),
                    ),
                  ),
                  const SizedBox(height: 4),
                  if (ingredients.isNotEmpty) ...[
                    Text(
                      ingredients.take(2).join(', '),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 12,
                        color: Color(0xFF9A9790),
                      ),
                    ),
                    const SizedBox(height: 4),
                  ],
                  Text(
                    _timeAgo(scannedAt),
                    style: const TextStyle(
                      fontSize: 11,
                      color: Color(0xFF9A9790),
                    ),
                  ),
                ],
              ),
            ),

            // Risk badge
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(
                color: _riskBg(riskLevel),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                  color: _riskColor(riskLevel).withValues(alpha: 0.3),
                ),
              ),
              child: Text(
                riskLevel[0].toUpperCase() + riskLevel.substring(1),
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: _riskColor(riskLevel),
                ),
              ),
            ),

            const SizedBox(width: 8),
            const Icon(
              Icons.chevron_right_rounded,
              size: 18,
              color: Color(0xFFBBB9B5),
            ),
          ],
        ),
      ),
    );
  }
}

// â”€â”€â”€ Empty Scans â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _EmptyScans extends StatelessWidget {
  final VoidCallback onScanTap;

  const _EmptyScans({required this.onScanTap});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 48, horizontal: 24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
      ),
      child: Column(
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              color: const Color(0xFFF2EFE9),
              borderRadius: BorderRadius.circular(18),
            ),
            child: const Icon(
              Icons.document_scanner_outlined,
              size: 30,
              color: Color(0xFF9A9790),
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            'No scans yet',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              color: Color(0xFF1A1814),
            ),
          ),
          const SizedBox(height: 6),
          const Text(
            'Upload your first ingredients image\nto see results here',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 13,
              color: Color(0xFF9A9790),
              height: 1.5,
            ),
          ),
          const SizedBox(height: 20),
          OutlinedButton.icon(
            onPressed: onScanTap,
            icon: const Icon(Icons.upload_rounded, size: 18),
            label: const Text('Upload image'),
            style: OutlinedButton.styleFrom(
              foregroundColor: AppTheme.primary,
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(99),
              ),
              side: BorderSide(color: AppTheme.primary.withValues(alpha: 0.5)),
            ),
          ),
        ],
      ),
    );
  }
}

// â”€â”€â”€ Profile Page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _ProfilePage extends StatelessWidget {
  final String userId;
  final String username;
  final ApiService apiService;
  final Map<String, dynamic>? userProfile;
  final VoidCallback onNavigateToScanHistory;
  final VoidCallback onProfileUpdated;

  const _ProfilePage({
    required this.userId,
    required this.username,
    required this.apiService,
    required this.userProfile,
    required this.onNavigateToScanHistory,
    required this.onProfileUpdated,
  });

  @override
  Widget build(BuildContext context) {
    final displayName = userProfile?['username']?.toString().isNotEmpty == true
        ? userProfile!['username'].toString()
        : username;
    final initial = displayName.isNotEmpty ? displayName[0].toUpperCase() : 'U';

    return Scaffold(
      backgroundColor: const Color(0xFFF7F4F0),
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        surfaceTintColor: Colors.transparent,
        automaticallyImplyLeading: false,
        title: const Text(
          'Profile',
          style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              color: Color(0xFF1A1814)),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // â”€â”€ Avatar + name â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
          Container(
            padding: const EdgeInsets.symmetric(vertical: 24),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
            ),
            child: Column(
              children: [
                Container(
                  width: 80,
                  height: 80,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [
                        const Color(0xFF2A6E54),
                        const Color(0xFF2A6E54).withValues(alpha: 0.8),
                      ],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    shape: BoxShape.circle,
                  ),
                  child: Center(
                    child: Text(
                      initial,
                      style: const TextStyle(
                        fontSize: 36,
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 14),
                Text(
                  displayName,
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF1A1814),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  userProfile?['email'] ?? 'user@example.com',
                  style: const TextStyle(
                    fontSize: 13,
                    color: Color(0xFF9A9790),
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 16),

          // â”€â”€ Menu â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
          _MenuCard(
            items: [
              _MenuItem(
                icon: Icons.person_outline_rounded,
                iconColor: const Color(0xFF185FA5),
                iconBg: const Color(0xFFE6F1FB),
                title: 'Edit profile',
                onTap: () => Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => EditAccountScreen(
                      userId: userId,
                      userProfile: userProfile,
                    ),
                  ),
                ).then((_) => onProfileUpdated()),
              ),
              _MenuItem(
                icon: Icons.restaurant_menu_outlined,
                iconColor: const Color(0xFF854F0B),
                iconBg: const Color(0xFFFFF3E2),
                title: 'Dietary profile',
                onTap: () => Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => ProfileSetupScreen(userId: userId),
                  ),
                ).then((_) => onProfileUpdated()),
              ),
              _MenuItem(
                icon: Icons.history_rounded,
                iconColor: const Color(0xFF2A6E54),
                iconBg: const Color(0xFFE9F5EE),
                title: 'Scan history',
                isLast: true,
                onTap: onNavigateToScanHistory,
              ),
            ],
          ),

          const SizedBox(height: 16),

          // â”€â”€ Logout â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
          GestureDetector(
            onTap: () => _showLogoutDialog(context),
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 14),
              decoration: BoxDecoration(
                color: const Color(0xFFFDECEA),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                    color: const Color(0xFFE57A75).withValues(alpha: 0.4)),
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.logout_rounded,
                      size: 18, color: Color(0xFFA32D2D)),
                  SizedBox(width: 8),
                  Text(
                    'Log out',
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFFA32D2D),
                    ),
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 16),
        ],
      ),
    );
  }

  void _showLogoutDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        title: const Text(
          'Log out',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
        content: const Text(
          'Are you sure you want to log out?',
          style: TextStyle(fontSize: 13, color: Color(0xFF5A5754)),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pushNamedAndRemoveUntil(
              context,
              '/',
              (route) => false,
            ),
            style:
                TextButton.styleFrom(foregroundColor: const Color(0xFFA32D2D)),
            child: const Text('Log out'),
          ),
        ],
      ),
    );
  }
}

// â”€â”€â”€ Menu Card â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _MenuCard extends StatelessWidget {
  final List<_MenuItem> items;

  const _MenuCard({required this.items});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
      ),
      child: Column(children: items),
    );
  }
}

class _MenuItem extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final Color iconBg;
  final String title;
  final VoidCallback onTap;
  final bool isLast;

  const _MenuItem({
    required this.icon,
    required this.iconColor,
    required this.iconBg,
    required this.title,
    required this.onTap,
    this.isLast = false,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          border: isLast
              ? null
              : const Border(
                  bottom: BorderSide(color: Color(0x0A000000)),
                ),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
        child: Row(
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: iconBg,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, size: 18, color: iconColor),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Text(
                title,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                  color: Color(0xFF1A1814),
                ),
              ),
            ),
            const Icon(
              Icons.chevron_right_rounded,
              size: 18,
              color: Color(0xFFBBB9B5),
            ),
          ],
        ),
      ),
    );
  }
}

// â”€â”€â”€ Section Label â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _SectionLabel extends StatelessWidget {
  final String label;

  const _SectionLabel({required this.label});

  @override
  Widget build(BuildContext context) {
    return Text(
      label.toUpperCase(),
      style: const TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w600,
        color: Color(0xFF9A9790),
        letterSpacing: 0.8,
      ),
    );
  }
}
