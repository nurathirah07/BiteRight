import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';

class ScanScreen extends StatefulWidget {
  final String userId;
  final VoidCallback? onBack;

  const ScanScreen({super.key, required this.userId, this.onBack});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  final ImagePicker _picker = ImagePicker();
  final ApiService _apiService = ApiService();
  final ScrollController _scrollController = ScrollController();
  File? _selectedImage;
  bool _isLoading = false;
  bool _isAnalyzing = false;
  Map<String, dynamic>? _scanResult;
  String? _errorMessage;

  // Editable ingredients as a single string (raw text for editing)
  String _editableIngredientsText = '';
  final TextEditingController _ingredientsController = TextEditingController();

  // Store raw data for reference
  String _rawExtractedText = '';
  List<String> _processedIngredients = [];

  @override
  void dispose() {
    _scrollController.dispose();
    _ingredientsController.dispose();
    super.dispose();
  }

  Future<void> _pickImageFromGallery() async {
    try {
      final XFile? image = await _picker.pickImage(
        source: ImageSource.gallery,
        maxWidth: 1600,
        maxHeight: 1600,
        imageQuality: 85,
      );

      if (image != null) {
        setState(() {
          _selectedImage = File(image.path);
          _scanResult = null;
          _errorMessage = null;
          _editableIngredientsText = '';
          _rawExtractedText = '';
          _processedIngredients = [];
          _ingredientsController.clear();
        });
        await _scanImage();
      }
    } catch (e) {
      setState(() {
        _errorMessage = 'Error accessing image: $e';
      });
    }
  }

  // Validate image before scanning
  Future<bool> _validateImage(File image) async {
    try {
      final bytes = await image.readAsBytes();
      final imageSize = bytes.length;

      if (imageSize < 10000) {
        setState(() {
          _errorMessage =
              'Image too small or invalid. Please take a clearer photo.';
        });
        return false;
      }
      return true;
    } catch (e) {
      setState(() {
        _errorMessage = 'Error validating image: $e';
      });
      return false;
    }
  }

  // Send image to backend for OCR extraction and NLP processing
  Future<void> _scanImage() async {
    if (_selectedImage == null) return;

    if (!await _validateImage(_selectedImage!)) {
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final data = await _apiService.extractIngredients(_selectedImage!);

      if (data != null && data['error'] == null) {
        final rawText = (data['raw_text'] ?? '').toString().trim();
        final ingredients = List<String>.from(data['ingredients'] ?? []);
        if (rawText.isEmpty && ingredients.isEmpty) {
          setState(() {
            _errorMessage =
                data['warning']?.toString() ??
                'No text could be read from this image. Try a clearer photo of the ingredients list.';
            _isLoading = false;
          });
          return;
        }

        setState(() {
          // Store processed ingredients for analysis
          _processedIngredients = ingredients;
          _rawExtractedText = rawText.isNotEmpty
              ? rawText
              : ingredients.join(', ');

          // Use RAW EXTRACTED TEXT for editing (not processed)
          _editableIngredientsText = _rawExtractedText;
          _ingredientsController.text = _editableIngredientsText;
          _isLoading = false;
        });
      } else {
        setState(() {
          _errorMessage = data?['error']?.toString() ?? 'Extraction failed';
          _isLoading = false;
        });
      }
    } catch (e) {
      setState(() {
        _errorMessage = 'Network error: $e';
        _isLoading = false;
      });
    }
  }

  // Send edited ingredients for full analysis and properly save to history
  Future<void> _analyzeIngredients() async {
    if (_editableIngredientsText.trim().isEmpty) {
      setState(() {
        _errorMessage = 'No ingredients to analyze';
      });
      return;
    }

    setState(() {
      _isAnalyzing = true;
      _errorMessage = null;
    });

    try {
      final data = await _apiService.analyzeIngredientsWithProfile(
        widget.userId,
        _editableIngredientsText,
      );

      if (data != null && data['error'] == null) {
        final ingredients = List<String>.from(data['ingredients'] ?? []);
        if (ingredients.isEmpty && _editableIngredientsText.trim().isEmpty) {
          setState(() {
            _errorMessage =
                'No ingredients found to analyze. Edit the extracted text and try again.';
            _isAnalyzing = false;
          });
          return;
        }

        final riskLevel = data['risk_level'] ?? 'unknown';
        if (riskLevel == 'unknown') {
          setState(() {
            _errorMessage =
                'Analysis could not determine a risk level. Please verify the ingredient text.';
            _isAnalyzing = false;
          });
          return;
        }

        final riskScore = data['risk_score'] ?? 0;
        final confidence = data['confidence'] ?? 0.75;
        final alerts = data['alerts'] as List? ?? [];

        // Prepare the scan data with ALL fields properly set
        final Map<String, dynamic> scanDataToSave = {
          'product_name': 'Scanned Product',
          'ingredients': ingredients.isNotEmpty ? ingredients : data['ingredients'] ?? [],
          'ingredient_details': data['ingredient_details'] ?? [],
          'risk_level': riskLevel,
          'risk_score': riskScore,
          'confidence': confidence,
          'alerts': alerts,
          'recommendations': data['recommendations'] ?? [],
          'detection_method': data['detection_method'] ?? 'AI Analysis',
          'allergens_detected': data['allergens_detected'] ?? [],
          'raw_text': _editableIngredientsText,
          'was_edited':
              _editableIngredientsText.trim() != _rawExtractedText.trim(),
        };

        // Save to history
        final scanId = await _apiService.addScanToHistory(
          widget.userId,
          scanDataToSave,
        );

        if (scanId != null) {
          data['id'] = scanId;
          data['scan_id'] = scanId;
        }
        data['was_edited'] = scanDataToSave['was_edited'];

        setState(() {
          _scanResult = data;
          _isAnalyzing = false;
        });
      } else {
        setState(() {
          _errorMessage = data?['error']?.toString() ?? 'Analysis failed';
          _isAnalyzing = false;
        });
      }
    } catch (e) {
      setState(() {
        _errorMessage = 'Network error: $e';
        _isAnalyzing = false;
      });
    }
  }

  // Reset the scan screen
  void _resetScan() {
    setState(() {
      _selectedImage = null;
      _scanResult = null;
      _editableIngredientsText = '';
      _rawExtractedText = '';
      _processedIngredients = [];
      _ingredientsController.clear();
      _errorMessage = null;
      _isLoading = false;
      _isAnalyzing = false;
    });
  }

  // Get color based on risk level
  Color _getRiskColor(String riskLevel) {
    switch (riskLevel) {
      case 'safe':
        return AppTheme.safe;
      case 'caution':
        return AppTheme.caution;
      case 'unsafe':
        return AppTheme.unsafe;
      default:
        return Colors.grey;
    }
  }

  // Get icon based on risk level
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
          onPressed: widget.onBack ??
              () {
                if (Navigator.canPop(context)) {
                  Navigator.pop(context);
                }
              },
        ),
        title: const Text(
          'Upload ingredients',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
        actions: [
          if (_selectedImage != null)
            TextButton(
              onPressed: _resetScan,
              child: const Text('New image', style: TextStyle(fontSize: 12)),
            ),
        ],
      ),
      body: _isLoading
          ? const Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(AppTheme.primary),
                  ),
                  SizedBox(height: 16),
                  Text(
                    'Reading ingredients from image...\nThis may take up to a minute.',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 13, color: Color(0xFF9A9790)),
                  ),
                ],
              ),
            )
          : _isAnalyzing
              ? const Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      CircularProgressIndicator(
                        valueColor:
                            AlwaysStoppedAnimation<Color>(AppTheme.primary),
                      ),
                      SizedBox(height: 16),
                      Text('Analyzing ingredients for allergens...'),
                    ],
                  ),
                )
              : _scanResult != null
                  ? _buildResultView()
                  : _editableIngredientsText.isNotEmpty
                      ? _buildEditIngredientsView()
                      : _selectedImage != null
                          ? _buildPreviewView()
                          : _buildInitialView(),
    );
  }

  // Initial view with instructions
  Widget _buildInitialView() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
            ),
            child: Column(
              children: [
                Container(
                  width: 92,
                  height: 92,
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFF3E2),
                    borderRadius: BorderRadius.circular(24),
                  ),
                  child: const Icon(
                    Icons.upload_file_rounded,
                    size: 46,
                    color: AppTheme.primary,
                  ),
                ),
                const SizedBox(height: 16),
                const Text(
                  'Upload a food label',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF1A1814),
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'We\'ll extract and analyze the ingredients',
                  style: TextStyle(
                    fontSize: 13,
                    color: Color(0xFF9A9790),
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _isLoading ? null : _pickImageFromGallery,
                    icon: const Icon(Icons.upload_rounded, size: 20),
                    label: const Text('Upload image'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.primary,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 20),

          // Tips Section
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Row(
                  children: [
                    Icon(Icons.tips_and_updates_rounded,
                        color: AppTheme.primary, size: 18),
                    SizedBox(width: 8),
                    Text(
                      'Tips for Better Results',
                      style: TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 13,
                        color: Color(0xFF1A1814),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                _buildTipItem('Upload a clear photo of the ingredients list'),
                _buildTipItem('Avoid glare, blur, and heavy shadows'),
                _buildTipItem('Crop so the "INGREDIENTS" section fills the frame'),
                _buildTipItem('You can edit extracted text before analyzing'),
              ],
            ),
          ),

          if (_errorMessage != null) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFFFDECEA),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(
                    color: const Color(0xFFA32D2D).withValues(alpha: 0.2)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.error_outline_rounded,
                      color: Color(0xFFA32D2D), size: 18),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      _errorMessage!,
                      style: const TextStyle(
                          fontSize: 12, color: Color(0xFFA32D2D)),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildTipItem(String tip) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('• ',
              style: TextStyle(fontSize: 12, color: Color(0xFF9A9790))),
          Expanded(
            child: Text(
              tip,
              style: const TextStyle(fontSize: 12, color: Color(0xFF5A5754)),
            ),
          ),
        ],
      ),
    );
  }

  // Preview view after image selection
  Widget _buildPreviewView() {
    return Column(
      children: [
        if (_errorMessage != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFFFDECEA),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(
                  color: const Color(0xFFA32D2D).withValues(alpha: 0.2),
                ),
              ),
              child: Row(
                children: [
                  const Icon(
                    Icons.error_outline_rounded,
                    color: Color(0xFFA32D2D),
                    size: 18,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      _errorMessage!,
                      style: const TextStyle(
                        fontSize: 12,
                        color: Color(0xFFA32D2D),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        Expanded(
          child: Center(
            child: Container(
              margin: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.05),
                    blurRadius: 10,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: Image.file(
                  _selectedImage!,
                  fit: BoxFit.contain,
                ),
              ),
            ),
          ),
        ),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.05),
                blurRadius: 10,
                offset: const Offset(0, -2),
              ),
            ],
          ),
          child: Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: _resetScan,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: const Color(0xFF5A5754),
                    side: const BorderSide(color: Color(0xFFE5E0D8)),
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10),
                    ),
                  ),
                  child: const Text('Cancel'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: ElevatedButton(
                  onPressed: _scanImage,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.primary,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10),
                    ),
                  ),
                  child: const Text('Retry extraction'),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  // Edit ingredients view with single text field (shows raw extracted text)
  Widget _buildEditIngredientsView() {
    return Column(
      children: [
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Info card
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: const Color(0xFFE6F1FB),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                        color: AppTheme.primary.withValues(alpha: 0.25)),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 32,
                        height: 32,
                        decoration: BoxDecoration(
                          color: AppTheme.primary.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Icon(Icons.edit_note_rounded,
                            color: AppTheme.primary, size: 18),
                      ),
                      const SizedBox(width: 12),
                      const Expanded(
                        child: Text(
                          'You can edit the extracted text below. Correct any OCR errors, add missing ingredients, or remove incorrect ones.',
                          style: TextStyle(
                              fontSize: 12,
                              color: AppTheme.primary,
                              height: 1.4),
                        ),
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 20),

                const Text(
                  'Extracted Text',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF1A1814),
                  ),
                ),
                const SizedBox(height: 4),
                const Text(
                  'Edit this text to correct any OCR errors',
                  style: TextStyle(fontSize: 11, color: Color(0xFF9A9790)),
                ),

                const SizedBox(height: 12),

                // Single text field for the raw text
                Container(
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFFE5E0D8)),
                  ),
                  child: TextFormField(
                    controller: _ingredientsController,
                    maxLines: 20,
                    decoration: const InputDecoration(
                      hintText:
                          'Extracted text will appear here. Edit as needed...',
                      hintStyle:
                          TextStyle(fontSize: 12, color: Color(0xFF9A9790)),
                      border: InputBorder.none,
                      contentPadding: EdgeInsets.all(14),
                    ),
                    style: const TextStyle(fontSize: 13),
                    onChanged: (value) {
                      _editableIngredientsText = value;
                    },
                  ),
                ),

                const SizedBox(height: 16),

                // Quick actions
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () {
                          setState(() {
                            _editableIngredientsText = '';
                            _ingredientsController.clear();
                          });
                        },
                        icon: const Icon(Icons.clear_rounded, size: 16),
                        label: const Text('Clear'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: const Color(0xFFA32D2D),
                          side: const BorderSide(color: Color(0xFFA32D2D)),
                          padding: const EdgeInsets.symmetric(vertical: 10),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () {
                          if (_rawExtractedText.isNotEmpty) {
                            setState(() {
                              _editableIngredientsText = _rawExtractedText;
                              _ingredientsController.text = _rawExtractedText;
                            });
                          }
                        },
                        icon: const Icon(Icons.restore_rounded, size: 16),
                        label: const Text('Reset'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: AppTheme.primary,
                          side: const BorderSide(color: AppTheme.primary),
                          padding: const EdgeInsets.symmetric(vertical: 10),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),

                // Processed ingredients preview (for reference)
                if (_processedIngredients.isNotEmpty)
                  Container(
                    margin: const EdgeInsets.only(top: 20),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: const Color(0xFFE5E0D8)),
                    ),
                    child: ExpansionTile(
                      title: const Text(
                        'Processed Ingredients Preview',
                        style: TextStyle(
                            fontSize: 13, fontWeight: FontWeight.w500),
                      ),
                      leading: Container(
                        width: 28,
                        height: 28,
                        decoration: BoxDecoration(
                          color: AppTheme.primary.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Icon(Icons.list_alt_rounded,
                            size: 14, color: AppTheme.primary),
                      ),
                      children: [
                        Padding(
                          padding: const EdgeInsets.all(14),
                          child: Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: _processedIngredients
                                .map(
                                  (ing) => Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 10, vertical: 5),
                                    decoration: BoxDecoration(
                                      color: const Color(0xFFF2EFE9),
                                      borderRadius: BorderRadius.circular(16),
                                    ),
                                    child: Text(
                                      ing,
                                      style: const TextStyle(
                                          fontSize: 11,
                                          color: Color(0xFF5A5754)),
                                    ),
                                  ),
                                )
                                .toList(),
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ),

        // Bottom buttons
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white,
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.05),
                blurRadius: 10,
                offset: const Offset(0, -2),
              ),
            ],
          ),
          child: Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: _resetScan,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: const Color(0xFF5A5754),
                    side: const BorderSide(color: Color(0xFFE5E0D8)),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10),
                    ),
                  ),
                  child: const Text('Cancel'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: ElevatedButton(
                  onPressed: _editableIngredientsText.trim().isEmpty
                      ? null
                      : _analyzeIngredients,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.primary,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10),
                    ),
                  ),
                  child: const Text('Analyze'),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  // Result view after scanning - structured format
  Widget _buildResultView() {
    final riskLevel = _scanResult?['risk_level'] ?? 'unknown';
    final alerts = _scanResult?['alerts'] as List? ?? [];
    final detectionMethod = _scanResult?['detection_method'] ?? 'AI Analysis';
    final confidence = _scanResult?['confidence'] ?? 0.0;
    final ingredientDetails = List<Map<String, dynamic>>.from(
      _scanResult?['ingredient_details'] ?? [],
    );
    final recommendations = List<String>.from(
      _scanResult?['recommendations'] ?? [],
    );

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Risk Level Card
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  _getRiskColor(riskLevel),
                  _getRiskColor(riskLevel).withValues(alpha: 0.8),
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Column(
              children: [
                Icon(
                  _getRiskIcon(riskLevel),
                  size: 48,
                  color: Colors.white,
                ),
                const SizedBox(height: 12),
                Text(
                  riskLevel.toUpperCase(),
                  style: const TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        detectionMethod,
                        style: const TextStyle(
                            fontSize: 10, color: Colors.white70),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        'Confidence: ${(confidence * 100).toInt()}%',
                        style: const TextStyle(
                            fontSize: 10, color: Colors.white70),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),

          const SizedBox(height: 20),

          // Recommendations Section
          if (recommendations.isNotEmpty) ...[
            const _SectionLabel(label: 'Recommendations'),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: const Color(0xFFF2EFE9),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: recommendations
                    .map(
                      (item) => Padding(
                        padding: const EdgeInsets.only(bottom: 6),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Container(
                              margin: const EdgeInsets.only(top: 4),
                              width: 4,
                              height: 4,
                              decoration: const BoxDecoration(
                                color: AppTheme.primary,
                                shape: BoxShape.circle,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                item,
                                style: const TextStyle(
                                  fontSize: 12,
                                  color: Color(0xFF5A5754),
                                  height: 1.4,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    )
                    .toList(),
              ),
            ),
            const SizedBox(height: 20),
          ],

          // Alerts Section
          if (alerts.isNotEmpty) ...[
            const _SectionLabel(label: 'Alerts'),
            Container(
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
              ),
              child: Column(
                children: alerts
                    .map(
                      (alert) => Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 12),
                        decoration: BoxDecoration(
                          border: Border(
                            bottom: BorderSide(
                                color: Colors.black.withValues(alpha: 0.05)),
                          ),
                        ),
                        child: Row(
                          children: [
                            Container(
                              width: 32,
                              height: 32,
                              decoration: BoxDecoration(
                                color: const Color(0xFFFDECEA),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: const Icon(
                                Icons.warning_amber_rounded,
                                size: 16,
                                color: Color(0xFFA32D2D),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Text(
                                alert.toString(),
                                style: const TextStyle(
                                    fontSize: 13, color: Color(0xFF5A5754)),
                              ),
                            ),
                          ],
                        ),
                      ),
                    )
                    .toList(),
              ),
            ),
            const SizedBox(height: 20),
          ],

          // Ingredients Analysis Section - Structured
          const _SectionLabel(label: 'Ingredients Analysis'),
          Container(
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
            ),
            child: ingredientDetails.isEmpty
                ? const Padding(
                    padding: EdgeInsets.all(32),
                    child: Center(
                      child: Text(
                        'No ingredients analyzed',
                        style:
                            TextStyle(fontSize: 13, color: Color(0xFF9A9790)),
                      ),
                    ),
                  )
                : Column(
                    children: ingredientDetails.asMap().entries.map((entry) {
                      final index = entry.key;
                      final detail = entry.value;
                      final ingredient =
                          detail['ingredient']?.toString() ?? 'Unknown';
                      final status = detail['status']?.toString() ?? 'safe';
                      final reasons =
                          List<String>.from(detail['reasons'] ?? []);
                      final matches = List<Map<String, dynamic>>.from(
                          detail['matches'] ?? []);
                      final confidence = detail['confidence'] ?? 0.0;
                      final isLast = index == ingredientDetails.length - 1;

                      return Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 12),
                        decoration: BoxDecoration(
                          border: isLast
                              ? null
                              : const Border(
                                  bottom: BorderSide(color: Color(0x0A000000))),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Container(
                                  width: 4,
                                  height: 4,
                                  decoration: BoxDecoration(
                                    color: status == 'safe'
                                        ? AppTheme.safe
                                        : status == 'caution'
                                            ? AppTheme.caution
                                            : AppTheme.unsafe,
                                    shape: BoxShape.circle,
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Text(
                                    ingredient,
                                    style: const TextStyle(
                                      fontSize: 14,
                                      fontWeight: FontWeight.w600,
                                      color: Color(0xFF1A1814),
                                    ),
                                  ),
                                ),
                                _RiskBadge(status: status),
                              ],
                            ),
                            if (reasons.isNotEmpty) ...[
                              const SizedBox(height: 8),
                              ...reasons.map((reason) => Padding(
                                    padding: const EdgeInsets.only(
                                        left: 14, bottom: 4),
                                    child: Row(
                                      children: [
                                        const Icon(Icons.info_outline_rounded,
                                            size: 12, color: Color(0xFF9A9790)),
                                        const SizedBox(width: 6),
                                        Expanded(
                                          child: Text(
                                            reason,
                                            style: const TextStyle(
                                              fontSize: 11,
                                              color: Color(0xFF9A9790),
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  )),
                            ],
                            if (matches.isNotEmpty) ...[
                              const SizedBox(height: 8),
                              Padding(
                                padding: const EdgeInsets.only(left: 14),
                                child: Wrap(
                                  spacing: 6,
                                  runSpacing: 6,
                                  children: matches.map((match) {
                                    final type =
                                        match['type']?.toString() ?? 'match';
                                    final keyword =
                                        match['keyword']?.toString() ?? '';
                                    final matchType =
                                        match['match_type']?.toString() ??
                                            'exact';
                                    return Container(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 8, vertical: 4),
                                      decoration: BoxDecoration(
                                        color: const Color(0xFFF2EFE9),
                                        borderRadius: BorderRadius.circular(8),
                                      ),
                                      child: Text(
                                        '$type: $keyword ($matchType)',
                                        style: const TextStyle(
                                          fontSize: 10,
                                          color: Color(0xFF5A5754),
                                          fontWeight: FontWeight.w500,
                                        ),
                                      ),
                                    );
                                  }).toList(),
                                ),
                              ),
                            ],
                            if (confidence > 0) ...[
                              const SizedBox(height: 6),
                              Padding(
                                padding: const EdgeInsets.only(left: 14),
                                child: Row(
                                  children: [
                                    const Text(
                                      'Confidence: ',
                                      style: TextStyle(
                                          fontSize: 10,
                                          color: Color(0xFF9A9790)),
                                    ),
                                    Container(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 6, vertical: 2),
                                      decoration: BoxDecoration(
                                        color: const Color(0xFFF2EFE9),
                                        borderRadius: BorderRadius.circular(8),
                                      ),
                                      child: Text(
                                        '${(confidence * 100).toInt()}%',
                                        style: const TextStyle(
                                            fontSize: 10,
                                            fontWeight: FontWeight.w500),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ],
                        ),
                      );
                    }).toList(),
                  ),
          ),

          const SizedBox(height: 24),

          // New Scan Button
          Center(
            child: ElevatedButton.icon(
              onPressed: _resetScan,
              icon: const Icon(Icons.add_photo_alternate_rounded, size: 18),
              label: const Text('Scan Another Product'),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: AppTheme.primary,
                padding:
                    const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
                side:
                    BorderSide(color: AppTheme.primary.withValues(alpha: 0.3)),
                elevation: 0,
              ),
            ),
          ),

          const SizedBox(height: 16),
        ],
      ),
    );
  }
}

// Section Label Component
class _SectionLabel extends StatelessWidget {
  final String label;

  const _SectionLabel({required this.label});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        label.toUpperCase(),
        style: const TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w500,
          letterSpacing: 0.6,
          color: Color(0xFF9A9790),
        ),
      ),
    );
  }
}

// Risk Badge Component
class _RiskBadge extends StatelessWidget {
  final String status;

  const _RiskBadge({required this.status});

  @override
  Widget build(BuildContext context) {
    Color color;
    String label;

    switch (status) {
      case 'safe':
        color = AppTheme.safe;
        label = 'SAFE';
        break;
      case 'caution':
        color = AppTheme.caution;
        label = 'CAUTION';
        break;
      case 'unsafe':
        color = AppTheme.unsafe;
        label = 'UNSAFE';
        break;
      default:
        color = Colors.grey;
        label = 'UNKNOWN';
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Text(
        label,
        style:
            TextStyle(fontSize: 9, fontWeight: FontWeight.w600, color: color),
      ),
    );
  }
}
