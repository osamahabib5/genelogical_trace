@echo off
REM Quick Start Script for Genealogy Ancestry Chatbot (Windows)

echo.
echo 🚀 Starting Genealogy Ancestry Chatbot...
echo.

REM Check if Docker is installed
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker is not installed. Please install Docker Desktop first.
    pause
    exit /b 1
)

REM Check if Docker Compose is installed
docker-compose --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker Compose is not installed. Please update Docker Desktop.
    pause
    exit /b 1
)

REM Create .env if it doesn't exist
if not exist .env (
    echo 📝 Creating .env file from template...
    copy .env.example .env
    echo.
    echo ⚠️  Please edit .env and add your OPENAI_API_KEY
    pause
)

REM Check if OPENAI_API_KEY is set
findstr /M "OPENAI_API_KEY=sk-" .env >nul
if %errorlevel% neq 0 (
    echo.
    echo ⚠️  OPENAI_API_KEY not set in .env. Please add it first.
    echo You can get an API key from https://platform.openai.com/api-keys
    pause
    exit /b 1
)

echo 📦 Building and starting Docker containers...
docker-compose up -d

echo.
echo ⏳ Waiting for services to start...
timeout /t 5

echo.
echo 🎉 Application started successfully!
echo.
echo 📌 Access the application:
echo    Frontend: http://localhost:3000
echo    API Docs: http://localhost:8000/docs
echo.
echo 📚 Documentation: See README.md
echo.
echo 🛑 To stop the application: docker-compose down
echo.
pause
