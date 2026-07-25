import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import 'scan_details_screen.dart';

class PantryScreen extends StatefulWidget {
  final String userId;

  const PantryScreen({super.key, required this.userId});

  @override
  State<PantryScreen> createState() => _PantryScreenState();
}

class _PantryScreenState extends State<PantryScreen> {
  final ApiService _apiService = ApiService();
  final TextEditingController _searchController = TextEditingController();

  List<Map<String, dynamic>> _allPantryItems = [];
  List<Map<String, dynamic>> _filteredItems = [];
  bool _isLoading = true;
  String _selectedCategory = 'all'; // 'all', 'safe', 'caution', 'unsafe'

  @override
  void initState() {
    super.initState();
    _loadPantry();
    _searchController.addListener(_filterItems);
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadPantry() async {
    setState(() => _isLoading = true);
    final items = await _apiService.getUserPantry(widget.userId);
    if (mounted) {
      setState(() {
        _allPantryItems = items;
        _isLoading = false;
      });
      _filterItems();
    }
  }

  void _filterItems() {
    final query = _searchController.text.toLowerCase().trim();
    setState(() {
      _filteredItems = _allPantryItems.where((item) {
        final category = (item['safety_category'] ?? 'safe').toString().toLowerCase();
        final name = (item['product_name'] ?? item['title'] ?? '').toString().toLowerCase();
        final brand = (item['brand'] ?? '').toString().toLowerCase();
        final ingredients = (item['ingredients_text'] ?? '').toString().toLowerCase();

        final matchesCategory = (_selectedCategory == 'all') || (category == _selectedCategory);
        final matchesQuery = query.isEmpty ||
            name.contains(query) ||
            brand.contains(query) ||
            ingredients.contains(query);

        return matchesCategory && matchesQuery;
      }).toList();
    });
  }

  Future<void> _deleteItem(String itemId, String productName) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete Food Item?'),
        content: Text('Are you sure you want to remove "$productName" from your Pantry?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            child: const Text('Delete'),
          ),
        ],
      ),
    );

    if (confirm == true) {
      final success = await _apiService.deletePantryItem(widget.userId, itemId);
      if (success && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Removed "$productName" from Pantry')),
        );
        _loadPantry();
      }
    }
  }

  void _viewItemDetail(Map<String, dynamic> item) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => ScanDetailsScreen(
          userId: widget.userId,
          scanId: item['id']?.toString() ?? item['barcode']?.toString() ?? '',
          scanData: item,
        ),
      ),
    );
  }

  Color _getBadgeColor(String category) {
    switch (category.toLowerCase()) {
      case 'safe':
        return Colors.green.shade700;
      case 'caution':
        return Colors.amber.shade800;
      case 'unsafe':
        return Colors.red.shade700;
      default:
        return AppTheme.primary;
    }
  }

  IconData _getBadgeIcon(String category) {
    switch (category.toLowerCase()) {
      case 'safe':
        return Icons.check_circle_rounded;
      case 'caution':
        return Icons.warning_rounded;
      case 'unsafe':
        return Icons.cancel_rounded;
      default:
        return Icons.info_rounded;
    }
  }

  @override
  Widget build(BuildContext context) {
    final safeCount = _allPantryItems.where((i) => (i['safety_category'] ?? '').toString().toLowerCase() == 'safe').length;
    final cautionCount = _allPantryItems.where((i) => (i['safety_category'] ?? '').toString().toLowerCase() == 'caution').length;
    final unsafeCount = _allPantryItems.where((i) => (i['safety_category'] ?? '').toString().toLowerCase() == 'unsafe').length;

    return Scaffold(
      backgroundColor: const Color(0xFFF9F6F0),
      appBar: AppBar(
        title: const Text(
          'My Saved Pantry',
          style: TextStyle(fontWeight: FontWeight.bold, color: AppTheme.text),
        ),
        elevation: 0,
        backgroundColor: Colors.transparent,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded, color: AppTheme.primary),
            onPressed: _loadPantry,
            tooltip: 'Refresh Pantry',
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _loadPantry,
        color: AppTheme.primary,
        child: Column(
          children: [
            // Search Bar
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: TextField(
                controller: _searchController,
                decoration: InputDecoration(
                  hintText: 'Search saved foods or ingredients...',
                  prefixIcon: const Icon(Icons.search_rounded, color: AppTheme.primary),
                  suffixIcon: _searchController.text.isNotEmpty
                      ? IconButton(
                          icon: const Icon(Icons.clear_rounded),
                          onPressed: () {
                            _searchController.clear();
                          },
                        )
                      : null,
                  filled: true,
                  fillColor: Colors.white,
                  contentPadding: const EdgeInsets.symmetric(vertical: 12),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(16),
                    borderSide: BorderSide(color: Colors.grey.shade300),
                  ),
                ),
              ),
            ),

            // Category Tabs
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Row(
                children: [
                  _buildFilterChip('all', 'All (${_allPantryItems.length})', Icons.dashboard_rounded, AppTheme.primary),
                  const SizedBox(width: 8),
                  _buildFilterChip('safe', 'Safe ($safeCount)', Icons.check_circle_rounded, Colors.green.shade700),
                  const SizedBox(width: 8),
                  _buildFilterChip('caution', 'Caution ($cautionCount)', Icons.warning_rounded, Colors.amber.shade800),
                  const SizedBox(width: 8),
                  _buildFilterChip('unsafe', 'Unsafe ($unsafeCount)', Icons.cancel_rounded, Colors.red.shade700),
                ],
              ),
            ),

            const SizedBox(height: 8),

            // Content List
            Expanded(
              child: _isLoading
                  ? const Center(child: CircularProgressIndicator(color: AppTheme.primary))
                  : _filteredItems.isEmpty
                      ? _buildEmptyState()
                      : ListView.builder(
                          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                          itemCount: _filteredItems.length,
                          itemBuilder: (context, index) {
                            final item = _filteredItems[index];
                            final productName = item['product_name'] ?? item['title'] ?? 'Scanned Food';
                            final category = (item['safety_category'] ?? 'safe').toString().toLowerCase();
                            final imageUrl = item['image_url'] ?? '';
                            final brand = item['brand'] ?? '';

                            return Card(
                              margin: const EdgeInsets.only(bottom: 12),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                              elevation: 2,
                              color: Colors.white,
                              child: InkWell(
                                borderRadius: BorderRadius.circular(16),
                                onTap: () => _viewItemDetail(item),
                                child: Padding(
                                  padding: const EdgeInsets.all(12),
                                  child: Row(
                                    children: [
                                      // Image or Category Icon
                                      Container(
                                        width: 56,
                                        height: 56,
                                        decoration: BoxDecoration(
                                          color: _getBadgeColor(category).withValues(alpha: 0.1),
                                          borderRadius: BorderRadius.circular(12),
                                        ),
                                        child: imageUrl.isNotEmpty
                                            ? ClipRRect(
                                                borderRadius: BorderRadius.circular(12),
                                                child: Image.network(
                                                  imageUrl,
                                                  fit: BoxFit.cover,
                                                  errorBuilder: (_, __, ___) => Icon(
                                                    _getBadgeIcon(category),
                                                    color: _getBadgeColor(category),
                                                    size: 28,
                                                  ),
                                                ),
                                              )
                                            : Icon(
                                                _getBadgeIcon(category),
                                                color: _getBadgeColor(category),
                                                size: 28,
                                              ),
                                      ),
                                      const SizedBox(width: 14),

                                      // Food Details
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                              productName,
                                              style: const TextStyle(
                                                fontWeight: FontWeight.bold,
                                                fontSize: 15,
                                                color: AppTheme.text,
                                              ),
                                              maxLines: 1,
                                              overflow: TextOverflow.ellipsis,
                                            ),
                                            if (brand.isNotEmpty) ...[
                                              const SizedBox(height: 2),
                                              Text(
                                                brand,
                                                style: TextStyle(
                                                  fontSize: 12,
                                                  color: Colors.grey.shade600,
                                                ),
                                              ),
                                            ],
                                            const SizedBox(height: 6),
                                            Row(
                                              children: [
                                                Container(
                                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                                  decoration: BoxDecoration(
                                                    color: _getBadgeColor(category).withValues(alpha: 0.15),
                                                    borderRadius: BorderRadius.circular(6),
                                                  ),
                                                  child: Text(
                                                    category.toUpperCase(),
                                                    style: TextStyle(
                                                      fontSize: 10,
                                                      fontWeight: FontWeight.bold,
                                                      color: _getBadgeColor(category),
                                                    ),
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ],
                                        ),
                                      ),

                                      // Actions
                                      IconButton(
                                        icon: const Icon(Icons.delete_outline_rounded, color: Colors.grey),
                                        onPressed: () => _deleteItem(item['id'] ?? '', productName),
                                      ),
                                    ],
                                  ),
                                ),
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

  Widget _buildFilterChip(String categoryKey, String label, IconData icon, Color color) {
    final isSelected = _selectedCategory == categoryKey;
    return ChoiceChip(
      avatar: Icon(icon, size: 16, color: isSelected ? Colors.white : color),
      label: Text(
        label,
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.bold,
          color: isSelected ? Colors.white : AppTheme.text,
        ),
      ),
      selected: isSelected,
      selectedColor: color,
      backgroundColor: Colors.white,
      onSelected: (selected) {
        if (selected) {
          setState(() {
            _selectedCategory = categoryKey;
          });
          _filterItems();
        }
      },
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.inventory_2_outlined, size: 64, color: Colors.grey.shade400),
            const SizedBox(height: 16),
            Text(
              _selectedCategory == 'all'
                  ? 'No Foods in Your Pantry Yet'
                  : 'No ${_selectedCategory.toUpperCase()} Foods Found',
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppTheme.text),
            ),
            const SizedBox(height: 8),
            Text(
              'Scan products or barcodes to automatically save items into your personal pantry!',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 13, color: Colors.grey.shade600),
            ),
          ],
        ),
      ),
    );
  }
}
