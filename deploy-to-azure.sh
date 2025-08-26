#!/bin/bash

echo "🚀 Hughes Lawn AI - Azure Deployment Script"
echo "==========================================="

# Variables
RESOURCE_GROUP="SAXTech-AI"
APP_NAME="hughes-lawn-ai"
LOCATION="eastus2"
PLAN_NAME="hughes-lawn-ai-plan"
DB_NAME="hughes-lawn-ai-db"

# Check if logged in to Azure
echo "📋 Checking Azure login status..."
if ! az account show &>/dev/null; then
    echo "❌ Not logged in to Azure. Please run: az login"
    exit 1
fi

echo "✅ Azure login confirmed"

# Create App Service Plan if it doesn't exist
echo "📦 Creating App Service Plan..."
az appservice plan create \
    --name $PLAN_NAME \
    --resource-group $RESOURCE_GROUP \
    --location $LOCATION \
    --sku B1 \
    --is-linux \
    --output none

echo "✅ App Service Plan ready"

# Create Web App
echo "🌐 Creating Web App..."
az webapp create \
    --name $APP_NAME \
    --resource-group $RESOURCE_GROUP \
    --plan $PLAN_NAME \
    --runtime "PYTHON:3.9" \
    --output none

echo "✅ Web App created"

# Configure App Settings
echo "⚙️  Configuring App Settings..."
az webapp config appsettings set \
    --name $APP_NAME \
    --resource-group $RESOURCE_GROUP \
    --settings \
        ECOWITT_APP_KEY="14CF42F092D6CC8C5421160A37A0417A" \
        ECOWITT_API_KEY="e5f2d6ff-2323-477e-8041-6e284b401b83" \
        ECOWITT_MAC="34:94:54:96:22:F5" \
        RAINBIRD_IP="q0852082.eero.online" \
        RAINBIRD_PIN="886004" \
        RAINBIRD_PORT="71.217.130.52" \
        N8N_WEBHOOK_URL="https://workflows.saxtechnology.com/webhook/hughes-lawn-ai" \
        DATABASE_URL="sqlite:///home/hughes_lawn_ai.db" \
    --output none

echo "✅ App Settings configured"

# Enable CORS
echo "🔧 Enabling CORS..."
az webapp cors add \
    --name $APP_NAME \
    --resource-group $RESOURCE_GROUP \
    --allowed-origins "*" \
    --output none

echo "✅ CORS enabled"

# Deploy code using ZIP deployment
echo "📤 Preparing deployment package..."
zip -r deploy.zip . \
    -x "*.git*" \
    -x "hughes_lawn_env/*" \
    -x "*.log" \
    -x "*.db" \
    -x "__pycache__/*" \
    -x "*.pyc" \
    -x "node_modules/*" \
    -x "deploy.zip"

echo "📤 Deploying to Azure..."
az webapp deployment source config-zip \
    --name $APP_NAME \
    --resource-group $RESOURCE_GROUP \
    --src deploy.zip \
    --output none

echo "✅ Deployment complete"

# Get the app URL
APP_URL=$(az webapp show --name $APP_NAME --resource-group $RESOURCE_GROUP --query defaultHostName -o tsv)

echo ""
echo "=========================================="
echo "✨ Hughes Lawn AI deployed successfully!"
echo "=========================================="
echo ""
echo "🌐 Application URL: https://$APP_URL"
echo "📊 Dashboard: https://$APP_URL"
echo "🚿 RainBird API: https://$APP_URL/api/rainbird"
echo "🪝 Webhook URL: https://$APP_URL/webhook"
echo ""
echo "📝 Next Steps:"
echo "1. Import the n8n workflow (n8n-hughes-lawn-ai-workflow.json)"
echo "2. Update the n8n webhook URL to: https://$APP_URL/webhook"
echo "3. Configure your RainBird Dynamic DNS if needed"
echo "4. Test the system at: https://$APP_URL"
echo ""
echo "🔍 View logs with: az webapp log tail --name $APP_NAME --resource-group $RESOURCE_GROUP"
echo ""

# Clean up
rm -f deploy.zip
