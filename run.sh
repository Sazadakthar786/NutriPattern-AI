#!/bin/bash

# NutriPattern AI - macOS/Linux Startup Script
echo "🥗 Starting NutriPattern AI..."
echo ""

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    
    # Try to use python3.11 if available (better compatibility)
    if command -v python3.11 &> /dev/null; then
        echo "Using Python 3.11..."
        python3.11 -m venv venv
    elif command -v python3 &> /dev/null; then
        echo "Using Python 3..."
        python3 -m venv venv
    else
        echo "❌ Python 3 not found"
        echo "Install with: brew install python@3.11"
        exit 1
    fi
    
    if [ $? -ne 0 ]; then
        echo "❌ Failed to create virtual environment"
        echo "Try: brew install python@3.11"
        exit 1
    fi
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found!"
    echo "📝 Please run: python3 setup_env.py"
    echo "Or manually create a .env file from env_template.txt"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Install requirements
echo "📥 Installing/updating requirements..."
pip install -r requirements.txt

# Create uploads directory if it doesn't exist
echo "📁 Creating uploads directory..."
mkdir -p uploads
mkdir -p uploads/profile_images

# Check if Tesseract is available
if ! command -v tesseract &> /dev/null; then
    echo "⚠️  WARNING: Tesseract OCR not found!"
    echo "Run ./install_dependencies.sh to install it"
    echo ""
fi

# Start Flask app
echo ""
echo "✅ Starting Flask application..."
echo "📖 NutriPattern AI will be available at: http://127.0.0.1:5001"
echo "⚠️  Press Ctrl+C to stop the server"
echo ""
python app.py

