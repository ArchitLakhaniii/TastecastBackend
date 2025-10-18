# Tastecast Backend - Koyeb Deployment Guide

## Overview

This guide will help you deploy the Tastecast Backend (Flask + ML Pipeline) on Koyeb, a serverless platform optimized for containerized applications.

## Prerequisites

1. **Koyeb Account**: Sign up at [koyeb.com](https://www.koyeb.com)
2. **GitHub Repository**: Your code should be in a GitHub repository
3. **Koyeb CLI** (optional): Install for advanced configuration

## Project Structure

Your backend is now configured with:
- `Dockerfile` - Container configuration optimized for Koyeb
- `requirements.txt` - Python dependencies with version constraints
- `Procfile` - Alternative deployment method (buildpack)
- `.koyeb/config.yaml` - Koyeb service configuration
- Health check endpoint at `/api/health`

## Deployment Options

### Option 1: Docker Deployment (Recommended)

#### Step 1: Deploy via Koyeb Dashboard

1. **Login to Koyeb**: Go to [app.koyeb.com](https://app.koyeb.com)

2. **Create New Service**:
   - Click "Create Service"
   - Select "GitHub" as source
   - Connect your GitHub account
   - Select your repository: `TastecastBackend`

3. **Configure Build Settings**:
   ```
   Build Type: Docker
   Dockerfile: Dockerfile (auto-detected)
   Branch: main
   ```

4. **Configure Service Settings**:
   ```
   Service Name: tastecast-backend
   Instance Type: Starter (512MB RAM, 0.25 vCPU)
   Regions: Frankfurt (or your preferred region)
   Port: 8000
   Health Check: /api/health
   ```

5. **Environment Variables** (Optional):
   ```
   FLASK_ENV=production
   PORT=8000 (auto-set by Koyeb)
   ```

6. **Scaling Settings**:
   ```
   Min Instances: 1
   Max Instances: 3
   ```

7. **Deploy**: Click "Deploy"

#### Step 2: Monitor Deployment

- Build logs will show Docker image creation
- Service will be available at: `https://[service-name]-[org].koyeb.app`
- Check health at: `https://[your-url]/api/health`

### Option 2: Buildpack Deployment

If you prefer buildpack over Docker:

1. **In Service Configuration**:
   ```
   Build Type: Buildpack
   Buildpack: Python
   Build Command: pip install -r requirements.txt
   Run Command: web: gunicorn --bind 0.0.0.0:$PORT app:app
   ```

## Environment Configuration

### Production Environment Variables

Set these in Koyeb dashboard under "Environment":

```env
FLASK_ENV=production
PORT=8000
PYTHONPATH=/app
```

### Optional Environment Variables

```env
# If you need custom configurations
FORECAST_HORIZON_DAYS=30
FORECAST_YEAR=2026
```

## API Endpoints

Once deployed, your API will be available at:

```
Base URL: https://[your-service].koyeb.app

Health Check:
GET /api/health

File Upload & Processing:
POST /api/process-csv
Content-Type: application/json
{
  "csv_content": "date,qty_sold\\n2024-01-01,10",
  "filename": "data.csv"
}

Get Advisories:
GET /api/advisories

Get Forecast:
GET /api/forecast?location=default

Get Daily Plan:
GET /api/daily-plan

Beta Signup:
POST /api/beta-signup
{
  "email": "user@example.com"
}
```

## Frontend Integration

Update your frontend environment variables to point to your Koyeb deployment:

```env
# .env file in your frontend
VITE_API_BASE_URL_PROD=https://[your-service].koyeb.app
VITE_API_BASE_URL_DEV=http://localhost:5001
```

## Testing Your Deployment

### 1. Health Check
```bash
curl https://[your-service].koyeb.app/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00.000Z",
  "version": "1.0.0"
}
```

### 2. ML Pipeline Test
```bash
curl -X POST https://[your-service].koyeb.app/api/process-csv \
  -H "Content-Type: application/json" \
  -d '{
    "csv_content": "date,qty_sold\n2024-01-01,10\n2024-01-02,12",
    "filename": "test.csv"
  }'
```

## Monitoring & Logs

### Koyeb Dashboard
- **Service Overview**: Instance status, requests, response times
- **Logs**: Real-time application logs
- **Metrics**: CPU, memory, network usage
- **Deployments**: History and rollback options

### Application Logs
Your Flask application logs will appear in Koyeb's log stream:
```
[INFO] Starting Tastecast Backend Server...
[INFO] Upload folder: /app/uploads
[INFO] Booting worker with pid: 123
```

## Scaling & Performance

### Auto-scaling Configuration
```yaml
# In .koyeb/config.yaml
scaling:
  min: 1    # Always keep 1 instance running
  max: 3    # Scale up to 3 instances under load
```

### Performance Optimization
- **Cold Starts**: ~2-3 seconds for Python/ML workloads
- **Memory**: 512MB recommended for ML operations
- **CPU**: 0.25 vCPU sufficient for small workloads

## Troubleshooting

### Common Issues

#### 1. Build Failures
```bash
# Check requirements.txt compatibility
pip install -r requirements.txt

# Verify Dockerfile builds locally
docker build -t tastecast-backend .
docker run -p 8000:8000 tastecast-backend
```

#### 2. Memory Issues
- Increase instance size to "Small" (1GB RAM)
- Optimize ML model loading in `predcode.py`

#### 3. File Upload Issues
- Ensure upload directories exist (handled in Dockerfile)
- Check file permissions

#### 4. CORS Issues
- Frontend CORS is configured in `app.py`
- Add your frontend domain if needed:
```python
CORS(app, origins=["https://your-frontend.vercel.app"])
```

### Debug Commands

```bash
# Check service status
curl https://[your-service].koyeb.app/api/health

# Test ML pipeline
curl -X POST https://[your-service].koyeb.app/api/process-csv \
  -H "Content-Type: application/json" \
  -d @test-data.json

# View real-time logs in Koyeb dashboard
```

## Cost Optimization

### Koyeb Pricing (Starter)
- **Free Tier**: 1 service, 512MB RAM, limited hours
- **Starter**: ~$5-10/month for small production workloads
- **Scaling**: Pay per instance-hour when scaled

### Tips
1. Use health checks to prevent unnecessary scaling
2. Optimize Docker image size
3. Consider instance hibernation for dev environments

## Security Considerations

1. **Environment Variables**: Store sensitive data in Koyeb environment
2. **HTTPS**: Enabled by default on Koyeb
3. **Container Security**: Non-root user configured in Dockerfile
4. **File Uploads**: Validate and sanitize uploaded CSV files

## Next Steps

1. **Deploy to Koyeb** using this guide
2. **Update Frontend** environment variables
3. **Test Integration** between frontend and backend
4. **Monitor Performance** and optimize as needed
5. **Set up CI/CD** for automated deployments

Your Tastecast backend will now be running on Koyeb with:
- ✅ Containerized deployment
- ✅ Auto-scaling
- ✅ Health monitoring
- ✅ ML pipeline processing
- ✅ Production-ready configuration

## Support

- **Koyeb Docs**: [docs.koyeb.com](https://docs.koyeb.com)
- **Community**: [community.koyeb.com](https://community.koyeb.com)
- **Status**: [status.koyeb.com](https://status.koyeb.com)
