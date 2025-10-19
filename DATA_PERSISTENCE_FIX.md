# Data Persistence Fix

## Problem
When users clicked "Clear Data", the data would clear successfully but return after page reload. This happened because:

1. The clear endpoint removed artifacts but left the demo CSV file (`tastecast_one_item_2023_2025.csv`)
2. When the frontend reloaded and requested advisories, the system found no artifacts
3. The system automatically regenerated ML artifacts from the demo CSV file
4. Result: Demo data appeared to "come back" after clearing

## Solution

### Updated Clear Data Endpoint (`/api/clear-data`)
Instead of deleting the demo file, we now:
1. **Move** the demo file to `.backup` extension: `tastecast_one_item_2023_2025.csv.backup`
2. Clear all artifacts as before
3. This prevents automatic regeneration from demo data

### New Restore Demo Endpoint (`/api/restore-demo`)
Added endpoint to restore demo data when needed:
1. Moves `.backup` file back to active name
2. Regenerates ML artifacts from demo data
3. Allows users to get back to demo state if needed

### Updated Advisories Endpoint
Modified to handle truly empty states:
- Returns helpful message when no data exists
- Doesn't auto-regenerate from demo file
- Cleaner UX for empty states

## Usage

### Clear All Data (Persistent)
```bash
curl -X POST http://localhost:5001/api/clear-data
```
Response:
```json
{
  "status": "success",
  "cleared_items": [
    "artifacts directory",
    "main data file (moved to backup)", 
    "uploads directory",
    "pipeline logs"
  ]
}
```

### Restore Demo Data
```bash
curl -X POST http://localhost:5001/api/restore-demo
```

### Check Empty State
```bash
curl http://localhost:5001/api/advisories
```
Returns:
```json
{
  "advisories": [],
  "message": "No data available - upload CSV to generate recommendations"
}
```

## Technical Details

The core issue was that the ML system has a fallback mechanism to use demo data when no user data exists. By moving (not deleting) the demo file, we break this fallback chain while preserving the ability to restore if needed.

This solution provides:
- ✅ Persistent data clearing 
- ✅ Ability to restore demo data
- ✅ Clean empty states
- ✅ No loss of demo data
- ✅ Better user experience

## Files Modified
- `app.py`: Updated clear/restore endpoints and advisories handling
- Added this documentation file
