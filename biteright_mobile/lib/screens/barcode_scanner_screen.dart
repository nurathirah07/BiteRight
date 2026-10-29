import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import 'scan_details_screen.dart';

/// Result returned when the user chooses to photograph the label instead.
const String kScanLabelInstead = 'scan_label';

class BarcodeScannerScreen extends StatefulWidget {
  final String userId;

  const BarcodeScannerScreen({super.key, required this.userId});

  @override
  State<BarcodeScannerScreen> createState() => _BarcodeScannerScreenState();
}

class _BarcodeScannerScreenState extends State<BarcodeScannerScreen> {
  final ApiService _apiService = ApiService();
  final MobileScannerController _scannerController = MobileScannerController();
  final TextEditingController _manualController = TextEditingController();

  bool _isProcessing = false;

  @override
  void dispose() {
    _scannerController.dispose();
    _manualController.dispose();
    super.dispose();
  }

  Future<void> _processBarcode(String barcode) async {
    if (_isProcessing || barcode.trim().isEmpty) return;

    setState(() {
      _isProcessing = true;
    });

    try {
      await _scannerController.stop();

      final result = await _apiService.lookupBarcode(barcode.trim(), widget.userId);

      if (!mounted) return;

      if (result['found'] == true) {
        final badges = result['newly_unlocked_badges'] as List? ?? const [];
        if (badges.isNotEmpty) {
          final names = badges
              .map((b) => b is Map ? b['name']?.toString() : null)
              .whereType<String>()
              .join(', ');
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('New badge unlocked: $names')),
          );
        }
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (context) => ScanDetailsScreen(
              userId: widget.userId,
              scanId: result['barcode']?.toString() ?? '',
              scanData: result,
            ),
          ),
        );
      } else {
        final scanLabel = await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (dialogContext) => AlertDialog(
            title: const Text('Product not found'),
            content: Text(
              result['message']?.toString() ??
                  'No product details found for barcode $barcode. Try taking a photo of the ingredient label instead.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogContext, false),
                child: const Text('Try again'),
              ),
              ElevatedButton(
                onPressed: () => Navigator.pop(dialogContext, true),
                child: const Text('Scan label instead'),
              ),
            ],
          ),
        );
        if (!mounted) return;
        if (scanLabel == true) {
          Navigator.pop(context, kScanLabelInstead);
          return;
        }
        await _scannerController.start();
        setState(() => _isProcessing = false);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(ApiService.friendlyError(e))),
        );
        _scannerController.start();
        setState(() => _isProcessing = false);
      }
    }
  }

  void _showManualBarcodeDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Enter Barcode Manually'),
        content: TextField(
          controller: _manualController,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            hintText: 'e.g. 737628064502 (UPC/EAN)',
            labelText: 'Barcode Number',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () {
              final code = _manualController.text.trim();
              Navigator.pop(context);
              if (code.isNotEmpty) {
                _processBarcode(code);
              }
            },
            child: const Text('Lookup'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('Scan Product Barcode'),
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.keyboard_rounded),
            onPressed: _showManualBarcodeDialog,
            tooltip: 'Enter Manually',
          ),
        ],
      ),
      body: Stack(
        children: [
          // Camera Barcode Scanner
          MobileScanner(
            controller: _scannerController,
            onDetect: (capture) {
              final List<Barcode> barcodes = capture.barcodes;
              for (final barcode in barcodes) {
                final rawValue = barcode.rawValue;
                if (rawValue != null && rawValue.isNotEmpty) {
                  _processBarcode(rawValue);
                  break;
                }
              }
            },
          ),

          // Reticle Overlay Box
          Center(
            child: Container(
              width: 260,
              height: 180,
              decoration: BoxDecoration(
                border: Border.all(color: AppTheme.primary, width: 3),
                borderRadius: BorderRadius.circular(16),
              ),
              child: const Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.qr_code_scanner_rounded, color: Colors.white70, size: 48),
                  SizedBox(height: 8),
                  Text(
                    'Align Barcode inside frame',
                    style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13),
                  ),
                ],
              ),
            ),
          ),

          // Bottom Manual Code Bar
          Positioned(
            bottom: 30,
            left: 24,
            right: 24,
            child: ElevatedButton.icon(
              onPressed: _showManualBarcodeDialog,
              icon: const Icon(Icons.edit_rounded),
              label: const Text('Enter Barcode Manually'),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.primary,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              ),
            ),
          ),

          if (_isProcessing)
            Container(
              color: Colors.black54,
              child: const Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    CircularProgressIndicator(color: AppTheme.primary),
                    SizedBox(height: 16),
                    Text(
                      'Checking Open Food Facts database...',
                      style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
