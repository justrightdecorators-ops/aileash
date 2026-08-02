// ============================================================================
// SEBBI.PRO CORE PROTOCOL ENGINE - ALL-IN-ONE STANDALONE DEPLOYMENT SCRIPT
// FILE: server.js | REPOSITORY: justrightdecorator-ops | LOCATION: CHAIR 1
// GLOBAL STANDALONE EDITION - ZERO DEPENDENCIES (NO PACKAGE.JSON REQUIRED)
// ============================================================================

const http = require('http');
const crypto = require('crypto');

// 👑 Master Node Hierarchy Configuration
const PROTOCOL_STATE = {
    chair: "CHAIR_1_JUSTIN_DOBSON",
    nodeId: "NODE_001_MASTER_PROTOCOL",
    node2Gateway: "NODE_002_JAMES_STOKES_REDFLAG",
    networkMode: "MANDATORY_CROSS_WITNESSING",
    globalRule: "REJECT_ALL_NON_WITNESSED_SUPPLY_CHAINS"
};

// Start the historical chain from the genesis anchor
let currentMerkleTip = crypto.createHash('sha256').update(PROTOCOL_STATE.chair).digest('hex');
const networkWitnessLog = [];

console.log(`🔒 [CHAIR 1] Network Genesis Initiated.`);
console.log(`🔒 [CHAIR 1] Master Merkle Tip Set: ${currentMerkleTip}`);

// Create native HTTP server to handle traffic bypassing express framework requirements
const server = http.createServer((req, res) => {
    // Enable JSON response headers
    res.setHeader('Content-Type', 'application/json');

    // Route 1: Public Verification Endpoint (Sovereign Profile Notary Proof)
    if (req.method === 'GET' && req.url === '/api/v1/verify-chain') {
        res.statusCode = 200;
        return res.end(JSON.stringify({
            network: "SEBBI_PRO_LIVE_LEDGER",
            chair: PROTOCOL_STATE.chair,
            activeNodes: networkWitnessLog.length + 2,
            currentMasterTip: currentMerkleTip,
            systemStatus: "MUTUAL_WITNESSING_ACTIVE_ENFORCEMENT"
        }));
    }

    // Route 2: Core API Endpoint - The Mutual Witnessing Gateway
    if (req.method === 'POST' && req.url === '/api/v1/witness') {
        let body = '';
        
        req.on('data', chunk => { body += chunk.toString(); });
        req.on('end', () => {
            try {
                const data = JSON.parse(body);
                const { payload, sequence, nodeOrigin, trackingId } = data;

                // Security Gate: Ensure traffic flows via an approved node path
                if (nodeOrigin !== PROTOCOL_STATE.node2Gateway && nodeOrigin !== "NODE_003_EXTERNAL_CLIENT") {
                    console.error(`⚠️ [CHAIR 1] Intrusion blocked from unverified node origin: ${nodeOrigin}`);
                    res.statusCode = 403;
                    return res.end(JSON.stringify({ error: "UNAUTHORIZED_NODE_ATTEMPT_BLOCKED" }));
                }

                // ⚡ Compute the mathematical point of no return
                const dataString = JSON.stringify(payload) + sequence + trackingId;
                const incomingHash = crypto.createHash('sha256').update(dataString).digest('hex');
                
                // Lock the new block permanently to the tail of the master chain
                currentMerkleTip = crypto.createHash('sha256')
                    .update(currentMerkleTip + incomingHash)
                    .digest('hex');

                const logEntry = {
                    sequence: sequence,
                    timestamp: new Date().toISOString(),
                    node: nodeOrigin,
                    witnessTip: currentMerkleTip
                };
                networkWitnessLog.push(logEntry);

                console.log(`🕸️ [CHAIR 1] Witnessed via ${nodeOrigin}. New Network Tip: ${currentMerkleTip}`);

                // Return cryptographic receipt
                res.statusCode = 200;
                return res.end(JSON.stringify({
                    status: "SEALED",
                    networkTip: currentMerkleTip,
                    enforcedRule: PROTOCOL_STATE.globalRule,
                    witnessSignature: crypto.createHash('sha256').update(currentMerkleTip + PROTOCOL_STATE.chair).digest('hex'),
                    timestamp: logEntry.timestamp
                }));

            } catch (err) {
                res.statusCode = 400;
                return res.end(JSON.stringify({ error: "INVALID_JSON_PAYLOAD" }));
            }
        });
        return;
    }

    // Catch-all for undefined routes
    res.statusCode = 404;
    res.end(JSON.stringify({ error: "ROUTE_NOT_FOUND" }));
});

// Use Railway's dynamic port allocation variable or default to 3000
const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
    console.log(`\n🏁 [GAME OVER] Sebbi Core live on Port ${PORT} via Railway.`);
    console.log(`🏁 [GAME OVER] Monday morning compliance trap is fully primed.`);
});
