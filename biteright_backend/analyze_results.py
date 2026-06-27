# biteright_backend/analyze_results.py
"""
Analyze test results and generate detailed report
Compatible with test_accuracy.py output
"""

import json
import os
import csv
from collections import Counter
from datetime import datetime

def analyze_results():
    """Analyze detailed test results"""
    
    print("="*70)
    print("BITERIGHT - DETAILED ACCURACY ANALYSIS")
    print(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Load results
    results_path = 'test_results/detailed_results.json'
    if not os.path.exists(results_path):
        print("\n❌ No test results found. Run test_accuracy.py first.")
        return
    
    with open(results_path, 'r') as f:
        results = json.load(f)
    
    # Load ground truth for reference
    ground_truth = []
    ground_truth_path = 'test_data/ground_truth.csv'
    if os.path.exists(ground_truth_path):
        with open(ground_truth_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ground_truth.append(row)
    
    # Filter successful tests
    successful = [r for r in results if r.get('success', False)]
    failed = [r for r in results if not r.get('success', False)]
    
    print(f"\n📊 TEST SUMMARY")
    print("-"*50)
    print(f"Total test cases: {len(results)}")
    print(f"✅ Successful: {len(successful)} ({len(successful)/len(results)*100:.1f}%)")
    print(f"❌ Failed: {len(failed)} ({len(failed)/len(results)*100:.1f}%)")
    
    if not successful:
        print("\n⚠️ No successful tests to analyze.")
        print("Common issues:")
        print("  - Flask server not running")
        print("  - Image files missing")
        print("  - API endpoint errors")
        return
    
    # Calculate binary accuracy
    correct = sum(1 for r in successful if r.get('is_correct', False))
    total_successful = len(successful)
    
    print(f"\n🎯 CLASSIFICATION ACCURACY")
    print("-"*50)
    print(f"Correct predictions: {correct}/{total_successful}")
    print(f"Binary Classification Accuracy: {correct/total_successful:.2%}")
    
    # Analyze false negatives (MISSED DANGERS - CRITICAL!)
    false_negatives = [r for r in successful if not r.get('is_correct', False) and not r.get('expected_safe', True)]
    print(f"\n⚠️ FALSE NEGATIVES (Missed Dangers) - CRITICAL")
    print("-"*50)
    print(f"Count: {len(false_negatives)}")
    
    if false_negatives:
        print("\nThese are CRITICAL errors - system said SAFE but product was UNSAFE:")
        for fn in false_negatives[:10]:
            print(f"  • {fn.get('image_name', 'unknown')} for {fn.get('profile_id', 'unknown')}")
            print(f"    Expected: UNSAFE | Predicted: {fn.get('predicted_risk', 'unknown')}")
    
    # Analyze false positives (False alarms)
    false_positives = [r for r in successful if not r.get('is_correct', False) and r.get('expected_safe', False)]
    print(f"\n⚠️ FALSE POSITIVES (False Alarms)")
    print("-"*50)
    print(f"Count: {len(false_positives)}")
    
    if false_positives:
        print("\nSystem said UNSAFE but product was actually SAFE:")
        for fp in false_positives[:10]:
            print(f"  • {fp.get('image_name', 'unknown')} for {fp.get('profile_id', 'unknown')}")
            print(f"    Expected: SAFE | Predicted: {fp.get('predicted_risk', 'unknown')}")
    
    # Per-image analysis
    print(f"\n🖼 PER-IMAGE ACCURACY")
    print("-"*50)
    image_stats = {}
    for r in successful:
        img = r.get('image_name', 'unknown')
        if img not in image_stats:
            image_stats[img] = {'correct': 0, 'total': 0}
        image_stats[img]['total'] += 1
        if r.get('is_correct', False):
            image_stats[img]['correct'] += 1
    
    # Sort by accuracy (worst first)
    sorted_images = sorted(image_stats.items(), key=lambda x: x[1]['correct']/x[1]['total'])
    
    print("\nWorst performing images (lowest accuracy):")
    for img, stats in sorted_images[:5]:
        accuracy = stats['correct'] / stats['total']
        print(f"  • {img}: {accuracy:.1%} ({stats['correct']}/{stats['total']} correct)")
    
    print("\nBest performing images (highest accuracy):")
    for img, stats in sorted_images[-5:]:
        accuracy = stats['correct'] / stats['total']
        print(f"  • {img}: {accuracy:.1%} ({stats['correct']}/{stats['total']} correct)")
    
    # Per-profile analysis
    print(f"\n👤 PER-PROFILE ACCURACY")
    print("-"*50)
    profile_stats = {}
    for r in successful:
        pid = r.get('profile_id', 'unknown')
        if pid not in profile_stats:
            profile_stats[pid] = {'correct': 0, 'total': 0, 'false_pos': 0, 'false_neg': 0}
        profile_stats[pid]['total'] += 1
        if r.get('is_correct', False):
            profile_stats[pid]['correct'] += 1
        elif r.get('expected_safe', True):
            profile_stats[pid]['false_pos'] += 1
        else:
            profile_stats[pid]['false_neg'] += 1
    
    for pid, stats in profile_stats.items():
        accuracy = stats['correct'] / stats['total']
        print(f"\n  {pid}:")
        print(f"    Accuracy: {accuracy:.1%} ({stats['correct']}/{stats['total']})")
        print(f"    False Positives (false alarms): {stats['false_pos']}")
        print(f"    False Negatives (missed dangers): {stats['false_neg']}")
    
    # Risk score analysis
    risk_errors = []
    for r in successful:
        if 'expected_score' in r and 'predicted_score' in r:
            error = abs(r['expected_score'] - r['predicted_score'])
            risk_errors.append(error)
    
    if risk_errors:
        print(f"\n📊 RISK SCORE ERROR ANALYSIS")
        print("-"*50)
        print(f"Mean absolute error: {sum(risk_errors)/len(risk_errors):.1f} points")
        print(f"Min error: {min(risk_errors)} points")
        print(f"Max error: {max(risk_errors)} points")
        print(f"Standard deviation: {((sum((e - sum(risk_errors)/len(risk_errors))**2 for e in risk_errors)/len(risk_errors))**0.5):.1f} points")
    
    # Response time analysis
    response_times = [r['response_time'] for r in successful if r.get('response_time', 0) > 0]
    if response_times:
        print(f"\n⚡ PERFORMANCE ANALYSIS")
        print("-"*50)
        print(f"Average response time: {sum(response_times)/len(response_times):.2f} seconds")
        print(f"Fastest: {min(response_times):.2f} seconds")
        print(f"Slowest: {max(response_times):.2f} seconds")
        
        # Check requirement (<60 seconds from Table 3.7)
        avg_time = sum(response_times)/len(response_times)
        if avg_time < 60:
            print(f"✓ Requirement met: Average response time ({avg_time:.1f}s) < 60s")
        else:
            print(f"✗ Requirement NOT met: Average response time ({avg_time:.1f}s) exceeds 60s")
    
    # Summary of failed tests
    if failed:
        print(f"\n❌ FAILED TEST ANALYSIS")
        print("-"*50)
        error_types = Counter()
        for f in failed:
            error_msg = f.get('error', 'Unknown error')[:50]
            error_types[error_msg] += 1
        
        print("Common errors:")
        for error, count in error_types.most_common(5):
            print(f"  • {error}: {count} times")
    
    # Save analysis report
    os.makedirs('test_results', exist_ok=True)
    report_path = 'test_results/analysis_report.txt'
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write("BITERIGHT - DETAILED ANALYSIS REPORT\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*70 + "\n\n")
        
        f.write("TEST SUMMARY\n")
        f.write("-"*50 + "\n")
        f.write(f"Total Test Cases: {len(results)}\n")
        f.write(f"Successful: {len(successful)}\n")
        f.write(f"Failed: {len(failed)}\n")
        f.write(f"Binary Accuracy: {correct/len(successful):.2%}\n\n")
        
        f.write("ERROR ANALYSIS\n")
        f.write("-"*50 + "\n")
        f.write(f"False Negatives (Missed Dangers): {len(false_negatives)}\n")
        f.write(f"False Positives (False Alarms): {len(false_positives)}\n\n")
        
        if risk_errors:
            f.write("RISK SCORE ERROR\n")
            f.write("-"*50 + "\n")
            f.write(f"Mean Error: {sum(risk_errors)/len(risk_errors):.1f} points\n\n")
        
        if response_times:
            f.write("PERFORMANCE\n")
            f.write("-"*50 + "\n")
            f.write(f"Average Response Time: {sum(response_times)/len(response_times):.2f} seconds\n")
            f.write(f"Requirement (<60s): {'MET' if avg_time < 60 else 'NOT MET'}\n")
    
    print(f"\n" + "="*70)
    print(f"✅ Analysis complete!")
    print(f"📄 Report saved to: {report_path}")
    print("="*70)

def print_confusion_matrix_summary():
    """Print confusion matrix summary if metrics file exists"""
    
    metrics_path = 'test_results/accuracy_metrics.json'
    if os.path.exists(metrics_path):
        with open(metrics_path, 'r') as f:
            metrics = json.load(f)
        
        print("\n" + "="*70)
        print("CONFUSION MATRIX SUMMARY")
        print("="*70)
        
        cm = metrics.get('confusion_matrix', {})
        print(f"\n                    Predicted")
        print(f"                    SAFE     UNSAFE")
        print(f"Actual SAFE        {cm.get('true_negative', 0):5d}    {cm.get('false_positive', 0):5d}")
        print(f"       UNSAFE      {cm.get('false_negative', 0):5d}    {cm.get('true_positive', 0):5d}")
        
        print(f"\nAccuracy:  {metrics.get('accuracy', 0):.2%}")
        print(f"Precision: {metrics.get('precision', 0):.2%}")
        print(f"Recall:    {metrics.get('recall', 0):.2%}")
        print(f"F1-Score:  {metrics.get('f1_score', 0):.2%}")
        print(f"Mean Risk Score Error: {metrics.get('mean_risk_score_error', 0):.1f} points")

if __name__ == "__main__":
    analyze_results()
    print_confusion_matrix_summary()