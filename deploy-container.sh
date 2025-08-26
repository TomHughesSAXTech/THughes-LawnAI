#!/bin/bash

echo "🚀 Hughes Lawn AI - Azure Container Deployment"
echo "=============================================="

# Configuration
RESOURCE_GROUP="SAXTech-AI"
CONTAINER_NAME="hughes-lawn-ai"
LOCATION="eastus2"
REGISTRY_NAME="hugheslawnai"
IMAGE_NAME="hughes-lawn-ai"
DNS_NAME="hughes-lawn-ai"

# Check Azure login
echo "📋 Checking Azure login..."
if ! az account show &>/dev/null; then
    echo "❌ Not logged in to Azure. Please run: az login"
    exit 1
fi

echo "✅ Logged in to Azure"

# Create container registry if it doesn't exist
echo "📦 Setting up Container Registry..."
if ! az acr show --name $REGISTRY_NAME --resource-group $RESOURCE_GROUP &>/dev/null; then
    echo "Creating container registry..."
    az acr create \
        --name $REGISTRY_NAME \
        --resource-group $RESOURCE_GROUP \
        --location $LOCATION \
        --sku Basic \
        --admin-enabled true \
        --output none
    echo "✅ Container registry created"
else
    echo "✅ Container registry exists"
fi

# Get registry credentials
echo "🔑 Getting registry credentials..."
REGISTRY_USERNAME=$(az acr credential show --name $REGISTRY_NAME --query username -o tsv)
REGISTRY_PASSWORD=$(az acr credential show --name $REGISTRY_NAME --query passwords[0].value -o tsv)
REGISTRY_SERVER="${REGISTRY_NAME}.azurecr.io"

# Build Docker image locally
echo "🔨 Building Docker image..."
docker build -t $IMAGE_NAME:latest .

# Tag image for Azure registry
echo "🏷️  Tagging image..."
docker tag $IMAGE_NAME:latest $REGISTRY_SERVER/$IMAGE_NAME:latest

# Login to Azure Container Registry
echo "🔐 Logging in to container registry..."
echo $REGISTRY_PASSWORD | docker login $REGISTRY_SERVER -u $REGISTRY_USERNAME --password-stdin

# Push image to registry
echo "📤 Pushing image to registry..."
docker push $REGISTRY_SERVER/$IMAGE_NAME:latest

# Create container instance
echo "🚀 Creating container instance..."
az container create \
    --name $CONTAINER_NAME \
    --resource-group $RESOURCE_GROUP \
    --location $LOCATION \
    --image $REGISTRY_SERVER/$IMAGE_NAME:latest \
    --registry-login-server $REGISTRY_SERVER \
    --registry-username $REGISTRY_USERNAME \
    --registry-password $REGISTRY_PASSWORD \
    --dns-name-label $DNS_NAME \
    --ports 8000 \
    --cpu 1 \
    --memory 1 \
    --restart-policy Always \
    --environment-variables \
        ECOWITT_APP_KEY="14CF42F092D6CC8C5421160A37A0417A" \
        ECOWITT_API_KEY="e5f2d6ff-2323-477e-8041-6e284b401b83" \
        ECOWITT_MAC="34:94:54:96:22:F5" \
        RAINBIRD_IP="q0852082.eero.online" \
        RAINBIRD_PIN="886004" \
        N8N_WEBHOOK_URL="https://workflows.saxtechnology.com/webhook/hughes-lawn-ai" \
    --output none

# Get container URL
echo "🔍 Getting container URL..."
CONTAINER_URL=$(az container show \
    --name $CONTAINER_NAME \
    --resource-group $RESOURCE_GROUP \
    --query ipAddress.fqdn \
    --output tsv)

echo ""
echo "=============================================="
echo "✨ Hughes Lawn AI deployed successfully!"
echo "=============================================="
echo ""
echo "🌐 Application URL: http://$CONTAINER_URL:8000"
echo "📊 Dashboard: http://$CONTAINER_URL:8000"
echo "🚿 API Status: http://$CONTAINER_URL:8000/api/status"
echo "🪝 Webhook URL: http://$CONTAINER_URL:8000/webhook"
echo ""
echo "📝 n8n Integration:"
echo "1. Import the workflow: n8n-hughes-lawn-ai-workflow.json"
echo "2. Update webhook URL to: http://$CONTAINER_URL:8000/webhook"
echo ""
echo "🔍 View logs:"
echo "az container logs --name $CONTAINER_NAME --resource-group $RESOURCE_GROUP"
echo ""
echo "🔄 Restart container:"
echo "az container restart --name $CONTAINER_NAME --resource-group $RESOURCE_GROUP"
echo ""
