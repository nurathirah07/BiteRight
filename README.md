# BiteRight — Allergen & Dietary Risk Detection System

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Flutter](https://img.shields.io/badge/Flutter-3.0+-blue.svg)](https://flutter.dev/)
[![Firebase](https://img.shields.io/badge/Firebase-9.0+-orange.svg)](https://firebase.google.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**BiteRight** is an AI-powered mobile application that helps individuals with food allergies and dietary restrictions identify harmful ingredients in packaged food products. By photographing food labels, the system runs OCR → NLP/ML analysis → personalized allergen risk assessment based on the user's dietary profile.

---

## 📱 Key Features

### Core Functionality
- **Personalized Food Safety Profiles**: Choose from 10 allergens and 6 dietary restrictions (Halal, Vegan, Diabetic, Low Sodium, Vegetarian, Keto).
- **Allergen Severity Level Customization**: Set custom severity levels (**High**, **Medium**, **Low**) for each selected allergen to tune alert sensitivity.
- **Interactive Severity Level Guide & Fallback Advice**: Built-in interactive guide explaining High (severe/anaphylaxis), Medium (moderate/hives), and Low (mild intolerance) levels, including step-by-step guidance for users unsure of their severity.
- **OCR-Based Ingredient Extraction**: Dual-engine approach using OCR.Space API (primary) and Tesseract OCR (fallback).
- **NLP Allergen Detection**: Context-aware parsing with negation detection, safe-term filtering, and ingredient synonym matching.
- **AI/ML Risk Classification**: Hybrid ensemble model combining 60% Random Forest Classifier + 40% rule-based safety verification.
- **Editable Ingredient List**: Users can review and edit extracted OCR text before running risk analysis.

### User Features
- **Real-Time Risk Alerts**: Color-coded risk indicators (Safe / Caution / Unsafe) with detailed ingredient breakdown.
- **Scan History**: View, filter, search, and delete past product scans.
- **Gamification & Achievement Badges**: 15 unlockable badges celebrating food safety milestones and scan streaks.
- **Analytics Dashboard**: Comprehensive charts tracking daily, weekly, and monthly scan trends and safety stats.
- **Password Reset**: Secure OTP-based email password recovery.

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
- **Authentication**: Email/Password with signed session tokens and OTP reset

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

# Configure environment (see the table below)
cp .env.example .env   # then fill in the values

# Run the Flask server
python app.py
```

#### Backend environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `SECRET_KEY` | **Yes (production)** | Signs session tokens. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`. If unset, a random key is used and everyone is signed out whenever the server restarts. |
| `FIREBASE_CREDENTIALS_JSON` | One of these two | Full service-account JSON as a single string (convenient on Render). |
| `FIREBASE_KEY_PATH` | One of these two | Path to the service-account file (default `serviceAccountKey.json`). |
| `BREVO_API_KEY` / `SENDER_EMAIL` | For password reset | Sends reset-code emails. SMTP (`SMTP_SERVER`, `SMTP_PORT`, `SENDER_PASSWORD`) is the fallback. |
| `AUTH_REQUIRED` | No | Defaults to `true`. Set `false` only for local debugging without tokens. |
| `TOKEN_MAX_AGE_DAYS` | No | Session lifetime, default 30 days. |
| `MAX_UPLOAD_MB` | No | Largest accepted image, default 10 MB. |
| `ENABLE_DEBUG_ENDPOINTS` | No | Exposes `/test-firebase`, `/test-products`, `/search-allergens/*`, `GET /users` and `/test/analyze`. Keep off in production. |
| `LOG_RESET_CODES` | No | Prints reset codes to the server log. Local development only. |

#### Authentication

`POST /login` and `POST /users` return a `token`. Every user-scoped endpoint
(`/users/<id>/...`, `/analyze-with-profile`, `/barcode/<code>`) requires
`Authorization: Bearer <token>`, and a token only grants access to its own
user. Passwords are hashed with scrypt; accounts created with the older
SHA-256 scheme are upgraded automatically on their next sign-in.

### Mobile App Setup

```bash
cd biteright/biteright_mobile

# Install Flutter dependencies
flutter pub get

# Run the app against the production backend
flutter run

# ...or against a local backend (Android emulator shown)
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:5000
```

---

## 📁 Project Structure

```
biteright/
├── biteright_mobile/                # Flutter mobile application
│   ├── lib/
│   │   ├── screens/              # UI screens (login, scan, profile setup, analytics, etc.)
│   │   ├── models/               # Data models (UserProfile, ScanHistory, AnalyticsSummary, etc.)
│   │   └── services/             # ApiService (HTTP client) and SessionService (sign-in state)
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
│   ├── app.py                    # Flask routes & server
│   ├── security.py               # Password hashing, session tokens, rate limiting
│   ├── analytics.py              # Scan statistics & achievement badges
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

cd ../biteright_mobile
flutter test
```

### Functional Testing (API)
```bash
# Extract ingredients from image
curl -X POST -F "image=@label.jpg" http://localhost:5000/extract-ingredients

# Sign in to get a session token
curl -X POST -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "your-password"}' \
  http://localhost:5000/login

# Analyze ingredients with user profile
curl -X POST -H "Content-Type: application/json" \
  -H "Authorization: Bearer TOKEN" \
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
