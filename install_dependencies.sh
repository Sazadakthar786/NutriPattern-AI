#!/bin/bash

# macOS Dependency Installer for NutriPattern AI
echo "🍎 Installing macOS dependencies for NutriPattern AI..."

# Check if Homebrew is installed
if ! command -v brew &> /dev/null
then
    echo "❌ Homebrew not found. Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "✅ Homebrew already installed"
fi

# Install Tesseract OCR
echo ""
echo "📝 Installing Tesseract OCR..."
if ! command -v tesseract &> /dev/null
then
    brew install tesseract
    echo "✅ Tesseract OCR installed"
else
    echo "✅ Tesseract OCR already installed"
fi

# Install Poppler (for PDF to image conversion)
echo ""
echo "📄 Installing Poppler..."
if ! command -v pdftoppm &> /dev/null
then
    brew install poppler
    echo "✅ Poppler installed"
else
    echo "✅ Poppler already installed"
fi

# Check Python installation
echo ""
echo "🐍 Checking Python installation..."
if ! command -v python3 &> /dev/null
then
    echo "⚠️  Python 3 not found. Installing..."
    brew install python@3.11
else
    echo "✅ Python 3 already installed"
    python3 --version
fi

echo ""
echo "✅ All system dependencies are ready!"
echo ""
echo "📋 Next steps:"
echo "1. Run: ./run.sh"
echo "2. The app will be available at http://127.0.0.1:5000"
echo ""

