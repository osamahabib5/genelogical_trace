#!/bin/bash
# Project initialization script
# This script sets up the project after cloning

set -e

echo "🔧 Initializing Genealogy Ancestry Chatbot Project..."

# Create necessary directories
mkdir -p uploads

# Copy environment template if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ Created .env file (edit with your OpenAI API key)"
fi

# Make scripts executable
chmod +x start.sh 2>/dev/null || true

# Display setup instructions
echo ""
echo "📋 Project Setup Complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env and add your OpenAI API key:"
echo "   OPENAI_API_KEY=sk-your-api-key-here"
echo ""
echo "2. Start the application:"
echo "   ./start.sh       (Linux/Mac)"
echo "   start.bat        (Windows)"
echo "   docker-compose up -d  (Manual)"
echo ""
echo "3. Open browser:"
echo "   http://localhost:3000"
echo ""
echo "📚 For more information, see:"
echo "   - README.md (full documentation)"
echo "   - QUICK_START.md (5-minute guide)"
echo "   - DEVELOPMENT.md (for developers)"
echo ""
