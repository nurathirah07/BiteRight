import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';

class ProfileSetupScreen extends StatefulWidget {
  final String userId;
  final bool isSignUp;

  const ProfileSetupScreen({
    super.key,
    required this.userId,
    this.isSignUp = false,
  });

  @override
  State<ProfileSetupScreen> createState() => _ProfileSetupScreenState();
}

class _ProfileSetupScreenState extends State<ProfileSetupScreen> {
  final ApiService _apiService = ApiService();

  List<Map<String, dynamic>> _allergenCategories = [];
  List<Map<String, dynamic>> _dietaryCategories = [];

  // Store allergies with severity
  Map<String, String> _selectedAllergiesWithSeverity = {}; // id -> severity
  Set<String> _selectedDiets = {};

  bool _isLoading = true;
  bool _isSaving = false;
  bool _hasError = false;
  String _errorMessage = '';

  // Severity options - made static const to fix the const constructor issue

  void _log(String message) {
    if (kDebugMode) {
      print('ProfileScreen: $message');
    }
  }

  @override
  void initState() {
    super.initState();
    _log('Initializing ProfileSetupScreen for user: ${widget.userId}');
    _testConnectionAndLoad();
  }

  Future<void> _testConnectionAndLoad() async {
    _log('Testing connection to backend...');
    final isConnected = await _apiService.testConnection();

    if (isConnected) {
      _log('Connection successful, loading data...');
      await Future.wait([
        _loadOptions(),
        _loadUserProfile(),
      ]);
    } else {
      _log('Connection failed - using fallback data');
      setState(() {
        _hasError = true;
        _errorMessage = 'Cannot connect to server. Using offline data.';
        _loadFallbackData();
      });
    }
  }

  void _loadFallbackData() {
    _log('Loading fallback data');
    setState(() {
      _allergenCategories = [
        {
          'category': 'Nuts',
          'items': [
            {
              'id': 'peanuts',
              'label': 'Peanuts',
              'severity': 'high',
              'severity_options': ['high', 'medium', 'low'],
              'warning': 'Common allergen, severe reactions possible'
            },
            {
              'id': 'tree_nuts',
              'label': 'Tree Nuts',
              'severity': 'high',
              'severity_options': ['high', 'medium', 'low'],
              'warning': 'Almonds, walnuts, cashews, etc.'
            }
          ]
        },
        {
          'category': 'Dairy & Eggs',
          'items': [
            {
              'id': 'milk',
              'label': 'Milk/Dairy',
              'severity': 'medium',
              'severity_options': ['high', 'medium', 'low'],
              'warning': 'Milk, cheese, yogurt, butter'
            },
            {
              'id': 'eggs',
              'label': 'Eggs',
              'severity': 'medium',
              'severity_options': ['high', 'medium', 'low'],
              'warning': 'Egg whites, egg yolks'
            }
          ]
        },
        {
          'category': 'Seafood',
          'items': [
            {
              'id': 'fish',
              'label': 'Fish',
              'severity': 'high',
              'severity_options': ['high', 'medium', 'low'],
              'warning': 'All types of fish'
            },
            {
              'id': 'shellfish',
              'label': 'Shellfish',
              'severity': 'high',
              'severity_options': ['high', 'medium', 'low'],
              'warning': 'Shrimp, crab, lobster, clams'
            }
          ]
        },
        {
          'category': 'Other Allergens',
          'items': [
            {
              'id': 'soy',
              'label': 'Soy',
              'severity': 'medium',
              'severity_options': ['high', 'medium', 'low'],
              'warning': 'Soybeans, tofu, soy sauce'
            },
            {
              'id': 'wheat',
              'label': 'Wheat',
              'severity': 'medium',
              'severity_options': ['high', 'medium', 'low'],
              'warning': 'Wheat, flour, bread'
            },
            {
              'id': 'gluten',
              'label': 'Gluten',
              'severity': 'medium',
              'severity_options': ['high', 'medium', 'low'],
              'warning': 'Wheat, barley, rye'
            },
            {
              'id': 'sesame',
              'label': 'Sesame',
              'severity': 'medium',
              'severity_options': ['high', 'medium', 'low'],
              'warning': 'Sesame seeds, tahini'
            }
          ]
        }
      ];

      _dietaryCategories = [
        {
          'category': 'Lifestyle',
          'items': [
            {
              'id': 'vegetarian',
              'label': 'Vegetarian',
              'warning': 'No meat, fish, or poultry'
            },
            {
              'id': 'vegan',
              'label': 'Vegan',
              'warning': 'No animal products including dairy, eggs, honey'
            },
            {
              'id': 'keto',
              'label': 'Keto',
              'warning': 'Low carb, high fat diet'
            },
          ]
        },
        {
          'category': 'Religious & Health',
          'items': [
            {
              'id': 'halal',
              'label': 'Halal',
              'warning': 'No pork, alcohol, proper preparation'
            },
            {
              'id': 'diabetic',
              'label': 'Diabetic',
              'warning': 'Low sugar, controlled carbs'
            },
            {
              'id': 'low_sodium',
              'label': 'Low Sodium',
              'warning': 'Reduced salt intake'
            },
          ]
        }
      ];

      _isLoading = false;
    });
  }

  Future<void> _loadOptions() async {
    try {
      _log('Loading dietary options...');
      final data = await _apiService.getDietaryOptions();

      if (data != null && mounted) {
        _log('Data received: ${data.keys}');
        setState(() {
          _allergenCategories =
              _convertMapToList(data['options']?['allergens'] ?? {});
          _dietaryCategories =
              _convertMapToList(data['options']?['dietary'] ?? {});
          _isLoading = false;
          _hasError = false;

          _log('Loaded ${_allergenCategories.length} allergen categories');
          _log('Loaded ${_dietaryCategories.length} dietary categories');
        });
      } else if (mounted) {
        _log('No data received, using fallback');
        setState(() {
          _loadFallbackData();
        });
      }
    } catch (e) {
      _log('Error loading options: $e');
      if (mounted) {
        setState(() {
          _loadFallbackData();
        });
      }
    }
  }

  List<Map<String, dynamic>> _convertMapToList(Map<String, dynamic> map) {
    List<Map<String, dynamic>> result = [];
    map.forEach((key, value) {
      result.add({
        'category': key,
        'items': value,
      });
    });
    return result;
  }

  Future<void> _loadUserProfile() async {
    try {
      _log('Loading user profile...');
      final profile = await _apiService.getUserProfile(widget.userId);

      if (profile != null && mounted) {
        setState(() {
          final profileData = profile['profile'] ?? profile;

          // Load allergies with severity
          final allergies = profileData['allergies'] ?? [];
          _selectedAllergiesWithSeverity = {};
          for (var allergy in allergies) {
            if (allergy is Map) {
              _selectedAllergiesWithSeverity[allergy['id']] =
                  allergy['severity'] ?? 'medium';
            } else {
              _selectedAllergiesWithSeverity[allergy.toString()] = 'medium';
            }
          }

          _selectedDiets =
              Set<String>.from(profileData['dietary_restrictions'] ?? []);
          _log(
              'Loaded ${_selectedAllergiesWithSeverity.length} allergies with severity');
        });
      }
    } catch (e) {
      _log('Error loading profile: $e');
    }
  }

  Future<void> _saveProfile() async {
    _log('Saving profile...');
    setState(() => _isSaving = true);

    // Convert allergies to list of maps with severity
    final allergiesList = _selectedAllergiesWithSeverity.entries
        .map((entry) => {'id': entry.key, 'severity': entry.value})
        .toList();

    try {
      final success = await _apiService.updateUserProfileWithSeverity(
        widget.userId,
        allergiesList,
        _selectedDiets.toList(),
      );

      if (success && mounted) {
        _log('Profile saved successfully');

        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Dietary profile updated successfully!'),
            backgroundColor: Colors.green,
            duration: Duration(seconds: 2),
          ),
        );

        if (!widget.isSignUp && Navigator.canPop(context)) {
          Navigator.pop(context, true);
        } else {
          final profile = await _apiService.getUserProfile(widget.userId);
          final username = profile?['profile']?['username'] ?? 'User';

          if (mounted) {
            Navigator.pushReplacementNamed(
              context,
              '/home',
              arguments: {
                'userId': widget.userId,
                'username': username,
              },
            );
          }
        }
      } else if (mounted) {
        _showErrorDialog('Failed to save profile');
      }
    } catch (e) {
      _log('Error saving profile: $e');
      if (mounted) {
        _showErrorDialog('Network error: $e');
      }
    } finally {
      if (mounted) {
        setState(() => _isSaving = false);
      }
    }
  }

  Future<void> _goHome() async {
    if (!widget.isSignUp && Navigator.canPop(context)) {
      Navigator.pop(context);
      return;
    }

    if (widget.userId.isEmpty) {
      Navigator.pop(context);
      return;
    }

    final profile = await _apiService.getUserProfile(widget.userId);
    final username = profile?['profile']?['username'] ?? 'User';

    if (!mounted) return;
    Navigator.pushNamedAndRemoveUntil(
      context,
      '/home',
      (route) => false,
      arguments: {
        'userId': widget.userId,
        'username': username,
      },
    );
  }

  void _clearSelections() {
    setState(() {
      _selectedAllergiesWithSeverity.clear();
      _selectedDiets.clear();
    });
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
          content:
              Text('Selections cleared. Add any restrictions that apply.')),
    );
  }

  void _showErrorDialog(String message) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
        ),
        title: const Text(
          'Error',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
        content: Text(
          message,
          style: const TextStyle(fontSize: 13, color: Color(0xFF5A5754)),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final canPop = !widget.isSignUp && Navigator.canPop(context);
    return PopScope(
      canPop: canPop,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) {
          _goHome();
        }
      },
      child: Scaffold(
        backgroundColor: const Color(0xFFF7F4F0),
        appBar: AppBar(
          backgroundColor: Colors.white,
          elevation: 0,
          surfaceTintColor: Colors.transparent,
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
            onPressed: _goHome,
          ),
          title: const Text(
            'Food Safety Profile',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
          ),
          actions: [
            TextButton(
              onPressed: (_selectedAllergiesWithSeverity.isEmpty &&
                      _selectedDiets.isEmpty)
                  ? null
                  : _clearSelections,
              child: const Text('Clear'),
            ),
          ],
        ),
        body: _isLoading
            ? const Center(child: CircularProgressIndicator())
            : _hasError
                ? Center(
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
                              Icons.wifi_off_rounded,
                              size: 32,
                              color: Color(0xFFA32D2D),
                            ),
                          ),
                          const SizedBox(height: 16),
                          Text(
                            _errorMessage,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              fontSize: 14,
                              color: Color(0xFF5A5754),
                            ),
                          ),
                          const SizedBox(height: 20),
                          ElevatedButton(
                            onPressed: () {
                              setState(() {
                                _isLoading = true;
                                _hasError = false;
                                _testConnectionAndLoad();
                              });
                            },
                            style: ElevatedButton.styleFrom(
                              backgroundColor: AppTheme.primary,
                              foregroundColor: Colors.white,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(10),
                              ),
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 24, vertical: 12),
                            ),
                            child: const Text('Retry'),
                          ),
                        ],
                      ),
                    ),
                  )
                : SingleChildScrollView(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            gradient: const LinearGradient(
                              colors: [Color(0xFFFFF3E2), Color(0xFFE9F7D8)],
                              begin: Alignment.topLeft,
                              end: Alignment.bottomRight,
                            ),
                            borderRadius: BorderRadius.circular(16),
                            border: Border.all(color: Colors.white),
                          ),
                          child: Row(
                            children: [
                              Container(
                                width: 36,
                                height: 36,
                                decoration: BoxDecoration(
                                  color: const Color(0xFFFCE8C5),
                                  borderRadius: BorderRadius.circular(10),
                                ),
                                child: const Icon(
                                  Icons.info_outline_rounded,
                                  size: 18,
                                  color: Color(0xFF854F0B),
                                ),
                              ),
                              const SizedBox(width: 12),
                              const Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      'Select all that apply',
                                      style: TextStyle(
                                        fontSize: 14,
                                        fontWeight: FontWeight.w700,
                                        color: Color(0xFF1A1814),
                                      ),
                                    ),
                                    Text(
                                      'Allergies can be set with severity levels',
                                      style: TextStyle(
                                        fontSize: 11,
                                        color: Color(0xFF9A9790),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),



                        const SizedBox(height: 20),

                        // Allergens Section
                        _SettingsCard(
                          sections: [
                            _SettingsSection(
                              title: 'Allergens',
                              items: _buildAllergenItems(),
                            ),
                          ],
                        ),

                        const SizedBox(height: 20),

                        // Dietary Preferences Section
                        _SettingsCard(
                          sections: [
                            _SettingsSection(
                              title: 'Dietary Preferences',
                              items: _buildDietaryItems(),
                            ),
                          ],
                        ),

                        const SizedBox(height: 32),

                        // Save button
                        SizedBox(
                          width: double.infinity,
                          height: 48,
                          child: ElevatedButton(
                            onPressed: _isSaving ? null : _saveProfile,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: AppTheme.primary,
                              foregroundColor: Colors.white,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(10),
                              ),
                              elevation: 0,
                            ),
                            child: _isSaving
                                ? const SizedBox(
                                    width: 20,
                                    height: 20,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      color: Colors.white,
                                    ),
                                  )
                                : const Text(
                                    'Save Profile',
                                    style: TextStyle(
                                        fontSize: 14,
                                        fontWeight: FontWeight.w600),
                                  ),
                          ),
                        ),

                        const SizedBox(height: 16),
                      ],
                    ),
                  ),
      ),
    );
  }



  List<Widget> _buildAllergenItems() {
    List<Widget> items = [];

    for (var category in _allergenCategories) {
      final categoryItems =
          List<Map<String, dynamic>>.from(category['items'] ?? []);

      items.add(
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 6, 14, 4),
          child: Text(
            category['category'].toString().toUpperCase(),
            style: const TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w500,
              letterSpacing: 0.6,
              color: Color(0xFF9A9790),
            ),
          ),
        ),
      );

      for (int i = 0; i < categoryItems.length; i++) {
        final item = categoryItems[i];
        final isLast = i == categoryItems.length - 1 &&
            category == _allergenCategories.last;

        items.add(
          _AllergenTile(
            item: item,
            isSelected: _selectedAllergiesWithSeverity.containsKey(item['id']),
            selectedSeverity:
                _selectedAllergiesWithSeverity[item['id']] ?? 'medium',
            isLast: isLast,
            onToggle: (id) {
              setState(() {
                if (_selectedAllergiesWithSeverity.containsKey(id)) {
                  _selectedAllergiesWithSeverity.remove(id);
                } else {
                  _selectedAllergiesWithSeverity[id] = 'medium';
                }
              });
            },
            onSeverityChange: (id, severity) {
              setState(() {
                _selectedAllergiesWithSeverity[id] = severity;
              });
            },
          ),
        );
      }
    }

    return items;
  }

  List<Widget> _buildDietaryItems() {
    List<Widget> items = [];

    for (var category in _dietaryCategories) {
      final categoryItems =
          List<Map<String, dynamic>>.from(category['items'] ?? []);

      items.add(
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 6, 14, 4),
          child: Text(
            category['category'].toString().toUpperCase(),
            style: const TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w500,
              letterSpacing: 0.6,
              color: Color(0xFF9A9790),
            ),
          ),
        ),
      );

      for (int i = 0; i < categoryItems.length; i++) {
        final item = categoryItems[i];
        final isLast = i == categoryItems.length - 1 &&
            category == _dietaryCategories.last;

        items.add(
          _DietaryTile(
            item: item,
            isSelected: _selectedDiets.contains(item['id']),
            isLast: isLast,
            onToggle: (id) {
              setState(() {
                if (_selectedDiets.contains(id)) {
                  _selectedDiets.remove(id);
                } else {
                  _selectedDiets.add(id);
                }
              });
            },
          ),
        );
      }
    }

    return items;
  }
}

// ─── Settings Card ─────────────────────────────────────────────────────────────

class _SettingsCard extends StatelessWidget {
  final List<_SettingsSection> sections;

  const _SettingsCard({required this.sections});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
      ),
      child: Column(
        children: List.generate(sections.length, (i) {
          final section = sections[i];
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 14, 14, 4),
                child: Text(
                  section.title.toUpperCase(),
                  style: const TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w500,
                    letterSpacing: 0.6,
                    color: Color(0xFF9A9790),
                  ),
                ),
              ),
              ...section.items,
            ],
          );
        }),
      ),
    );
  }
}

class _SettingsSection {
  final String title;
  final List<Widget> items;
  const _SettingsSection({required this.title, required this.items});
}

// ─── Allergen Tile (with severity dropdown) ───────────────────────────────────

class _AllergenTile extends StatelessWidget {
  final Map<String, dynamic> item;
  final bool isSelected;
  final String selectedSeverity;
  final bool isLast;
  final Function(String) onToggle;
  final Function(String, String) onSeverityChange;

  static const List<String> _severityOptions = ['high', 'medium', 'low'];

  const _AllergenTile({
    required this.item,
    required this.isSelected,
    required this.selectedSeverity,
    required this.isLast,
    required this.onToggle,
    required this.onSeverityChange,
  });

  Color _getSeverityColor(String severity) {
    switch (severity) {
      case 'high':
        return const Color(0xFFA32D2D);
      case 'medium':
        return const Color(0xFFE67E22);
      case 'low':
        return const Color(0xFF2A6E54);
      default:
        return const Color(0xFF9A9790);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        border: isLast
            ? null
            : const Border(bottom: BorderSide(color: Color(0x0A000000))),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
      child: Row(
        children: [
          Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => onToggle(item['id']),
              child: Row(
                children: [
                  SizedBox(
                    width: 40,
                    height: 40,
                    child: Checkbox(
                      value: isSelected,
                      onChanged: (_) => onToggle(item['id']),
                      activeColor: AppTheme.primary,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(6),
                      ),
                    ),
                  ),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          item['label'] ?? 'Unknown',
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w500,
                            color: Color(0xFF1A1814),
                          ),
                        ),
                        if (item['warning'] != null)
                          Text(
                            item['warning'],
                            style: const TextStyle(
                              fontSize: 11,
                              color: Color(0xFF9A9790),
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (isSelected)
            Container(
              margin: const EdgeInsets.only(right: 8),
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color:
                    _getSeverityColor(selectedSeverity).withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: _getSeverityColor(selectedSeverity)
                      .withValues(alpha: 0.3),
                ),
              ),
              child: DropdownButton<String>(
                value: selectedSeverity,
                underline: const SizedBox(),
                icon: Icon(
                  Icons.arrow_drop_down,
                  color: _getSeverityColor(selectedSeverity),
                  size: 18,
                ),
                items: _severityOptions.map((severity) {
                  return DropdownMenuItem(
                    value: severity,
                    child: Row(
                      children: [
                        Container(
                          width: 10,
                          height: 10,
                          decoration: BoxDecoration(
                            color: _getSeverityColor(severity),
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          severity.toUpperCase(),
                          style: TextStyle(
                            color: _getSeverityColor(severity),
                            fontWeight: FontWeight.w600,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ),
                  );
                }).toList(),
                onChanged: (value) {
                  if (value != null) {
                    onSeverityChange(item['id'], value);
                  }
                },
              ),
            ),
        ],
      ),
    );
  }
}

// ─── Dietary Tile (simple checkbox) ──────────────────────────────────────────

class _DietaryTile extends StatelessWidget {
  final Map<String, dynamic> item;
  final bool isSelected;
  final bool isLast;
  final Function(String) onToggle;

  const _DietaryTile({
    required this.item,
    required this.isSelected,
    required this.isLast,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => onToggle(item['id']),
      child: Container(
        decoration: BoxDecoration(
          border: isLast
              ? null
              : const Border(bottom: BorderSide(color: Color(0x0A000000))),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
        child: Row(
          children: [
            SizedBox(
              width: 40,
              height: 40,
              child: Checkbox(
                value: isSelected,
                onChanged: (_) => onToggle(item['id']),
                activeColor: AppTheme.primary,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(6),
                ),
              ),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item['label'] ?? 'Unknown',
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      color: Color(0xFF1A1814),
                    ),
                  ),
                  if (item['warning'] != null)
                    Text(
                      item['warning'],
                      style: const TextStyle(
                        fontSize: 11,
                        color: Color(0xFF9A9790),
                      ),
                    ),
                ],
              ),
            ),
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: const Color(0xFFF2EFE9),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(
                Icons.restaurant_menu_outlined,
                size: 16,
                color: isSelected ? AppTheme.primary : const Color(0xFF9A9790),
              ),
            ),
          ],
        ),
      ),
    );
  }
}