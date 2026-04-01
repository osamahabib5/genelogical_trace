# Azure Container Apps Deployment Script for Genealogy Chatbot
# Usage: .\deploy.ps1 [resource-group] [location] [acr-name] [postgres-connection-string]

param(
    [string]$ResourceGroup = "genealogy-rg",
    [string]$Location = "eastus",
    [string]$AcrName = "genealogyacr",
    [string]$PostgresConnectionString = "postgresql://username:password@server.postgres.database.azure.com/database"
)

Write-Host "Deploying Genealogy Chatbot to Azure Container Apps..." -ForegroundColor Green
Write-Host "Resource Group: $ResourceGroup"
Write-Host "Location: $Location"
Write-Host "ACR Name: $AcrName"
Write-Host "Using existing PostgreSQL instance"

# Check if logged in
try {
    $account = az account show 2>$null | ConvertFrom-Json
} catch {
    Write-Host "Please login to Azure first: az login" -ForegroundColor Red
    exit 1
}

# Create resource group
Write-Host "Creating resource group..."
az group create --name $ResourceGroup --location $Location --output none

# Create ACR
Write-Host "Creating Azure Container Registry..."
az acr create --resource-group $ResourceGroup --name $AcrName --sku Basic --output none

# Login to ACR
Write-Host "Logging into ACR..."
az acr login --name $AcrName

# # Build and push images
# Write-Host "Building and pushing backend image..."
# Set-Location ../app/backend
# # docker build -t "$AcrName.azurecr.io/genealogy-backend:latest"
# # Make sure there is a space and a dot (or path) at the end!
# docker build -t "$ACR_NAME.azurecr.io/genealogy-frontend:latest" ../app/backend
# docker push "$AcrName.azurecr.io/genealogy-backend:latest"

Write-Host "Building and pushing frontend image..."
Set-Location ../frontend
# docker build -t "$AcrName.azurecr.io/genealogy-frontend:latest"
docker build -t "$ACR_NAME.azurecr.io/genealogy-frontend:latest" ../app/frontend
docker push "$AcrName.azurecr.io/genealogy-frontend:latest"

Set-Location ../../deployment

# Create Container Apps environment
Write-Host "Creating Container Apps environment..."
az containerapp env create `
  --name genealogy-env `
  --resource-group $ResourceGroup `
  --location $Location `
  --output none

# Get registry credentials
$acrUsername = az acr credential show --name $AcrName --query username -o tsv
$acrPassword = az acr credential show --name $AcrName --query passwords[0].value -o tsv

# Deploy backend
Write-Host "Deploying backend..."
az containerapp create `
  --name genealogy-backend `
  --resource-group $ResourceGroup `
  --environment genealogy-env `
  --image "$AcrName.azurecr.io/genealogy-backend:latest" `
  --target-port 8000 `
  --ingress external `
  --registry-server "$AcrName.azurecr.io" `
  --registry-username $acrUsername `
  --registry-password $acrPassword `
  --env-vars "DATABASE_URL=$PostgresConnectionString" `
            "OPENAI_API_KEY=$env:OPENAI_API_KEY" `
            "ALLOWED_ORIGINS=https://genealogy-frontend.bluehill-*.eastus.azurecontainerapps.io" `
  --cpu 0.5 `
  --memory 1Gi `
  --output none

# Get backend URL
$backendUrl = az containerapp show --name genealogy-backend --resource-group $ResourceGroup --query properties.configuration.ingress.fqdn -o tsv

# Deploy frontend
Write-Host "Deploying frontend..."
az containerapp create `
  --name genealogy-frontend `
  --resource-group $ResourceGroup `
  --environment genealogy-env `
  --image "$AcrName.azurecr.io/genealogy-frontend:latest" `
  --target-port 3000 `
  --ingress external `
  --registry-server "$AcrName.azurecr.io" `
  --registry-username $acrUsername `
  --registry-password $acrPassword `
  --env-vars "REACT_APP_API_URL=https://$backendUrl/api" `
  --cpu 0.5 `
  --memory 1Gi `
  --output none

# Get frontend URL
$frontendUrl = az containerapp show --name genealogy-frontend --resource-group $ResourceGroup --query properties.configuration.ingress.fqdn -o tsv

Write-Host "Deployment completed!" -ForegroundColor Green
Write-Host "Frontend URL: https://$frontendUrl"
Write-Host "Backend API: https://$backendUrl"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Update ALLOWED_ORIGINS in backend with the actual frontend URL"
Write-Host "2. Ensure your PostgreSQL database has the pgvector extension enabled"
Write-Host "3. Initialize the database by connecting to PostgreSQL and running init.sql"
Write-Host "4. Set your API keys (OPENAI_API_KEY, etc.) as needed"
Write-Host ""
Write-Host "To cleanup: az group delete --name $ResourceGroup --yes"