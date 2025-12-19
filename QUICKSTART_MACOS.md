# Quick Start Guide for macOS

## Before You Begin

Your macOS needs Xcode Command Line Tools and Homebrew to install the required dependencies. Follow these steps:

### Step 1: Install Xcode Command Line Tools
```bash
xcode-select --install
```

### Step 2: Install Homebrew
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Step 3: Install Dependencies
```bash
./install_dependencies.sh
```

This will install:
- Tesseract OCR (for reading text from images)
- Poppler (for PDF processing)

### Step 4: Set Up Environment
```bash
python3 setup_env.py
```

This will create a `.env` file with your credentials.

### Step 5: Run the Application
```bash
./run.sh
```

Then open your browser and go to: **http://127.0.0.1:5000**

---

## Alternative: Manual Setup

If you prefer to set up manually:

### 1. Install dependencies one by one:
```bash
brew install tesseract poppler
```

### 2. Create Python virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Python packages:
```bash
pip install -r requirements.txt
```

### 4. Create .env file:
```bash
python3 setup_env.py
```

### 5. Run the application:
```bash
python app.py
```

---

## Troubleshooting

### Homebrew command not found after installation
You may need to add Homebrew to your PATH. Run:
```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

### Permission denied when installing
Some installations require admin access. You may be prompted for your password.

### Port 5000 already in use
If another application is using port 5000, you can change the port in `app.py`:
```python
app.run(debug=True, port=5001)
```

---

## Need Help?

For detailed information, see [MACOS_SETUP.md](MACOS_SETUP.md)

