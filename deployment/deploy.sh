#!/bin/bash

# Azure Container Apps Deployment Script for Genealogy Chatbot
# Usage: ./deploy.sh [resource-group] [location] [acr-name] [postgres-connection-string]

set -e

# Default values
RESOURCE_GROUP=${1:-genealogy-rg}
LOCATION=${2:-eastus}
ACR_NAME=${3:-genealogyacr}
POSTGRES_CONNECTION_STRING=${4:-"postgresql://username:password@server.postgres.database.azure.com/database"}

echo "Deploying Genealogy Chatbot to Azure Container Apps..."
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "ACR Name: $ACR_NAME"
echo "Using existing PostgreSQL instance"

# Login check
if ! az account show > /dev/null 2>&1; then
    echo "Please login to Azure first: az login"
    exit 1
fi

# Create resource group
echo "Creating resource group..."
az group create --name $RESOURCE_GROUP --location $LOCATION --output none

# Create ACR
echo "Creating Azure Container Registry..."
az acr create --resource-group $RESOURCE_GROUP --name $ACR_NAME --sku Basic --output none

# Login to ACR
echo "Logging into ACR..."
az acr login --name $ACR_NAME

# Build and push images
echo "Building and pushing backend image..."
cd ../app/backend
docker build -t $ACR_NAME.azurecr.io/genealogy-backend:latest .
docker push $ACR_NAME.azurecr.io/genealogy-backend:latest

echo "Building and pushing frontend image..."
cd ../frontend
docker build -t $ACR_NAME.azurecr.io/genealogy-frontend:latest .
docker push $ACR_NAME.azurecr.io/genealogy-frontend:latest

cd ../../deployment

# Create Container Apps environment
echo "Creating Container Apps environment..."
az containerapp env create \
  --name genealogy-env \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --output none

# Get registry credentials
ACR_USERNAME=$(az acr credential show --name $ACR_NAME --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query passwords[0].value -o tsv)

# Deploy backend
echo "Deploying backend..."
az containerapp create \
  --name genealogy-backend \
  --resource-group $RESOURCE_GROUP \
  --environment genealogy-env \
  --image $ACR_NAME.azurecr.io/genealogy-backend:latest \
  --target-port 8000 \
  --ingress external \
  --registry-server $ACR_NAME.azurecr.io \
  --registry-username $ACR_USERNAME \
  --registry-password $ACR_PASSWORD \
  --env-vars DATABASE_URL="$POSTGRES_CONNECTION_STRING" \
            OPENAI_API_KEY="$OPENAI_API_KEY" \
            ALLOWED_ORIGINS="https://genealogy-frontend.bluehill-*.eastus.azurecontainerapps.io" \
  --cpu 0.5 \
  --memory 1Gi \
  --output none

# Get backend URL
BACKEND_URL=$(az containerapp show --name genealogy-backend --resource-group $RESOURCE_GROUP --query properties.configuration.ingress.fqdn -o tsv)

# Deploy frontend
echo "Deploying frontend..."
az containerapp create \
  --name genealogy-frontend \
  --resource-group $RESOURCE_GROUP \
  --environment genealogy-env \
  --image $ACR_NAME.azurecr.io/genealogy-frontend:latest \
  --target-port 3000 \
  --ingress external \
  --registry-server $ACR_NAME.azurecr.io \
  --registry-username $ACR_USERNAME \
  --registry-password $ACR_PASSWORD \
  --env-vars REACT_APP_API_URL="https://$BACKEND_URL/api" \
  --cpu 0.5 \
  --memory 1Gi \
  --output none

# Get frontend URL
FRONTEND_URL=$(az containerapp show --name genealogy-frontend --resource-group $RESOURCE_GROUP --query properties.configuration.ingress.fqdn -o tsv)

echo "Deployment completed!"
echo "Frontend URL: https://$FRONTEND_URL"
echo "Backend API: https://$BACKEND_URL"
echo ""
echo "Next steps:"
echo "1. Update ALLOWED_ORIGINS in backend with the actual frontend URL"
echo "2. Ensure your PostgreSQL database has the pgvector extension enabled"
echo "3. Initialize the database by connecting to PostgreSQL and running init.sql"
echo "4. Set your API keys (OPENAI_API_KEY, etc.) as needed"
echo ""
echo "To cleanup: az group delete --name $RESOURCE_GROUP --yes"</content>
<parameter name="filePath">d:\North_American_Management_Work\genealogy_traceline\deployment\deploy.sh