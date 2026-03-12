@echo off
REM Project initialization script for Windows
REM This script sets up the project after cloning

echo.
echo 🔧 Initializing Genealogy Ancestry Chatbot Project...
echo.

REM Create necessary directories
if not exist uploads mkdir uploads

REM Copy environment template if not exists
if not exist .env (
    copy .env.example .env
    echo ✅ Created .env file (edit with your OpenAI API key)
)

REM Display setup instructions
echo.
echo 📋 Project Setup Complete!
echo.
echo Next steps:
echo 1. Edit .env and add your OpenAI API key:
echo    OPENAI_API_KEY=sk-your-api-key-here
echo.
echo 2. Start the application:
echo    start.bat
echo    or
echo    docker-compose up -d
echo.
echo 3. Open browser:
echo    http://localhost:3000
echo.
echo 📚 For more information, see:
echo    - README.md (full documentation)
echo    - QUICK_START.md (5-minute guide)
echo    - DEVELOPMENT.md (for developers)
echo.
pause
