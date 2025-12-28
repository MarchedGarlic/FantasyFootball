#!/bin/bash
# Fantasy Football Analysis Startup Script

echo "🏈 Starting Fantasy Football Analysis Server..."
echo ""

# Check if Python is installed
if ! command -v python &> /dev/null; then
    echo "❌ Python is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Check if pip is available
if ! command -v pip &> /dev/null; then
    echo "❌ pip is not installed. Please install pip."
    exit 1
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Install Node.js dependencies
if command -v npm &> /dev/null; then
    echo "📦 Installing Node.js dependencies..."
    npm install
else
    echo "⚠️  npm not found. Some build features may not work."
fi

echo ""
echo "🚀 Starting Fantasy Football Analysis Server..."
echo "   Open your browser to: http://localhost:5000"
echo ""
echo "   Press Ctrl+C to stop the server"
echo ""

# Start the Flask server
python server.py