# 🛠️ TastecastBackend Tech Stack

## Overview
**TastecastBackend** is a production-ready ML-powered backend for demand forecasting and inventory optimization for bakeries.

---

## 🎯 Core Architecture

### Backend Framework
- **Flask 2.3+** - Lightweight Python web framework
  - RESTful API design
  - CORS enabled for frontend integration
  - Production-ready with Gunicorn

### Language & Runtime
- **Python 3.11** - Latest stable Python version
- **Docker** - Containerized deployment
- **Gunicorn 20.0+** - Production WSGI server (2 workers)

---

## 🧠 Machine Learning Stack

### ML/Data Science Libraries
- **scikit-learn 1.3+** - Machine learning algorithms
  - Ridge Regression for demand forecasting
  - Model persistence with joblib
  - Prediction intervals

- **pandas 2.0+** - Data manipulation and analysis
  - CSV processing
  - Time series handling
  - DataFrame operations

- **NumPy 1.24+** - Numerical computing
  - Array operations
  - Mathematical functions

- **SciPy 1.10+** - Scientific computing
  - Statistical functions
  - Optimization algorithms

### ML Models
- **Ridge Regression** (Primary forecasting model)
- **Prediction Intervals** for uncertainty quantification
- Pre-trained model stored in: `tastecast_ridge.joblib`

---

## 📊 Data Processing

### Data Storage
- **CSV Files** - Primary data format
  - Historical sales data
  - Forecast outputs
  - Advisory recommendations
  - Contact form submissions
  - Beta signup tracking

### Configuration
- **YAML (PyYAML 6.0+)** - Business configuration
  - Store parameters
  - Recipe configurations
  - Forecast settings
  - Inventory policies

---

## 🎨 Visualization & Reporting

### Libraries
- **Matplotlib 3.6+** - Data visualization
  - Forecast plots
  - Trend analysis
  - Report generation

### Utilities
- **python-dateutil 2.8+** - Advanced date/time handling

---

## 🏗️ Project Structure

### Modular Architecture
```
TastecastBackend/
├── app.py              # Flask API server (main entry point)
├── predcode.py         # ML prediction algorithms
├── run_all.py          # ML pipeline orchestration
├── suggestions.py      # Recommendation engine
├── config.yaml         # Business configuration
│
├── models/             # ML models
│   └── ridge_pi.py     # Ridge regression with prediction intervals
│
├── features/           # Feature engineering
│   └── builders.py     # Feature extraction
│
├── inventory/          # Inventory management
│   └── policy.py       # Reorder point logic
│
├── optimizers/         # Optimization algorithms
│   └── weekly_specials.py  # Special pricing optimizer
│
├── reports/            # Reporting & analytics
│   ├── metrics.py      # Performance metrics
│   ├── plots.py        # Visualization
│   └── export.py       # Data export
│
└── data/               # Data utilities
    └── utils.py        # Data processing helpers
```

---

## 🚀 Deployment Stack

### Containerization
- **Docker** - Container platform
  - Multi-stage builds (not used, but available)
  - Python 3.11-slim base image
  - Non-root user for security
  - Health checks configured

### Platform Options
- **Render.com** - Primary deployment (current)
  - Docker-based deployment
  - Auto-scaling
  - Free tier available
  
- **Koyeb** - Alternative deployment (configured)
  - Container deployment
  - Global edge network

### Server Configuration
- **Gunicorn** (Production WSGI)
  - 2 workers
  - 120s timeout
  - 2s keep-alive
  - Port: Dynamic (from ENV)

---

## 🔧 Development Tools

### Version Control
- **Git** - Source control
- **GitHub** - Code hosting
  - Repo: `ArchitLakhaniii/TastecastBackend`
  - Branch: `main`

### Environment Management
- **venv** - Virtual environment
- **pip** - Package management

---

## 🌐 API Endpoints

### Core Endpoints
```
GET  /                  # API status and info
GET  /api/health        # Health check
GET  /api/advisories    # ML recommendations
GET  /api/forecast      # Demand forecast data
GET  /api/daily-plan    # Daily inventory plan
POST /api/process-csv   # Upload & process data
POST /api/clear-data    # Clear all data
POST /api/restore-demo  # Restore demo data
POST /api/contact       # Contact form
POST /api/beta-signup   # Beta signup
```

### Debug Endpoints
```
GET /api/debug          # Import status
GET /api/logs           # Pipeline logs
GET /api/inspect-files  # File system inspection
```

---

## 🔐 Security Features

- **CORS enabled** - Cross-origin requests
- **Non-root Docker user** - Container security
- **File size limits** - 16MB max upload
- **Input validation** - Email, CSV format checks
- **Environment-based config** - Production/dev separation

---

## 📦 Data Artifacts

### ML Pipeline Outputs
```
artifacts/
├── advisories.csv      # Buy/sell recommendations
├── daily_plan.csv      # Daily inventory projections
└── .data_cleared       # Cleared state marker

uploads/
└── *.csv              # User-uploaded data

beta_signups/
└── beta_signups.csv   # Beta user signups
```

---

## 🎓 ML Features

### Forecasting Capabilities
- **Time series forecasting** (30-day horizon)
- **Demand prediction** with prediction intervals
- **Seasonal pattern detection**
- **Trend analysis**

### Optimization Features
- **Inventory optimization**
  - Reorder point calculation
  - Safety stock management
  - Lead time handling
  
- **Special pricing recommendations**
  - Surplus identification
  - Weekly special optimization
  - Menu item suggestions

### Business Logic
- **Ingredient planning** (apples, dough)
- **Production scheduling**
- **Waste reduction optimization**
- **CO2 impact calculation**

---

## 🔄 Data Flow

1. **CSV Upload** → Frontend sends data
2. **Data Processing** → pandas validation
3. **ML Pipeline** → scikit-learn forecasting
4. **Optimization** → Inventory & special calculations
5. **Advisory Generation** → Buy/sell recommendations
6. **API Response** → JSON data to frontend

---

## 📊 Performance Characteristics

### Local Development
- **Startup**: < 2 seconds
- **ML Pipeline**: 2-5 seconds
- **API Response**: < 100ms

### Production (Render Free Tier)
- **Cold start**: 30-60 seconds
- **ML Pipeline**: 5-10 seconds
- **API Response**: < 1 second

### Production (Render Starter)
- **No cold starts**
- **ML Pipeline**: 2-5 seconds
- **API Response**: < 500ms

---

## 🧪 Testing & Debugging

### Debug Tools
- Pipeline logging system
- File inspection endpoints
- Import status checking
- Health monitoring

### Test Scripts
- `test_cleared_state.py` - Cleared state testing
- `test_fixes.py` - Bug fix validation

---

## 📈 Scalability

### Current Limits (Free Tier)
- **Memory**: 512 MB RAM
- **CPU**: Shared
- **Storage**: Ephemeral (resets on restart)

### Upgrade Path (Starter)
- **Memory**: 512 MB RAM (guaranteed)
- **CPU**: 0.5 vCPU (dedicated)
- **Better**: No cold starts

---

## 🎯 Key Technical Decisions

1. **Flask over FastAPI** - Simplicity, mature ecosystem
2. **scikit-learn over TensorFlow** - Lightweight, sufficient for tabular data
3. **CSV over Database** - Simplicity, portability, low overhead
4. **Docker** - Consistent deployment across platforms
5. **Gunicorn** - Production-grade WSGI server
6. **YAML config** - Human-readable business parameters

---

## 🚧 Future Considerations

### Potential Upgrades
- **Database**: PostgreSQL for persistent storage
- **Caching**: Redis for faster responses
- **Task Queue**: Celery for async ML processing
- **Advanced ML**: Prophet or LSTM for better forecasting
- **Monitoring**: Sentry for error tracking
- **Analytics**: Mixpanel/Amplitude for usage tracking

---

## 📝 Summary

**TastecastBackend** is a modern, production-ready ML backend built with:
- **Python 3.11** + **Flask** + **scikit-learn**
- **Docker** containerization
- **RESTful API** design
- **Modular architecture**
- **Cloud-ready** (Render/Koyeb)

Perfect for: Demand forecasting, inventory optimization, and intelligent business recommendations for bakeries! 🥐📊
