const express = require('express');
const path = require('path');
const RainBird = require('./patched-rainbird');

const app = express();
const port = 3000;

// Rainbird controller configuration
const CONTROLLER_IP = '192.168.5.17';
const CONTROLLER_PIN = '886004';
const CONTROLLER_PORT = 443;

let rainbird;

// Initialize RainBird connection
async function initRainbird() {
    try {
        rainbird = new RainBird(CONTROLLER_IP, CONTROLLER_PIN);
        rainbird.setDebug(); // Enable debug to see detailed errors
        console.log('✅ RainBird HTTPS controller initialized');
        console.log(`📡 Controller: ${CONTROLLER_IP} (HTTPS)`);
        console.log(`🔑 PIN: ${CONTROLLER_PIN}`);
        return true;
    } catch (error) {
        console.error('❌ Failed to initialize RainBird:', error.message);
        return false;
    }
}

// Helper function to retry requests
async function retryRequest(fn, maxRetries = 2, delay = 1000) {
    for (let i = 0; i < maxRetries; i++) {
        try {
            const result = await fn();
            return result;
        } catch (error) {
            console.log(`❌ Attempt ${i + 1}/${maxRetries} failed:`, error.message);
            if (i === maxRetries - 1) {
                console.log(`🚫 Final attempt failed, throwing error`);
                throw error;
            }
            console.log(`🔄 Retry ${i + 1}/${maxRetries} after ${delay}ms`);
            await new Promise(resolve => setTimeout(resolve, delay));
        }
    }
}

// Middleware
app.use(express.json());
app.use(express.static('public'));

// Serve the main page
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'rainbird-interface.html'));
});

// API endpoints
app.post('/api/start-zone', async (req, res) => {
    try {
        const { zone, duration } = req.body;
        console.log(`🚿 Starting Zone ${zone} for ${duration} minutes`);
        
        const result = await retryRequest(() => rainbird.startZone(parseInt(zone), parseInt(duration)));
        
        res.json({
            success: true,
            message: `Zone ${zone} started for ${duration} minutes`,
            data: result
        });
    } catch (error) {
        console.error('❌ Error starting zone:', error.message);
        res.status(500).json({
            success: false,
            message: 'Failed to start zone',
            error: error.message
        });
    }
});

app.post('/api/stop-zone', async (req, res) => {
    try {
        const { zone } = req.body;
        console.log(`⛔ Stopping Zone ${zone || 'All'}`);
        
        const result = await retryRequest(() => rainbird.stopIrrigation());
        
        res.json({
            success: true,
            message: zone ? `Zone ${zone} stopped` : 'All zones stopped',
            data: result
        });
    } catch (error) {
        console.error('❌ Error stopping zone:', error.message);
        res.status(500).json({
            success: false,
            message: 'Failed to stop zone',
            error: error.message
        });
    }
});

app.get('/api/controller-info', async (req, res) => {
    try {
        console.log('ℹ️ Getting controller information');
        
        // Only get essential info to reduce requests
        const model = await retryRequest(() => rainbird.getModelAndVersion());
        
        const result = {
            model: model,
            connected: true,
            ip: CONTROLLER_IP,
            pin: CONTROLLER_PIN
        };
        
        res.json({
            success: true,
            message: 'Controller info retrieved',
            data: result
        });
    } catch (error) {
        console.error('❌ Error getting controller info:', error.message);
        res.status(500).json({
            success: false,
            message: 'Failed to get controller info',
            error: error.message
        });
    }
});

app.get('/api/zone-status', async (req, res) => {
    try {
        console.log('📊 Getting zone status');
        
        // Only get essential info to reduce connection issues
        const activeZones = await retryRequest(() => rainbird.getActiveZones());
        
        const result = {
            activeZones: activeZones,
            timestamp: new Date().toISOString()
        };
        
        res.json({
            success: true,
            message: 'Zone status retrieved',
            data: result
        });
    } catch (error) {
        console.error('❌ Error getting zone status:', error.message);
        res.status(500).json({
            success: false,
            message: 'Failed to get zone status',
            error: error.message
        });
    }
});

// Start server
async function startServer() {
    const initialized = await initRainbird();
    
    if (!initialized) {
        console.log('⚠️  Warning: RainBird controller not initialized. Some features may not work.');
    }
    
    app.listen(port, () => {
        console.log('');
        console.log('🚀 Rainbird Controller Web App Started!');
        console.log('');
        console.log('🌐 Open your browser and go to:');
        console.log(`   http://localhost:${port}`);
        console.log('');
        console.log('🎯 Features:');
        console.log('   • Start/Stop individual zones');
        console.log('   • Emergency stop all zones');
        console.log('   • View controller information');
        console.log('   • Check zone status');
        console.log('');
        console.log('📡 Controller Settings:');
        console.log(`   IP: ${CONTROLLER_IP}`);
        console.log(`   PIN: ${CONTROLLER_PIN}`);
        console.log('');
        console.log('Press Ctrl+C to stop the server');
        console.log('');
    });
}

startServer();
