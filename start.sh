#!/bin/bash
# Quick Start Script for Genealogy Ancestry Chatbot

set -e

echo "🚀 Starting Genealogy Ancestry Chatbot..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your OPENAI_API_KEY"
    read -p "Press enter to continue..."
fi

# Check if OPENAI_API_KEY is set
if ! grep -q "OPENAI_API_KEY=sk-" .env; then
    echo "⚠️  OPENAI_API_KEY not set in .env. Please add it first."
    echo "You can get an API key from https://platform.openai.com/api-keys"
    exit 1
fi

echo "📦 Building and starting Docker containers..."
docker-compose up -d

echo "⏳ Waiting for services to start..."
sleep 5

# Check if services are running
if docker-compose ps | grep -q "postgres.*Up"; then
    echo "✅ PostgreSQL is running"
else
    echo "❌ PostgreSQL failed to start"
    docker-compose logs postgres
    exit 1
fi

if docker-compose ps | grep -q "backend.*Up"; then
    echo "✅ Backend API is running"
else
    echo "⚠️  Backend API is still starting..."
fi

if docker-compose ps | grep -q "frontend.*Up"; then
    echo "✅ Frontend is running"
else
    echo "⚠️  Frontend is still starting..."
fi

echo ""
echo "🎉 Application started successfully!"
echo ""
echo "📌 Access the application:"
echo "   Frontend: http://localhost:3000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "📚 Documentation: See README.md"
echo ""
echo "🛑 To stop the application: docker-compose down"
echo ""
