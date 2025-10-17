# Tastecast Deployment Guide

## Overview
This guide will help you deploy Tastecast with:
- **Frontend**: Vercel (React app)
- **Backend**: Render (Python Flask API with ML pipeline)

## Backend Deployment (Render)

### 1. Prepare Backend Repository
```bash
# Navigate to your backend directory
cd "backend/IterationTwo copy"

# Ensure all required files are present:
# - app.py (Flask application)
# - requirements.txt (Python dependencies)
# - Procfile (Render startup command)
# - build.sh (Render build script)
```

### 2. Deploy to Render

1. **Create a Render Account**: Go to [render.com](https://render.com) and sign up

2. **Create a New Web Service**:
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Select the backend directory: `backend/IterationTwo copy`

3. **Configure the Service**:
   ```
   Name: tastecast-backend (or your preferred name)
   Environment: Python 3
   Build Command: ./build.sh
   Start Command: gunicorn app:app
   ```

4. **Set Environment Variables**:
   ```
   FLASK_ENV=production
   PORT=10000 (Render will set this automatically)
   ```

5. **Deploy**: Click "Create Web Service"

6. **Note Your Backend URL**: After deployment, you'll get a URL like:
   `https://tastecast-backend.onrender.com`

### 3. Update Frontend Configuration

Update the `.env` file in your frontend root directory:

```env
# Replace with your actual Render backend URL
VITE_API_BASE_URL_PROD=https://tastecast-backend.onrender.com
VITE_API_BASE_URL_DEV=http://localhost:5001
```

## Frontend Deployment (Vercel)

### 1. Update Environment Variables

In your Vercel dashboard:

1. Go to your project settings
2. Navigate to "Environment Variables"
3. Add:
   ```
   VITE_API_BASE_URL_PROD = https://your-actual-backend.onrender.com
   ```

### 2. Deploy Frontend

Since your frontend is already set up for Vercel:

```bash
# From the root directory
vercel --prod
```

Or simply push to your main branch if auto-deployment is enabled.

## Testing the Deployment

### 1. Test Backend Endpoints

Visit your backend URL to test:
- Health check: `https://your-backend.onrender.com/`
- API endpoints: `https://your-backend.onrender.com/api/advisories`

### 2. Test Frontend Integration

1. Visit your Vercel frontend URL
2. Upload a CSV file
3. Verify that predictions are generated using your real ML backend

## Environment Configurations

### Development
- Frontend: `http://localhost:5173` (Vite dev server)
- Backend: `http://localhost:5001` (Flask dev server)

### Production
- Frontend: `https://your-project.vercel.app`
- Backend: `https://your-backend.onrender.com`

## Troubleshooting

### Backend Issues
- Check Render logs for Python errors
- Ensure all dependencies in `requirements.txt`
- Verify file paths are correct

### Frontend Issues
- Check browser console for API errors
- Verify environment variables are set
- Test API endpoints directly

### CORS Issues
- Backend already configured with `flask-cors`
- Ensure frontend URL is allowed in production

## File Structure

```
Tastecast/
├── src/                    # Frontend React app
├── api/                    # Vercel serverless functions (fallback)
├── backend/IterationTwo copy/  # Python ML backend
│   ├── app.py             # Flask application
│   ├── requirements.txt   # Python dependencies
│   ├── Procfile          # Render startup
│   ├── build.sh          # Render build script
│   └── run_all.py        # ML pipeline
└── .env                  # Environment configuration
```

## Next Steps

1. Deploy backend to Render
2. Update frontend environment variables with real backend URL
3. Deploy frontend to Vercel
4. Test the complete integration
5. Monitor both services for performance

Your Tastecast application will now have:
- Real Python ML predictions from Render backend
- Fast, scalable frontend from Vercel
- Automatic fallback to serverless functions if needed
