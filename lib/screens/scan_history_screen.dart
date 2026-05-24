// lib/screens/scan_history_screen.dart
import 'package:flutter/material.dart';
import '../services/api_service.dart';
import 'scan_details_screen.dart';
import '../theme/app_theme.dart';

class ScanHistoryScreen extends StatefulWidget {
  final String userId;
  
  const ScanHistoryScreen({super.key, required this.userId});

  @override
  State<ScanHistoryScreen> createState() => _ScanHistoryScreenState();
}

class _ScanHistoryScreenState extends State<ScanHistoryScreen> {
  final ApiService _apiService = ApiService();
  List<Map<String, dynamic>> _scans = [];
  bool _isLoading = true;
  String? _errorMessage;
  String _filter = 'all'; // 'all', 'safe', 'caution', 'unsafe'

  @override
  void initState() {
    super.initState();
    _loadScanHistory();
  }

  Future<void> _loadScanHistory() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final scans = await _apiService.getScanHistory(widget.userId);
      
      // CRITICAL FIX: DO NOT recalculate - use the stored values directly
      // Just ensure required fields exist
      final processedScans = scans.map((scan) {
        return _ensureScanData(scan);
      }).toList();
      
      setState(() {
        _scans = processedScans;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _errorMessage = 'Failed to load scan history: $e';
        _isLoading = false;
      });
    }
  }

  // ONLY ensure required fields exist - DO NOT recalculate risk level
  Map<String, dynamic> _ensureScanData(Map<String, dynamic> scan) {
    // Get the stored risk level - use it as is
    String riskLevel = scan['risk_level'] ?? 'unknown';
    int riskScore = scan['risk_score'] ?? 0;
    final alerts = List<String>.from(scan['alerts'] ?? []);
    
    // If risk_level is 'unknown' or empty, determine from alerts ONLY as fallback
    if (riskLevel == 'unknown' || riskLevel == '') {
      // Check alerts for actual risk
      for (var alert in alerts) {
        final alertLower = alert.toLowerCase();
        if (alertLower.contains('matches your') || 
            (alertLower.contains('may violate') && alertLower.contains('diabetic'))) {
          riskLevel = 'unsafe';
          riskScore = 35;
          break;
        } else if (alertLower.contains('may violate')) {
          riskLevel = 'caution';
          riskScore = 55;
        }
      }
      if (riskLevel == 'unknown' || riskLevel == '') {
        riskLevel = 'safe';
        if (riskScore == 0) riskScore = 100;
      }
    }
    
    // Return scan with ensured fields (preserving original values)
    return {
      ...scan,
      'risk_level': riskLevel,
      'risk_score': riskScore,
      'confidence': scan['confidence'] ?? 0.75,
    };
  }

  List<Map<String, dynamic>> get _filteredScans {
    if (_filter == 'all') return _scans;
    return _scans.where((scan) => scan['risk_level'] == _filter).toList();
  }

  Color _getRiskColor(String riskLevel) {
    switch (riskLevel) {
      case 'safe':
        return AppTheme.safe;
      case 'caution':
        return AppTheme.caution;
      case 'unsafe':
        return AppTheme.unsafe;
      default:
        return const Color(0xFF9A9790);
    }
  }

  IconData _getRiskIcon(String riskLevel) {
    switch (riskLevel) {
      case 'safe':
        return Icons.check_circle_rounded;
      case 'caution':
        return Icons.warning_rounded;
      case 'unsafe':
        return Icons.dangerous_rounded;
      default:
        return Icons.help_outline_rounded;
    }
  }

  Future<bool> _confirmDeleteScan() async {
    return await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
        ),
        title: const Text(
          'Delete Scan',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
        content: const Text(
          'Are you sure you want to delete this scan? This action cannot be undone.',
          style: TextStyle(fontSize: 13, color: Color(0xFF5A5754)),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(
              foregroundColor: const Color(0xFFA32D2D),
            ),
            child: const Text('Delete'),
          ),
        ],
      ),
    ) ?? false;
  }

  Future<void> _deleteScan(Map<String, dynamic> scan) async {
    final scanId = scan['id']?.toString();
    if (scanId == null || scanId.isEmpty) return;

    final success = await _apiService.deleteScan(widget.userId, scanId);
    if (!mounted) return;

    if (success) {
      setState(() {
        _scans.removeWhere((s) => s['id']?.toString() == scanId);
      });
      _showSnackBar('Scan deleted successfully');
    } else {
      _showSnackBar('Failed to delete scan');
    }
  }

  void _showSnackBar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message, style: const TextStyle(fontSize: 13)),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        margin: const EdgeInsets.all(16),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF7F4F0),
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        surfaceTintColor: Colors.transparent,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text(
          'Scan History',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded, size: 20),
            onPressed: _loadScanHistory,
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _errorMessage != null
              ? _buildErrorView()
              : _scans.isEmpty
                  ? _buildEmptyView()
                  : Column(
                      children: [
                        _buildFilterChips(),
                        _buildStatsSummary(),
                        Expanded(
                          child: ListView.builder(
                            padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                            itemCount: _filteredScans.length,
                            itemBuilder: (context, index) {
                              final scan = _filteredScans[index];
                              final riskLevel = scan['risk_level'] ?? 'unknown';
                              final productName = scan['product_name'] ?? 'Unknown Product';
                              final ingredients = List<String>.from(scan['ingredients'] ?? []);
                              final scannedAt = scan['scanned_at'] != null
                                  ? DateTime.parse(scan['scanned_at'])
                                  : DateTime.now();
                              
                              return Dismissible(
                                key: Key(scan['id']?.toString() ?? 'scan-$index'),
                                direction: DismissDirection.endToStart,
                                background: Container(
                                  margin: const EdgeInsets.only(bottom: 8),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFFA32D2D),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  alignment: Alignment.centerRight,
                                  padding: const EdgeInsets.only(right: 20),
                                  child: const Icon(Icons.delete_rounded, color: Colors.white, size: 24),
                                ),
                                confirmDismiss: (_) => _confirmDeleteScan(),
                                onDismissed: (_) => _deleteScan(scan),
                                child: _ScanHistoryTile(
                                  productName: productName,
                                  riskLevel: riskLevel,
                                  ingredients: ingredients,
                                  scannedAt: scannedAt,
                                  riskIcon: _getRiskIcon(riskLevel),
                                  riskColor: _getRiskColor(riskLevel),
                                  onTap: () {
                                    Navigator.push(
                                      context,
                                      MaterialPageRoute(
                                        builder: (context) => ScanDetailsScreen(
                                          userId: widget.userId,
                                          scanId: scan['id'],
                                          scanData: scan,
                                        ),
                                      ),
                                    );
                                  },
                                ),
                              );
                            },
                          ),
                        ),
                      ],
                    ),
    );
  }

  Widget _buildErrorView() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: const Color(0xFFFDECEA),
                borderRadius: BorderRadius.circular(16),
              ),
              child: const Icon(
                Icons.error_outline_rounded,
                size: 32,
                color: Color(0xFFA32D2D),
              ),
            ),
            const SizedBox(height: 16),
            Text(
              _errorMessage!,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 14, color: Color(0xFF5A5754)),
            ),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: _loadScanHistory,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.primary,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              ),
              child: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmptyView() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                color: const Color(0xFFF2EFE9),
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Icon(
                Icons.history_rounded,
                size: 40,
                color: Color(0xFF9A9790),
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'No scans yet',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w600,
                color: Color(0xFF1A1814),
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'Scan your first food product to get started',
              style: TextStyle(fontSize: 13, color: Color(0xFF9A9790)),
            ),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: () {
                Navigator.pop(context);
              },
              icon: const Icon(Icons.add_photo_alternate_rounded, size: 18),
              label: const Text('Go to Scan'),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.primary,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFilterChips() {
    final filters = [
      {'id': 'all', 'label': 'All', 'color': const Color(0xFF9A9790)},
      {'id': 'safe', 'label': 'Safe', 'color': AppTheme.safe},
      {'id': 'caution', 'label': 'Caution', 'color': AppTheme.caution},
      {'id': 'unsafe', 'label': 'Unsafe', 'color': AppTheme.unsafe},
    ];

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: filters.map((filter) {
            final isSelected = _filter == filter['id'];
            return Padding(
              padding: const EdgeInsets.only(right: 8),
              child: FilterChip(
                label: Text(
                  filter['label'] as String,
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                    color: isSelected ? (filter['color'] as Color) : const Color(0xFF5A5754),
                  ),
                ),
                selected: isSelected,
                onSelected: (selected) {
                  setState(() {
                    _filter = filter['id'] as String;
                  });
                },
                backgroundColor: Colors.white,
                selectedColor: (filter['color'] as Color).withValues(alpha: 0.1),
                checkmarkColor: filter['color'] as Color,
                side: BorderSide(
                  color: isSelected
                      ? (filter['color'] as Color)
                      : const Color(0xFFE5E0D8),
                ),
                shape: StadiumBorder(
                  side: BorderSide(
                    color: isSelected
                        ? (filter['color'] as Color)
                        : const Color(0xFFE5E0D8),
                  ),
                ),
              ),
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _buildStatsSummary() {
    final total = _scans.length;
    final safeCount = _scans.where((s) => s['risk_level'] == 'safe').length;
    final cautionCount = _scans.where((s) => s['risk_level'] == 'caution').length;
    final unsafeCount = _scans.where((s) => s['risk_level'] == 'unsafe').length;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          _StatItem(label: 'Total', value: total.toString(), color: const Color(0xFF9A9790)),
          _StatItem(label: 'Safe', value: safeCount.toString(), color: AppTheme.safe),
          _StatItem(label: 'Caution', value: cautionCount.toString(), color: AppTheme.caution),
          _StatItem(label: 'Unsafe', value: unsafeCount.toString(), color: AppTheme.unsafe),
        ],
      ),
    );
  }
}

// Stat Item Component
class _StatItem extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _StatItem({
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          value,
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: color,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          label,
          style: const TextStyle(
            fontSize: 10,
            color: Color(0xFF9A9790),
            letterSpacing: 0.5,
          ),
        ),
      ],
    );
  }
}

// Scan History Tile Component
class _ScanHistoryTile extends StatelessWidget {
  final String productName;
  final String riskLevel;
  final List<String> ingredients;
  final DateTime scannedAt;
  final IconData riskIcon;
  final Color riskColor;
  final VoidCallback onTap;

  const _ScanHistoryTile({
    required this.productName,
    required this.riskLevel,
    required this.ingredients,
    required this.scannedAt,
    required this.riskIcon,
    required this.riskColor,
    required this.onTap,
  });

  String _formatDate(DateTime date) {
    final now = DateTime.now();
    final difference = now.difference(date);
    
    if (difference.inDays == 0) {
      if (difference.inHours == 0) {
        if (difference.inMinutes == 0) {
          return 'Just now';
        }
        return '${difference.inMinutes}m ago';
      }
      return '${difference.inHours}h ago';
    } else if (difference.inDays == 1) {
      return 'Yesterday';
    } else if (difference.inDays < 7) {
      return '${difference.inDays}d ago';
    } else {
      return '${date.day}/${date.month}/${date.year}';
    }
  }

  String _getRiskLabel(String riskLevel) {
    switch (riskLevel) {
      case 'safe':
        return 'SAFE';
      case 'caution':
        return 'CAUTION';
      case 'unsafe':
        return 'UNSAFE';
      default:
        return 'UNKNOWN';
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
        ),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: riskColor.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  riskIcon,
                  color: riskColor,
                  size: 24,
                ),
              ),
              const SizedBox(width: 12),
              
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      productName,
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: Color(0xFF1A1814),
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      ingredients.take(2).join(', '),
                      style: const TextStyle(
                        fontSize: 11,
                        color: Color(0xFF9A9790),
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        const Icon(
                          Icons.access_time_rounded,
                          size: 10,
                          color: Color(0xFF9A9790),
                        ),
                        const SizedBox(width: 4),
                        Text(
                          _formatDate(scannedAt),
                          style: const TextStyle(
                            fontSize: 10,
                            color: Color(0xFF9A9790),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: riskColor.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: riskColor.withValues(alpha: 0.3)),
                ),
                child: Text(
                  _getRiskLabel(riskLevel),
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    color: riskColor,
                  ),
                ),
              ),
              
              const SizedBox(width: 8),
              const Icon(
                Icons.chevron_right_rounded,
                size: 20,
                color: Color(0xFF9A9790),
              ),
            ],
          ),
        ),
      ),
    );
  }
}