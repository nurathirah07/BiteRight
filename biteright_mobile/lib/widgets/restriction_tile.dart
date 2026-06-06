// lib/widgets/restriction_tile.dart
import 'package:flutter/material.dart';
import '../models/dietary_option.dart';

class RestrictionTile extends StatelessWidget {
  final DietaryOption option;
  final bool isSelected;
  final VoidCallback onToggle;
  
  const RestrictionTile({
    super.key,
    required this.option,
    required this.isSelected,
    required this.onToggle,
  });
  
  Color _getSeverityColor() {
    if (option.severity == 'high') return Colors.red;
    if (option.severity == 'medium') return Colors.orange;
    return Colors.grey;
  }
  
  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: onToggle,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              // Checkbox
              Container(
                width: 24,
                height: 24,
                decoration: BoxDecoration(
                  color: isSelected ? Colors.orange : Colors.transparent,
                  border: Border.all(
                    color: isSelected ? Colors.orange : Colors.grey,
                    width: 2,
                  ),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: isSelected
                    ? const Icon(Icons.check, color: Colors.white, size: 18)
                    : null,
              ),
              
              const SizedBox(width: 12),
              
              // Icon based on severity
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  // ignore: deprecated_member_use
                  color: _getSeverityColor().withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(
                  option.severity == 'high' 
                      ? Icons.warning 
                      : Icons.info_outline,
                  color: _getSeverityColor(),
                  size: 20,
                ),
              ),
              
              const SizedBox(width: 12),
              
              // Title and warning
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      option.label,
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                      ),
                    ),
                    if (option.warning != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        option.warning!,
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.grey[600],
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              
              // Selected indicator
              if (isSelected)
                const Icon(
                  Icons.check_circle,
                  color: Colors.orange,
                  size: 20,
                ),
            ],
          ),
        ),
      ),
    );
  }
}