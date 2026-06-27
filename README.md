# BiteRight — Allergen & Dietary Risk Detection System

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Flutter](https://img.shields.io/badge/Flutter-3.0+-blue.svg)](https://flutter.dev/)
[![Firebase](https://img.shields.io/badge/Firebase-9.0+-orange.svg)](https://firebase.google.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**BiteRight** is an AI-powered mobile application that helps individuals with food allergies and dietary restrictions identify harmful ingredients in packaged food products. By photographing food labels, the system runs OCR → NLP/ML analysis → personalized allergen risk assessment based on the user's dietary profile.

---

## 📱 Key Features

### Core Functionality
- **Personalized Dietary Profiles**: Users can select from 10 allergens and 6 dietary restrictions (Halal, Vegan, Diabetic, Low Sodium, Vegetarian, Keto) with severity levels
- **OCR-Based Ingredient Extraction**: Dual-engine approach with OCR.Space API (primary) and Tesseract OCR (fallback)
- **NLP Allergen Detection**: Context-aware parsing with negation detection and safe-term filtering
- **AI/ML Risk Classification**: Hybrid ensemble (60% Random Forest + 40% rules)
- **Editable Ingredient List**: Users can correct OCR errors before analysis

### User Features
- **Real-Time Risk Alerts**: Color-coded indicators (Safe/Caution/Unsafe)
- **Scan History**: View, filter, and delete past scans
- **Gamification Badges**: 15 achievement badges with unlock animations
- **Analytics Dashboard**: Track scan statistics and safety trends
- **Password Reset**: OTP-based password recovery

---

## 🏗️ System Architecture

```
Flutter Mobile App (Dart)
        │  HTTP REST
        ▼
  Flask Backend (Python)
   ┌─────────────────────────────────────────┐
   │  OCR Service        NLP Service         │
   │  (OCR.Space API +   (Regex + Patterns)  │
   │   Tesseract)                            │
   │                   Risk Analyzer         │
   │                   (Fuzzy + Rules)       │
   │                   Processing Service    │
   │                   (RF ML 60% + Rules 40%)│
   └─────────────────────────────────────────┘
                    │
             Firebase Firestore
   [users, scan_history, product_ingredients,
    ingredient_matches, dietary_restrictions,
    user_badges]
```

---

## 🧩 Technology Stack

### Frontend (Mobile)
- **Framework**: Flutter (Dart) — cross-platform for Android & iOS
- **State Management**: StatefulWidget + setState
- **Database**: Firebase Firestore (NoSQL)
- **Authentication**: Email/Password with OTP reset

### Backend
- **Framework**: Python Flask REST API
- **OCR**: OCR.Space API (primary) + Tesseract (fallback)
- **Image Processing**: OpenCV
- **NLP**: NLTK, PyEnchant, Regex
- **ML**: Scikit-learn (Random Forest Classifier)
- **Database**: Firebase Admin SDK

---

## 📊 Performance Metrics

| Component | Metric | Result |
|-----------|--------|--------|
| **OCR** | Character Accuracy | **99.05%** (+63.52% vs Tesseract-only) |
| **NLP** | Binary Classification Accuracy | **100.00%** |
| **NLP** | Per-Allergen Precision/Recall | 85.45% / 88.68% |
| **ML/AI** | End-to-End Accuracy | **100.00%** |
| **ML/AI** | Response Time | **0.155 seconds** |
| **ML/AI** | Risk Score MAE | 6.1 points |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Flutter 3.0+
- Firebase Account
- OCR.Space API Key (optional, for primary OCR)

### Backend Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/biteright.git
cd biteright/biteright_backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure Firebase credentials
# Place your firebase-adminsdk.json in the config/ directory

# Run the Flask server
python app.py
```

### Mobile App Setup

```bash
cd biteright/biteright_app

# Install Flutter dependencies
flutter pub get

# Run the app
flutter run
```

---

## 📁 Project Structure

```
biteright/
├── biteright_app/                # Flutter mobile application
│   ├── lib/
│   │   ├── screens/              # UI screens (login, scan, history, etc.)
│   │   ├── models/               # Data models (UserProfile, ScanHistory, etc.)
│   │   └── services/             # API service (ApiService)
│   └── pubspec.yaml
│
├── biteright_backend/            # Flask backend
│   ├── services/
│   │   ├── ocr_service.py        # Dual-engine OCR (API + Tesseract)
│   │   ├── nlp_service.py        # Regex-based allergen detection
│   │   ├── risk_analyzer.py      # Rule-based risk engine
│   │   ├── processing_service.py # Hybrid ML (60%) + Rules (40%)
│   │   └── dietary_checker.py    # Legacy dietary checker
│   ├── models/                   # ML model files (random_forest.pkl)
│   ├── config/                   # Firebase credentials
│   ├── app.py                    # Flask routes & server
│   └── requirements.txt
│
└── README.md
```

---

## 🧪 Testing

### Unit Testing
```bash
cd biteright_backend
python -m pytest tests/
```

### Functional Testing (API)
```bash
# Extract ingredients from image
curl -X POST -F "image=@label.jpg" http://localhost:5000/extract-ingredients

# Analyze ingredients with user profile
curl -X POST -H "Content-Type: application/json" \
  -d '{"ingredients_text": "peanuts, sugar", "user_id": "USER_ID"}' \
  http://localhost:5000/analyze-with-profile
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 👥 Contributors

- **Nur Athirah Binti Azmi** — Project Developer & Researcher

---

## 🙏 Acknowledgments

- Universiti Teknologi MARA (UiTM)
- Faculty of Computer and Mathematical Sciences

---

> **Note**: This project was developed as part of a Bachelor of Information Technology (Hons.) thesis at Universiti Teknologi MARA.
