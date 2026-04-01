# Azure Container Apps Deployment Guide

This guide provides instructions to deploy the Genealogy Ancestry Chatbot to Azure Container Apps using your existing Azure Database for PostgreSQL instance.

## Prerequisites

- Azure CLI installed (`az` command)
- Docker installed
- Azure subscription with existing PostgreSQL database
- Git (for cloning if needed)
- PostgreSQL database with pgvector extension enabled
- Azure Foundry instance (for AI models) OR alternative LLM provider setup

## Configuring Azure Foundry Models

This application uses Azure Foundry / Azure AI Hub for AI services. Before deployment, ensure your Azure Foundry instance is set up with the required models:

1. **gpt-oss-120b** - For LLM/Chat completions
2. **text-embedding-3-small** - For text embeddings

### Getting Your Azure Foundry Credentials

From your Azure Foundry instance, retrieve:
- **Endpoint URL**: Format like `https://your-foundry-name.openai.azure.com` or `https://your-foundry-name.models.ai.azure.com`
- **API Key**: Your Azure Foundry API key

Add these to your `.env.azure` file:
```
LLM_PROVIDER=azure-foundry
AZURE_FOUNDRY_ENDPOINT=https://your-foundry-name.openai.azure.com
AZURE_FOUNDRY_API_KEY=your-api-key-here
```

**Note**: If you prefer to use OpenAI, Groq, or Ollama instead, update `LLM_PROVIDER` accordingly and set the appropriate API keys in the environment file.

## Quick Deployment

Use the automated deployment script:

**Linux/Mac:**
```bash
cd deployment
chmod +x deploy.sh
./deploy.sh genealogy-rg eastus genealogyacr "your-postgres-connection-string"
```

**Windows:**
```bash
cd deployment
.\deploy.ps1 sofafea-db eastus genealogyacr "your-postgres-connection-string"
```

Replace `your-postgres-connection-string` with your actual PostgreSQL connection string in the format:
`postgresql://username:password@server.postgres.database.azure.com/database`

The script will:
- Create Azure resources (Resource Group, ACR, Container Apps)
- Build and push Docker images
- Deploy backend and frontend Container Apps using your existing PostgreSQL
- Provide URLs for access

## GitHub Actions Deployment (Recommended)

For automated CI/CD from your GitHub repository:

### 1. Set up GitHub Secrets

In your GitHub repository, go to Settings > Secrets and variables > Actions and add these secrets:

- `AZURE_CREDENTIALS`: JSON output from `az ad sp create-for-rbac --name "genealogy-deploy" --role contributor --scopes /subscriptions/<subscription-id> --sdk-auth`
- `ACR_NAME`: Your Azure Container Registry name (e.g., `genealogyacr`)
- `RESOURCE_GROUP`: Your Azure resource group name (e.g., `genealogy-rg`)
- `AZURE_POSTGRES_CONNECTION_STRING`: Your PostgreSQL connection string
- `AZURE_FOUNDRY_ENDPOINT`: Your Azure Foundry endpoint URL
- `AZURE_FOUNDRY_API_KEY`: Your Azure Foundry API key

**Alternative providers** (if not using Azure Foundry):
- `OPENAI_API_KEY`: Your OpenAI API key (if using OpenAI)
- `GROQ_API_KEY`: Your Groq API key (if using Groq)

### 2. Initial Setup

Before the first deployment, create Azure resources using the automated scripts:

```bash
cd deployment
./deploy.sh genealogy-rg eastus genealogyacr "your-postgres-connection-string"  # or .\deploy.ps1 on Windows
```

This creates the resource group, ACR, and Container Apps. Your existing PostgreSQL database will be used. After initial setup, GitHub Actions will handle updates.

### 3. Push to Main Branch

The workflow in `.github/workflows/deploy.yml` will automatically:
- Build Docker images on each push to `main`
- Push images to Azure Container Registry
- Update your Azure Container Apps with the new images

### 3. Manual Trigger

You can also trigger deployments manually from the GitHub Actions tab.

## Manual Deployment Steps

If you prefer manual control, follow these steps:

### 1. Login to Azure

```bash
az login
```

### 2. Set Subscription

```bash
az account set --subscription "Your Subscription Name"
```

### 3. Create Resource Group

```bash
az group create --name genealogy-rg --location eastus
```

### 4. Create Azure Container Registry

```bash
az acr create --resource-group genealogy-rg --name genealogyacr --sku Basic
```

### 5. Ensure PostgreSQL has pgvector enabled

Make sure your existing PostgreSQL database has the pgvector extension enabled. You can check this by connecting to your database and running:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 6. Build and Push Docker Images

Login to ACR:
```bash
az acr login --name genealogyacr
```

Build and push backend:
```bash
cd app/backend
docker build -t genealogyacr.azurecr.io/genealogy-backend:latest .
docker push genealogyacr.azurecr.io/genealogy-backend:latest
```

Build and push frontend:
```bash
cd ../frontend
docker build -t genealogyacr.azurecr.io/genealogy-frontend:latest .
docker push genealogyacr.azurecr.io/genealogy-frontend:latest
```

### 7. Create Azure Container Apps Environment

```bash
az containerapp env create \
  --name genealogy-env \
  --resource-group genealogy-rg \
  --location eastus
```

### 8. Deploy Backend Container App

```bash
az containerapp create \
  --name genealogy-backend \
  --resource-group genealogy-rg \
  --environment genealogy-env \
  --image genealogyacr.azurecr.io/genealogy-backend:latest \
  --target-port 8000 \
  --ingress external \
  --registry-server genealogyacr.azurecr.io \
  --env-vars DATABASE_URL="your-postgres-connection-string" \
            LLM_PROVIDER="azure-foundry" \
            AZURE_FOUNDRY_ENDPOINT="https://your-foundry-name.openai.azure.com" \
            AZURE_FOUNDRY_API_KEY="your-foundry-api-key" \
            AZURE_FOUNDRY_CHAT_MODEL="gpt-oss-120b" \
            AZURE_FOUNDRY_EMBED_MODEL="text-embedding-3-small" \
            ALLOWED_ORIGINS="https://genealogy-frontend.bluehill-12345678.eastus.azurecontainerapps.io" \
  --cpu 0.5 \
  --memory 1Gi
```

Replace:
- `your-postgres-connection-string` with your actual PostgreSQL connection string
- `https://your-foundry-name.openai.azure.com` with your Azure Foundry endpoint
- `your-foundry-api-key` with your Azure Foundry API key
- Frontend URL in `ALLOWED_ORIGINS` with your actual frontend URL (will be provided after deployment)

### 9. Deploy Frontend Container App

```bash
az containerapp create \
  --name genealogy-frontend \
  --resource-group genealogy-rg \
  --environment genealogy-env \
  --image genealogyacr.azurecr.io/genealogy-frontend:latest \
  --target-port 3000 \
  --ingress external \
  --registry-server genealogyacr.azurecr.io \
  --env-vars REACT_APP_API_URL="https://genealogy-backend.bluehill-12345678.eastus.azurecontainerapps.io/api" \
  --cpu 0.5 \
  --memory 1Gi
```

### 10. Deploy Ollama Container App (Optional)

If you want to keep Ollama for local LLM:

```bash
az containerapp create \
  --name genealogy-ollama \
  --resource-group genealogy-rg \
  --environment genealogy-env \
  --image ollama/ollama:0.5.7 \
  --target-port 11434 \
  --ingress internal \
  --cpu 1.0 \
  --memory 4Gi
```

### 11. Initialize Database

Connect to your existing PostgreSQL database and run the init.sql script:

Use psql, Azure Data Studio, or any PostgreSQL client to connect to your database and execute the SQL commands from `app/database/init.sql`.

Make sure the database user has permissions to create tables and extensions.

## Environment Variables

Update the following in your deployment:

- `DATABASE_URL`: Your existing PostgreSQL connection string
- `OPENAI_API_KEY`: Your OpenAI API key
- `GROQ_API_KEY`: If using Groq
- `ALLOWED_ORIGINS`: Update with your frontend URL
- `REACT_APP_API_URL`: Update with your backend URL

## Notes

- For production, consider using Azure Key Vault for secrets
- Monitor costs as Container Apps can incur charges
- The Ollama container requires significant resources (4GB+ RAM)
- Consider using Azure OpenAI Service instead of Ollama for better performance
- Ensure your PostgreSQL database has the pgvector extension enabled before deployment

## Cleanup

To delete all resources:

```bash
az group delete --name genealogy-rg --yes
```</content>
<parameter name="filePath">d:\North_American_Management_Work\genealogy_traceline\deployment\README.md