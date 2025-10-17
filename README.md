# Tastecast Backend

Flask backend server for the Tastecast ML-powered restaurant forecasting application.

## Features

- **ML Pipeline**: Real-time demand forecasting using scikit-learn
- **CSV Processing**: Upload and process restaurant data
- **Advisory Generation**: Generate buy/special recommendations
- **REST API**: Full API for frontend integration

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
python app.py
```

Server will start at `http://localhost:5001`

### Production Deployment (Render)

1. Connect your repository to Render
2. Set up a new Web Service
3. Use these settings:
   - **Build Command**: `./build.sh`
   - **Start Command**: `gunicorn app:app`
   - **Environment**: Python 3

## API Endpoints

### Health Check
```
GET /
```

### Process CSV Data
```
POST /api/process-csv
Content-Type: application/json

{
  "csv_content": "date,item,quantity\n2024-01-01,apples,100",
  "filename": "data.csv"
}
```

### Get Advisories
```
GET /api/advisories
```

### Get Forecasts
```
GET /api/forecasts
```

## Environment Variables

- `FLASK_ENV`: Set to `production` for production deployment
- `PORT`: Port number (auto-set by Render)

## File Structure

```
backend/IterationTwo copy/
├── app.py              # Main Flask application
├── run_all.py          # ML pipeline entry point
├── predcode.py         # Prediction algorithms
├── suggestions.py      # Menu suggestion logic
├── requirements.txt    # Python dependencies
├── Procfile           # Render startup command
├── build.sh           # Render build script
├── artifacts/         # Generated predictions
└── uploads/           # Uploaded CSV files
```

## ML Pipeline

The backend uses a sophisticated ML pipeline that:

1. **Data Ingestion**: Processes uploaded CSV files
2. **Feature Engineering**: Extracts relevant patterns
3. **Demand Forecasting**: Uses ridge regression for predictions
4. **Advisory Generation**: Creates buy/special recommendations
5. **Menu Suggestions**: Generates menu items for surplus ingredients

## Dependencies

- Flask: Web framework
- Flask-CORS: Cross-origin resource sharing
- pandas: Data manipulation
- scikit-learn: Machine learning
- numpy: Numerical computing
- gunicorn: WSGI server for production
