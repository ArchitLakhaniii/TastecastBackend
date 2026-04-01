# API Endpoint Empty State Fix

## Problem Solved
When you clear data and reload the site, the API endpoints (`/api/advisories`, `/api/forecast`, `/api/daily-plan`) will now return empty responses instead of showing old CSV data.

## How It Works

### 1. Cleared State Marker
When you call `/api/clear-data`, the system now creates a marker file:
- File: `artifacts/.data_cleared`
- Contains: Timestamp of when data was cleared

### 2. API Endpoint Checks
All three main endpoints now check for this marker first:
- If `artifacts/.data_cleared` exists → Return empty data immediately
- If marker doesn't exist → Load data normally

### 3. Marker Removal
The marker is automatically removed when:
- New CSV data is uploaded via `/api/process-csv`
- Demo data is restored via `/api/restore-demo`

## API Response Examples

### When Data is Cleared
```json
// GET /api/advisories
{
  "advisories": [],
  "message": "No data available - upload CSV to generate recommendations", 
  "cleared": true
}

// GET /api/forecast
{
  "points": [],
  "location": "default",
  "total_forecast": 0,
  "avg_daily": 0,
  "waste_saved_lbs": 0,
  "co2_reduced_kg": 0,
  "message": "No data available - upload CSV to generate forecast",
  "cleared": true
}

// GET /api/daily-plan
{
  "daily_plan": [],
  "total_days": 0,
  "message": "No data available - upload CSV to generate daily plan",
  "cleared": true
}
```

## Testing
1. Call `/api/clear-data` to clear all data
2. Reload your site/page
3. API endpoints will return empty data with `"cleared": true`
4. Upload new CSV or restore demo to get data back

## Result
✅ No more demo data appearing after clearing and reloading!
✅ Clean empty states with helpful messages
✅ Clear indication when data has been cleared vs just missing
