#!/usr/bin/env python3
"""
Test script to validate the ML pipeline fixes
"""
import os
import sys
import tempfile

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test if all imports work"""
    print("Testing imports...")
    
    try:
        from cli import load_config
        print("✅ cli import successful")
    except ImportError as e:
        print(f"❌ cli import failed: {e}")
    
    try:
        from run_all import main as run_full_pipeline
        print("✅ run_all import successful")
    except ImportError as e:
        print(f"❌ run_all import failed: {e}")
    
    try:
        import app
        print("✅ app import successful")
    except ImportError as e:
        print(f"❌ app import failed: {e}")

def test_config_loading():
    """Test config loading"""
    print("\nTesting config loading...")
    
    try:
        from cli import load_config
        config = load_config("config.yaml")
        print("✅ Config loaded successfully")
        print(f"   - Forecast horizon: {config.get('forecast', {}).get('forecast_horizon_days', 'Not found')}")
        return True
    except Exception as e:
        print(f"❌ Config loading failed: {e}")
        return False

def test_pipeline():
    """Test the ML pipeline with sample data"""
    print("\nTesting ML pipeline...")
    
    # Create sample CSV data
    sample_data = """date,qty_sold,apples_start,dough_start,apples_end,dough_end,restocked
2023-01-01,9,300,120,273,111,0
2023-01-02,7,273,111,252,104,0
2023-01-03,9,252,104,225,95,0
2023-01-04,9,225,95,198,86,0
2023-01-05,6,198,86,180,80,0"""
    
    try:
        # Save sample data to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(sample_data)
            temp_path = f.name
        
        # Test the pipeline
        from run_all import main as run_full_pipeline
        result = run_full_pipeline(data_csv=temp_path, days_ahead=7)
        
        print("✅ Pipeline executed successfully")
        print(f"   - Result: {result}")
        
        # Clean up
        os.unlink(temp_path)
        return True
        
    except Exception as e:
        print(f"❌ Pipeline test failed: {e}")
        # Clean up
        if 'temp_path' in locals():
            try:
                os.unlink(temp_path)
            except:
                pass
        return False

def main():
    """Run all tests"""
    print("🔧 Testing Tastecast Backend Fixes\n")
    
    test_imports()
    config_ok = test_config_loading()
    pipeline_ok = test_pipeline()
    
    print("\n" + "="*50)
    if config_ok and pipeline_ok:
        print("🎉 All tests passed! Backend should work on Koyeb.")
    else:
        print("⚠️  Some tests failed. Check the errors above.")
    print("="*50)

if __name__ == "__main__":
    main()
