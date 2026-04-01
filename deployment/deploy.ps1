# Azure Container Apps Deployment Script for Genealogy Chatbot
# Usage: .\deploy.ps1 [resource-group] [location] [acr-name] [postgres-connection-string]

param(
    [string]$ResourceGroup = "sofafea-db",
    [string]$Location = "eastus",
    [string]$AcrName = "genealogyacr",
    [string]$PostgresConnectionString = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Host "Deploying Genealogy Chatbot to Azure Container Apps..." -ForegroundColor Green
Write-Host "Resource Group: $ResourceGroup"
Write-Host "Location: $Location"
Write-Host "ACR Name: $AcrName"

# 1. Ensure Registry Admin is enabled
Write-Host "Ensuring ACR Admin is enabled..." -ForegroundColor Cyan
az acr update -n $AcrName --admin-enabled true --output none

# 2. Build and Push Backend
Write-Host "Building and pushing backend image..." -ForegroundColor Cyan
$BackendPath = Join-Path $ScriptDir "../app/backend"
if (Test-Path $BackendPath) {
    docker build -t "$AcrName.azurecr.io/genealogy-backend:latest" $BackendPath
    docker push "$AcrName.azurecr.io/genealogy-backend:latest"
} else {
    Write-Host "Error: Backend path not found at $BackendPath" -ForegroundColor Red ; exit 1
}

# 3. Build and Push Frontend
Write-Host "Building and pushing frontend image..." -ForegroundColor Cyan
$FrontendPath = Join-Path $ScriptDir "../app/frontend"
if (Test-Path $FrontendPath) {
    docker build -t "$AcrName.azurecr.io/genealogy-frontend:latest" $FrontendPath
    docker push "$AcrName.azurecr.io/genealogy-frontend:latest"
} else {
    Write-Host "Error: Frontend path not found at $FrontendPath" -ForegroundColor Red ; exit 1
}

# 4. Create/Update Environment
Write-Host "Ensuring Container Apps environment exists..." -ForegroundColor Cyan
az containerapp env create `
  --name genealogy-env `
  --resource-group $ResourceGroup `
  --location $Location `
  --output none

# 5. Get registry credentials
$acrUsername = az acr credential show --name $AcrName --query username -o tsv
$acrPassword = az acr credential show --name $AcrName --query "passwords[0].value" -o tsv

# 6. Deploy backend
Write-Host "Deploying backend app..." -ForegroundColor Cyan
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
  --cpu 0.5 --memory 1.0Gi --output none

$backendUrl = az containerapp show --name genealogy-backend --resource-group $ResourceGroup --query properties.configuration.ingress.fqdn -o tsv

# 7. Deploy frontend
Write-Host "Deploying frontend app..." -ForegroundColor Cyan
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
  --env-vars "REACT_APP_API_URL=https://$backendUrl" `
  --cpu 0.5 --memory 1.0Gi --output none

$frontendUrl = az containerapp show --name genealogy-frontend --resource-group $ResourceGroup --query properties.configuration.ingress.fqdn -o tsv

Write-Host "`nDeployment Successful!" -ForegroundColor Green
Write-Host "Frontend: https://$frontendUrl"
Write-Host "Backend:  https://$backendUrl"