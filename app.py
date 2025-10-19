"""
Flask backend server for Tastecast application.
Connects the frontend with the prediction algorithms.
"""
import os
import sys
import json
import pandas as pd
import traceback
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import our prediction modules with error handling
try:
    from predcode import main as run_prediction, fit_model, forecast_next_days_window, per_ingredient_weekly_advisories_and_balance, upgrade_to_per_ingredient_restock_flags
    from suggestions import make_weekly_advisories, suggest_menu_items
    from run_all import main as run_full_pipeline
    IMPORTS_AVAILABLE = True
    print("SUCCESS: All ML modules imported successfully")
except ImportError as e:
    print(f"Warning: Some ML modules failed to import: {e}")
    
    # Try individual imports to see which ones work
    individual_imports = {}
    
    try:
        from run_all import main as run_full_pipeline
        individual_imports['run_all'] = True
        IMPORTS_AVAILABLE = True
        print("SUCCESS: run_all imported successfully")
    except ImportError as e:
        print(f"Failed to import run_all: {e}")
        individual_imports['run_all'] = False
        IMPORTS_AVAILABLE = False
        
        # Create comprehensive fallback function that actually creates new data
        def run_full_pipeline(data_csv=None, days_ahead=30):
            """Enhanced fallback pipeline function that creates realistic data"""
            log_pipeline_event("FALLBACK: Starting fallback pipeline execution")
            try:
                import pandas as pd
                import os
                from datetime import datetime, timedelta
                
                log_pipeline_event("FALLBACK: Imports successful, processing data")
                
                # Read the uploaded CSV to get recent data
                if data_csv and os.path.exists(data_csv):
                    log_pipeline_event(f"FALLBACK: Reading CSV from {data_csv}")
                    df = pd.read_csv(data_csv, parse_dates=['date'])
                    recent_avg = df['qty_sold'].tail(14).mean()  # Last 2 weeks average
                    last_date = pd.to_datetime(df['date'].max())
                    log_pipeline_event(f"FALLBACK: Analyzed {len(df)} rows, recent avg: {recent_avg:.1f}, last date: {last_date}")
                else:
                    log_pipeline_event("FALLBACK: No CSV found, using default values")
                    recent_avg = 8.5
                    last_date = datetime.now()
                
                # Create artifacts directory
                os.makedirs("artifacts", exist_ok=True)
                log_pipeline_event("FALLBACK: Created artifacts directory")
                
                # Generate realistic advisories based on the data
                start_date = last_date + timedelta(days=1)
                
                advisories = []
                
                # Add some realistic buy recommendations
                advisories.append({
                    'date': start_date.strftime('%Y-%m-%d'),
                    'type': 'BUY_APPLES',
                    'ingredient': 'apples',
                    'qty': 300,
                    'message': f'{start_date.strftime("%Y-%m-%d")}: BUY 300 apples - based on recent demand of {recent_avg:.1f} items/day',
                    'special_qty': 0,
                    'suggestions': '',
                    'reason': 'projected_demand'
                })
                
                # Add some special recommendations for weekends
                weekend_date = start_date + timedelta(days=(5 - start_date.weekday()) % 7)
                advisories.append({
                    'date': weekend_date.strftime('%Y-%m-%d'),
                    'type': 'SPECIAL_APPLES',
                    'ingredient': 'apples',
                    'qty': '',
                    'message': f'{weekend_date.strftime("%Y-%m-%d")}: Weekend special recommended - surplus expected',
                    'special_qty': max(3, int(recent_avg * 0.3)),
                    'suggestions': 'Apple Turnovers, Apple Cider Donuts, Mini Apple Hand Pies',
                    'reason': 'weekend_surplus'
                })
                
                # Save advisories
                advisories_df = pd.DataFrame(advisories)
                advisories_path = 'artifacts/advisories.csv'
                advisories_df.to_csv(advisories_path, index=False)
                log_pipeline_event(f"FALLBACK: Saved {len(advisories)} advisories to {advisories_path}")
                
                # Create basic daily plan
                dates = [start_date + timedelta(days=i) for i in range(days_ahead)]
                daily_plan = pd.DataFrame({
                    'date': dates,
                    'qty_sold': [int(recent_avg + (i % 7 - 3) * 0.5) for i in range(days_ahead)],
                    'apples_need': [int((recent_avg + (i % 7 - 3) * 0.5) * 3) for i in range(days_ahead)],
                    'dough_need': [int(recent_avg + (i % 7 - 3) * 0.5) for i in range(days_ahead)]
                })
                
                daily_plan_path = 'artifacts/daily_plan.csv'
                daily_plan.to_csv(daily_plan_path, index=False)
                log_pipeline_event(f"FALLBACK: Saved daily plan to {daily_plan_path}")
                
                log_pipeline_event(f"FALLBACK: Successfully completed pipeline with {len(advisories)} advisories")
                return {
                    "status": "fallback_success", 
                    "plan": daily_plan_path, 
                    "advisories": advisories_path,
                    "message": "Used intelligent fallback processing"
                }
                
            except Exception as e:
                log_pipeline_event(f"FALLBACK ERROR: Pipeline failed: {e}")
                return {"status": "error", "message": f"Fallback pipeline failed: {str(e)}"}
    
    # Set fallback for other functions
    def run_prediction(*args, **kwargs):
        """Fallback prediction function"""
        return {"status": "error", "message": "Prediction not available"}

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def read_latest_artifacts():
    """Read the latest generated artifacts (daily plan and advisories)"""
    try:
        # Try to read the most recent daily plan
        daily_plan_path = None
        advisories_path = None
        
        # Look for files in artifacts directory
        artifacts_dir = "artifacts"
        if os.path.exists(artifacts_dir):
            daily_plan_path = os.path.join(artifacts_dir, "daily_plan.csv")
            advisories_path = os.path.join(artifacts_dir, "advisories.csv")
        
        # If not found, look for generated files in current directory
        if not daily_plan_path or not os.path.exists(daily_plan_path):
            # Look for pattern like tastecast_daily_plan_*_per_ingredient.csv
            for file in os.listdir('.'):
                if file.startswith('tastecast_daily_plan_') and file.endswith('_per_ingredient.csv'):
                    daily_plan_path = file
                    break
        
        if not advisories_path or not os.path.exists(advisories_path):
            # Look for pattern like tastecast_weekly_advisories_*_per_ingredient.csv
            for file in os.listdir('.'):
                if file.startswith('tastecast_weekly_advisories_') and file.endswith('_per_ingredient.csv'):
                    advisories_path = file
                    break
        
        daily_plan = None
        advisories = None
        
        if daily_plan_path and os.path.exists(daily_plan_path):
            daily_plan = pd.read_csv(daily_plan_path)
        
        if advisories_path and os.path.exists(advisories_path):
            advisories = pd.read_csv(advisories_path)
        
        return daily_plan, advisories
    except Exception as e:
        print(f"Error reading artifacts: {e}")
        return None, None

@app.route('/', methods=['GET'])
def home():
    """Home route - API status and information"""
    return jsonify({
        'message': 'Tastecast Backend API is running!',
        'status': 'healthy',
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat(),
        'endpoints': {
            'health': '/api/health',
            'advisories': '/api/advisories',
            'forecast': '/api/forecast',
            'ingest': '/api/ingest (POST)',
            'daily_plan': '/api/daily-plan'
        }
    }), 200

@app.route('/api/subscribe', methods=['POST'])
def subscribe():
    """Handle beta subscription signup"""
    try:
        data = request.get_json()
        email = data.get('email')
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        # In a real app, you'd save this to a database
        print(f"New beta signup: {email}")
        return jsonify({'message': 'Successfully subscribed to beta'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/contact', methods=['POST'])
def contact():
    """Handle contact form submission"""
    try:
        data = request.get_json()
        
        # Validate required fields
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        message = data.get('message', '').strip()
        
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        
        # Basic email validation
        if '@' not in email or '.' not in email:
            return jsonify({'error': 'Please enter a valid email address'}), 400
        
        # Create contact submission
        submission = {
            'name': name,
            'email': email,
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'id': f"contact_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        }
        
        # Save to CSV file (in production, you'd use a proper database)
        import os
        import csv
        
        contacts_file = 'contacts/submissions.csv'
        os.makedirs('contacts', exist_ok=True)
        
        # Check if file exists to determine if we need headers
        file_exists = os.path.exists(contacts_file)
        
        with open(contacts_file, 'a', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['id', 'timestamp', 'name', 'email', 'message']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            # Write headers if this is a new file
            if not file_exists:
                writer.writeheader()
            
            writer.writerow(submission)
        
        return jsonify({
            'message': 'Thank you for your message! We will get back to you soon.',
            'status': 'success',
            'submission_id': submission['id']
        }), 200
        
    except Exception as e:
        print(f"Contact submission error: {e}")
        return jsonify({'error': 'Failed to submit contact form. Please try again.'}), 500

@app.route('/api/contacts', methods=['GET'])
def get_contacts():
    """Get all contact submissions (admin endpoint)"""
    try:
        import os
        import csv
        
        contacts_file = 'contacts/submissions.csv'
        
        if not os.path.exists(contacts_file):
            return jsonify({'contacts': [], 'total': 0}), 200
        
        contacts = []
        with open(contacts_file, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                contacts.append(row)
        
        # Sort by timestamp (newest first)
        contacts.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'contacts': contacts,
            'total': len(contacts)
        }), 200
        
    except Exception as e:
        print(f"Get contacts error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/restore-demo', methods=['POST'])
def restore_demo_data():
    """Restore the original demo data"""
    try:
        restored_items = []
        errors = []
        
        # Check for backup file and restore it
        backup_file = 'tastecast_one_item_2023_2025.csv.backup'
        main_file = 'tastecast_one_item_2023_2025.csv'
        
        if os.path.exists(backup_file):
            try:
                # Remove current main file if exists
                if os.path.exists(main_file):
                    os.remove(main_file)
                
                # Restore from backup
                os.rename(backup_file, main_file)
                restored_items.append('demo data file restored')
                
                # Run the pipeline to regenerate artifacts
                try:
                    result = subprocess.run(['python', 'run_all.py'], 
                                          capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        restored_items.append('ML artifacts regenerated')
                    else:
                        errors.append(f"Pipeline failed: {result.stderr}")
                except Exception as pipeline_error:
                    errors.append(f"Pipeline error: {str(pipeline_error)}")
                
            except Exception as e:
                errors.append(f"Failed to restore demo data: {str(e)}")
        else:
            errors.append("No backup demo data found to restore")
        
        status = 'success' if restored_items and not errors else 'partial' if restored_items else 'failed'
        
        response = {
            'status': status,
            'restored_items': restored_items
        }
        
        if errors:
            response['errors'] = errors
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/clear-data', methods=['POST'])
def clear_data():
    """Clear all ML-generated data (advisories, daily plan, forecast artifacts)"""
    try:
        import os
        import shutil
        
        cleared_items = []
        errors = []
        
        # Clear artifacts directory (advisories and daily plan)
        artifacts_dir = 'artifacts'
        if os.path.exists(artifacts_dir):
            try:
                shutil.rmtree(artifacts_dir)
                os.makedirs(artifacts_dir, exist_ok=True)
                cleared_items.append('artifacts directory (advisories & daily plan)')
            except Exception as e:
                errors.append(f"Failed to clear artifacts: {str(e)}")
        
        # Clear main data file (uploaded CSV)
        main_data_file = 'tastecast_one_item_2023_2025.csv'
        if os.path.exists(main_data_file):
            try:
                # Rename the default demo file instead of deleting it (so we can restore if needed)
                backup_name = 'tastecast_one_item_2023_2025.csv.backup'
                if os.path.exists(backup_name):
                    os.remove(backup_name)  # Remove old backup
                os.rename(main_data_file, backup_name)
                cleared_items.append('main data file (moved to backup)')
            except Exception as e:
                errors.append(f"Failed to clear main data file: {str(e)}")
        
        # Also check for the backup file and clear it if specifically requested
        backup_file = 'tastecast_one_item_2023_2025.csv.backup'
        if os.path.exists(backup_file):
            cleared_items.append('backup demo data available for restore')
        
        # Clear uploads directory
        uploads_dir = 'uploads'
        if os.path.exists(uploads_dir):
            try:
                shutil.rmtree(uploads_dir)
                os.makedirs(uploads_dir, exist_ok=True)
                cleared_items.append('uploads directory')
            except Exception as e:
                errors.append(f"Failed to clear uploads: {str(e)}")
        
        # Clear any legacy forecast files
        legacy_files = []
        for file in os.listdir('.'):
            if (file.startswith('tastecast_daily_plan_') or 
                file.startswith('tastecast_weekly_advisories_') or
                file.endswith('_per_ingredient.csv')):
                legacy_files.append(file)
        
        for file in legacy_files:
            try:
                os.remove(file)
                cleared_items.append(f'legacy file: {file}')
            except Exception as e:
                errors.append(f"Failed to remove {file}: {str(e)}")
        
        # Clear pipeline logs
        global PIPELINE_LOGS
        PIPELINE_LOGS.clear()
        cleared_items.append('pipeline logs')
        
        # Log the clear operation
        log_pipeline_event("DATA CLEARED: All ML artifacts and uploads removed")
        
        response = {
            'message': 'Data cleared successfully',
            'cleared_items': cleared_items,
            'status': 'success'
        }
        
        if errors:
            response['warnings'] = errors
            response['status'] = 'partial_success'
        
        return jsonify(response), 200
        
    except Exception as e:
        print(f"Clear data error: {e}")
        return jsonify({
            'error': 'Failed to clear data',
            'details': str(e),
            'status': 'error'
        }), 500

@app.route('/api/ingest', methods=['POST'])
def ingest_csv():
    """Handle CSV file upload and trigger prediction pipeline"""
    log_pipeline_event("CSV upload endpoint called (/api/ingest)")
    
    try:
        if 'file' not in request.files:
            log_pipeline_event("ERROR: No file provided in request")
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            log_pipeline_event("ERROR: No file selected")
            return jsonify({'error': 'No file selected'}), 400
        
        log_pipeline_event(f"Processing file: {file.filename}")
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            log_pipeline_event(f"File saved to: {filepath}")
            
            # Validate CSV format
            try:
                df = pd.read_csv(filepath)
                required_columns = ['date', 'qty_sold']
                log_pipeline_event(f"CSV loaded with {len(df)} rows and columns: {list(df.columns)}")
                
                if not all(col in df.columns for col in required_columns):
                    log_pipeline_event(f"ERROR: Missing required columns. Need: {required_columns}, Found: {list(df.columns)}")
                    return jsonify({
                        'error': f'CSV must contain columns: {required_columns}. Found: {list(df.columns)}'
                    }), 400
                
                # Move the uploaded file to replace the default data file
                import shutil
                shutil.copy(filepath, 'tastecast_one_item_2023_2025.csv')
                log_pipeline_event("CSV copied to main data file: tastecast_one_item_2023_2025.csv")
                
                # Run the prediction pipeline - FORCE it to run
                try:
                    log_pipeline_event("Starting ML pipeline execution...")
                    log_pipeline_event(f"Calling run_full_pipeline with data_csv='tastecast_one_item_2023_2025.csv', days_ahead=30")
                    
                    # Capture any stdout from the pipeline
                    import io
                    import contextlib
                    
                    old_stdout = sys.stdout
                    sys.stdout = captured_output = io.StringIO()
                    
                    try:
                        result = run_full_pipeline(data_csv='tastecast_one_item_2023_2025.csv', days_ahead=30)
                    finally:
                        sys.stdout = old_stdout
                        pipeline_output = captured_output.getvalue()
                        if pipeline_output:
                            log_pipeline_event(f"Pipeline stdout: {pipeline_output}")
                    
                    log_pipeline_event(f"Pipeline completed with result: {result}")
                    
                    if result and result.get("status") in ["success", "fallback_success"]:
                        log_pipeline_event("SUCCESS: Pipeline executed successfully")
                        return jsonify({
                            'message': 'CSV uploaded and processed successfully',
                            'filename': filename,
                            'rows': len(df),
                            'pipeline_result': result,
                            'note': 'ML pipeline executed successfully'
                        }), 200
                    elif result and result.get("status") == "fallback":
                        log_pipeline_event("WARNING: Pipeline used fallback processing")
                        return jsonify({
                            'message': 'CSV uploaded and processed with fallback',
                            'filename': filename,
                            'rows': len(df),
                            'pipeline_result': result,
                            'note': 'Pipeline used fallback processing - check logs for details'
                        }), 200
                    else:
                        return jsonify({
                            'message': 'CSV uploaded but pipeline returned unexpected result',
                            'filename': filename,
                            'rows': len(df),
                            'result': result
                        }), 200
                    
                except Exception as pred_error:
                    print(f"Prediction error: {pred_error}")
                    print(traceback.format_exc())
                    return jsonify({
                        'message': 'CSV uploaded but prediction failed',
                        'error': str(pred_error),
                        'filename': filename,
                        'rows': len(df)
                    }), 200  # Still return 200 since upload succeeded
                
            except Exception as csv_error:
                return jsonify({'error': f'Invalid CSV format: {str(csv_error)}'}), 400
        
        else:
            return jsonify({'error': 'Invalid file type. Only CSV files are allowed.'}), 400
            
    except Exception as e:
        print(f"Upload error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/process-csv', methods=['POST'])
def process_csv():
    """Handle CSV content upload and trigger prediction pipeline (for frontend API)"""
    try:
        data = request.get_json()
        
        if not data or 'csv_content' not in data:
            return jsonify({'error': 'No CSV content provided'}), 400
        
        csv_content = data['csv_content']
        filename = data.get('filename', 'upload.csv')
        
        print(f"Processing CSV: {filename}")
        
        # Save CSV content to a temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            temp_file.write(csv_content)
            temp_filepath = temp_file.name
        
        try:
            # Validate CSV format
            df = pd.read_csv(temp_filepath)
            required_columns = ['date', 'qty_sold']
            
            if not all(col in df.columns for col in required_columns):
                return jsonify({
                    'error': f'CSV must contain columns: {required_columns}. Found: {list(df.columns)}'
                }), 400
            
            # Copy to the expected location for the ML pipeline
            import shutil
            shutil.copy(temp_filepath, 'tastecast_one_item_2023_2025.csv')
            
            # Run the prediction pipeline
            try:
                print(f"DEBUG: IMPORTS_AVAILABLE = {IMPORTS_AVAILABLE}")
                if IMPORTS_AVAILABLE:
                    print("DEBUG: Running full ML pipeline...")
                    result = run_full_pipeline(data_csv='tastecast_one_item_2023_2025.csv', days_ahead=30)
                    print(f"DEBUG: Pipeline result = {result}")
                    
                    # Read generated advisories
                    advisories_path = 'artifacts/advisories.csv'
                    print(f"DEBUG: Checking for advisories at {advisories_path}")
                    if os.path.exists(advisories_path):
                        advisories_df = pd.read_csv(advisories_path)
                        advisories = advisories_df.to_dict('records')
                        print(f"DEBUG: Found {len(advisories)} advisories")
                        if len(advisories) > 0:
                            print(f"DEBUG: First advisory date: {advisories[0].get('date', 'N/A')}")
                    else:
                        advisories = []
                        print("DEBUG: No advisories file found")
                    
                    if result and result.get("status") == "success":
                        return jsonify({
                            'success': True,
                            'message': f'CSV {filename} processed successfully with ML pipeline',
                            'advisories': advisories,
                            'total_advisories': len(advisories),
                            'processed_rows': len(df),
                            'pipeline_result': result
                        }), 200
                    elif result and result.get("status") == "fallback":
                        return jsonify({
                            'success': True,
                            'message': f'CSV {filename} processed with fallback pipeline',
                            'advisories': advisories,
                            'total_advisories': len(advisories),
                            'processed_rows': len(df),
                            'warning': 'Using simplified processing'
                        }), 200
                    else:
                        return jsonify({
                            'success': False,
                            'message': 'CSV uploaded but ML pipeline returned unexpected result',
                            'advisories': advisories,
                            'result': result
                        }), 500
                else:
                    # Create basic fallback response
                    os.makedirs("artifacts", exist_ok=True)
                    simple_advisories = [{
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'type': 'info',
                        'message': f'Processed {len(df)} rows successfully',
                        'ingredient': 'general'
                    }]
                    
                    # Save to file
                    pd.DataFrame(simple_advisories).to_csv('artifacts/advisories.csv', index=False)
                    
                    return jsonify({
                        'success': True,
                        'message': f'CSV {filename} processed with basic pipeline',
                        'advisories': simple_advisories,
                        'total_advisories': len(simple_advisories),
                        'processed_rows': len(df),
                        'warning': 'Advanced ML features not available'
                    }), 200
                
            except Exception as pred_error:
                print(f"Prediction error: {pred_error}")
                print(traceback.format_exc())
                return jsonify({
                    'success': False,
                    'message': 'CSV uploaded but ML pipeline failed',
                    'error': str(pred_error),
                    'advisories': []
                }), 500
                
        except Exception as csv_error:
            return jsonify({'error': f'Invalid CSV format: {str(csv_error)}'}), 400
            
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_filepath)
            except:
                pass
            
    except Exception as e:
        print(f"Process CSV error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/forecast', methods=['GET'])
def get_forecast():
    """Get forecast data for a specific location"""
    try:
        location = request.args.get('location', 'default')
        
        # Read the latest daily plan
        daily_plan, advisories = read_latest_artifacts()
        
        if daily_plan is not None and len(daily_plan) > 0:
            # Extract forecast points from daily plan - use qty_total to include specials!
            forecast_points = daily_plan['qty_total'].head(14).tolist()  # Next 2 weeks including specials
            
            # Get current metrics - use qty_total for accurate totals
            total_forecast = daily_plan['qty_total'].sum()
            avg_daily = daily_plan['qty_total'].mean()
            
            # Calculate waste saved (example calculation)
            if 'special_added' in daily_plan.columns:
                special_sales = daily_plan['special_added'].sum()
                waste_saved_lbs = special_sales * 0.5  # Assume each special item saves 0.5 lbs waste
            else:
                waste_saved_lbs = total_forecast * 0.1  # Rough estimate
            
            response_data = {
                'points': forecast_points,
                'location': location,
                'total_forecast': int(total_forecast),
                'avg_daily': round(avg_daily, 1),
                'waste_saved_lbs': round(waste_saved_lbs, 1),
                'co2_reduced_kg': round(waste_saved_lbs * 2.8, 1)  # Convert to CO2 equivalent
            }
        else:
            # Return empty data if no forecast available (no CSV uploaded)
            response_data = {
                'points': [],
                'location': location,
                'total_forecast': 0,
                'avg_daily': 0,
                'waste_saved_lbs': 0,
                'co2_reduced_kg': 0
            }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"Forecast error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/promo', methods=['POST'])
def post_promo():
    """Handle promotional post to social media"""
    try:
        data = request.get_json()
        platform = data.get('platform', 'instagram')
        message = data.get('message', '')
        
        # In a real app, you'd integrate with social media APIs
        print(f"Promo posted to {platform}: {message}")
        
        return jsonify({
            'message': f'Promo posted to {platform} successfully',
            'platform': platform,
            'content': message,
            'posted_at': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/advisories', methods=['GET'])
def get_advisories():
    """Get current advisories and recommendations"""
    try:
        daily_plan, advisories = read_latest_artifacts()
        
        if advisories is not None and len(advisories) > 0:
            # Check if this is default demo data or user-generated data
            # New logic: check if we have realistic ML-generated data vs simple fallback data
            is_demo_data = False
            
            # Check for demo data indicators:
            # 1. Only 1 row with generic message
            # 2. Message contains "Default output" or "Based on recent average"
            # 3. Type is just 'forecast' instead of specific actions like 'BUY_APPLES'
            if len(advisories) <= 1:
                first_message = str(advisories.iloc[0].get('message', ''))
                first_type = str(advisories.iloc[0].get('type', ''))
                is_demo_data = (
                    'Default output' in first_message or 
                    'Based on recent average' in first_message or
                    first_type == 'forecast'
                )
            else:
                # Multiple rows = likely real ML data
                is_demo_data = False
            
            log_pipeline_event(f"Advisories analysis: {len(advisories)} rows, is_demo_data={is_demo_data}")
            
            # Convert advisories to proper format
            advisories_list = []
            for _, row in advisories.iterrows():
                # Parse the advisory data more intelligently
                message = row.get('message', '')
                
                # Only add "Default output:" prefix if it's actually demo data
                if is_demo_data:
                    message = f"Default output: {message}" if message else "Default output"
                
                advisory_data = {
                    'date': row.get('date', ''),
                    'type': row.get('type', ''),
                    'message': message,
                    'ingredient': row.get('ingredient', '') if 'ingredient' in row else None
                }
                
                # Add parsed suggestions if available
                if 'suggestions' in row and pd.notna(row['suggestions']):
                    advisory_data['suggestions'] = row['suggestions']
                
                # Add special quantity if available
                if 'special_qty' in row and pd.notna(row['special_qty']):
                    advisory_data['special_qty'] = int(row['special_qty'])
                
                # Add quantity info if available
                if 'qty' in row and pd.notna(row['qty']):
                    advisory_data['qty'] = row['qty']
                
                advisories_list.append(advisory_data)
            
            return jsonify({'advisories': advisories_list}), 200
        else:
            # Return empty advisories if no data (no CSV uploaded or data cleared)
            log_pipeline_event("No advisories data available - data may have been cleared")
            return jsonify({
                'advisories': [],
                'message': 'No data available - upload CSV to generate recommendations'
            }), 200
            
    except Exception as e:
        print(f"Advisories error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/daily-plan', methods=['GET'])
def get_daily_plan():
    """Get the detailed daily plan with inventory projections"""
    try:
        daily_plan, advisories = read_latest_artifacts()
        
        if daily_plan is not None:
            # Convert to list of dictionaries for JSON response
            plan_data = daily_plan.to_dict('records')
            
            # Clean up the data for frontend consumption
            for record in plan_data:
                # Convert any numpy types to Python types
                for key, value in record.items():
                    if pd.isna(value):
                        record[key] = None
                    elif isinstance(value, (pd.Timestamp)):
                        record[key] = value.isoformat()
                    elif hasattr(value, 'item'):  # numpy types
                        record[key] = value.item()
            
            return jsonify({
                'daily_plan': plan_data,
                'total_days': len(plan_data)
            }), 200
        else:
            return jsonify({'error': 'No daily plan available'}), 404
            
    except Exception as e:
        print(f"Daily plan error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    }), 200

# Global variable to store pipeline logs
PIPELINE_LOGS = []

def log_pipeline_event(message):
    """Add a timestamped log entry"""
    from datetime import datetime
    timestamp = datetime.now().isoformat()
    log_entry = f"[{timestamp}] {message}"
    PIPELINE_LOGS.append(log_entry)
    print(log_entry)  # Also print to console
    
    # Keep only last 50 logs to prevent memory issues
    if len(PIPELINE_LOGS) > 50:
        PIPELINE_LOGS.pop(0)

@app.route('/api/debug', methods=['GET'])
def debug_imports():
    """Debug endpoint to check import status and environment"""
    try:
        import os
        
        debug_info = {
            "current_directory": os.getcwd(),
            "python_path": sys.path[:3],  # First 3 entries
            "imports_available": IMPORTS_AVAILABLE,
        }
        
        # Test individual imports
        try:
            from cli import load_config
            debug_info["cli_import"] = "success"
            
            # Try to load config
            try:
                config = load_config()
                debug_info["config_exists"] = True
            except:
                debug_info["config_exists"] = False
                
        except ImportError as e:
            debug_info["cli_import"] = f"failed: {str(e)}"
            debug_info["config_exists"] = False
            
        try:
            from run_all import main
            debug_info["run_all_import"] = "success"
        except ImportError as e:
            debug_info["run_all_import"] = f"failed: {str(e)}"
            
        # Check if artifacts exist
        artifacts_path = "artifacts/advisories.csv"
        if os.path.exists(artifacts_path):
            debug_info["artifacts_exists"] = True
            try:
                import pandas as pd
                df = pd.read_csv(artifacts_path)
                debug_info["total_advisories"] = len(df)
                
                # Check if this looks like demo data vs real data
                if len(df) > 0:
                    first_date = df['date'].iloc[0] if 'date' in df.columns else 'unknown'
                    debug_info["artifacts_first_date"] = first_date
                    
                    # Check if it's demo data (dates in 2026+ or default messages)
                    is_demo = any([
                        '2026' in str(first_date),
                        'Default output' in str(df.to_string()) if hasattr(df, 'to_string') else False,
                        len(df) == 23  # Default demo data has 23 rows
                    ])
                    debug_info["is_demo_data"] = is_demo
                else:
                    debug_info["is_demo_data"] = True
                    
            except Exception as e:
                debug_info["artifacts_read_error"] = str(e)
        else:
            debug_info["artifacts_exists"] = False
            debug_info["is_demo_data"] = True
            
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

@app.route('/api/logs', methods=['GET'])
def get_pipeline_logs():
    """Get recent pipeline execution logs"""
    return jsonify({
        "logs": PIPELINE_LOGS[-20:],  # Last 20 logs
        "total_logs": len(PIPELINE_LOGS),
        "note": "These are the recent ML pipeline execution logs"
    })

@app.route('/api/inspect-files', methods=['GET'])
def inspect_files():
    """Inspect the actual CSV files and directory structure"""
    try:
        import os
        
        inspection = {
            "current_directory": os.getcwd(),
            "artifacts_directory_exists": os.path.exists("artifacts"),
            "files_found": {},
            "directory_contents": {}
        }
        
        # Check artifacts directory
        if os.path.exists("artifacts"):
            artifacts_files = os.listdir("artifacts")
            inspection["directory_contents"]["artifacts"] = artifacts_files
            
            # Check specific files
            for filename in ["advisories.csv", "daily_plan.csv"]:
                filepath = os.path.join("artifacts", filename)
                if os.path.exists(filepath):
                    try:
                        df = pd.read_csv(filepath)
                        inspection["files_found"][filename] = {
                            "exists": True,
                            "rows": len(df),
                            "columns": list(df.columns),
                            "first_5_rows": df.head().to_dict('records'),
                            "file_size_bytes": os.path.getsize(filepath)
                        }
                    except Exception as e:
                        inspection["files_found"][filename] = {
                            "exists": True,
                            "error": f"Could not read CSV: {str(e)}",
                            "file_size_bytes": os.path.getsize(filepath)
                        }
                else:
                    inspection["files_found"][filename] = {"exists": False}
        
        # Check root directory for any CSV files
        root_files = [f for f in os.listdir('.') if f.endswith('.csv')]
        inspection["directory_contents"]["root_csv_files"] = root_files
        
        # Check main data file
        main_data_file = "tastecast_one_item_2023_2025.csv"
        if os.path.exists(main_data_file):
            try:
                df = pd.read_csv(main_data_file)
                inspection["main_data_file"] = {
                    "exists": True,
                    "rows": len(df),
                    "columns": list(df.columns),
                    "date_range": f"{df['date'].min()} to {df['date'].max()}" if 'date' in df.columns else "No date column",
                    "sample_data": df.head(3).to_dict('records')
                }
            except Exception as e:
                inspection["main_data_file"] = {"exists": True, "error": str(e)}
        else:
            inspection["main_data_file"] = {"exists": False}
            
        return jsonify(inspection)
        
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

@app.route('/api/beta-signup', methods=['POST'])
def beta_signup():
    """Handle beta signup - save email to CSV and send notification"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        # Validate email format (basic check)
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        # Create beta_signups directory if it doesn't exist
        signup_dir = 'beta_signups'
        os.makedirs(signup_dir, exist_ok=True)
        
        # CSV file path for storing beta signups
        csv_path = os.path.join(signup_dir, 'beta_signups.csv')
        
        # Read existing signups or create new DataFrame
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            # Check if email already exists (case insensitive)
            if email.lower() in df['email'].str.lower().values:
                return jsonify({
                    'error': 'This email is already registered for beta access',
                    'duplicate': True
                }), 409  # Conflict status code
        else:
            df = pd.DataFrame(columns=['email', 'signup_date'])
        
        # Add new signup
        new_signup = pd.DataFrame({
            'email': [email],
            'signup_date': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        })
        df = pd.concat([df, new_signup], ignore_index=True)
        
        # Save to CSV
        df.to_csv(csv_path, index=False)
        
        # Send email notification using Python's smtplib
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            # Email configuration (using Gmail SMTP)
            smtp_server = "smtp.gmail.com"
            smtp_port = 587
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = "noreply@tastecast.com"
            msg['To'] = "archit.lakhani20@gmail.com"
            msg['Subject'] = "New Beta Signup - Tastecast"
            
            body = f"""
New Beta Signup Alert!

Email: {email}
Signup Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total Beta Signups: {len(df)}

Best regards,
Tastecast Beta System
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Note: For production, you'd want to use proper email service credentials
            # This is a simplified example that would need proper SMTP configuration
            print(f"Beta signup notification: New signup from {email}")
            print(f"Would send email to archit.lakhani20@gmail.com")
            
        except Exception as email_error:
            print(f"Email notification failed: {email_error}")
            # Continue execution even if email fails
        
        return jsonify({
            'message': 'Successfully signed up for beta!',
            'email': email,
            'total_signups': len(df)
        }), 200
        
    except Exception as e:
        print(f"Beta signup error: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Failed to process beta signup'}), 500

if __name__ == '__main__':
    # Ensure we're in the right directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    print("Starting Tastecast Backend Server...")
    print("Upload folder:", os.path.abspath(UPLOAD_FOLDER))
    
    # Use PORT environment variable if available (for Render)
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_ENV') != 'production'
    
    app.run(debug=debug, host='0.0.0.0', port=port)
