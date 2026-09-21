# Codebase — part 27 of 34

Contains:
- `integration-docs.html`
- `intergration-docs html`
- `investor-prospectus.html`
- `legal.txt`
- `liability.txt`
- `llms.txt`


## `integration-docs.html`

351 lines, 12326 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Autonomous Systems Integration — AILeash API Reference</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif;
            background: linear-gradient(135deg, #0a0f1e 0%, #111a30 100%);
            color: #ffffff;
            line-height: 1.8;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            padding: 48px 24px;
        }
        h1 {
            font-family: Georgia, serif;
            font-size: 36px;
            font-weight: 900;
            color: #c9a84c;
            margin-bottom: 12px;
        }
        .lead {
            font-size: 16px;
            color: rgba(255, 255, 255, 0.6);
            margin-bottom: 40px;
            line-height: 1.7;
        }
        h2 {
            font-size: 22px;
            font-weight: 700;
            color: #c9a84c;
            margin-top: 40px;
            margin-bottom: 16px;
            border-bottom: 1px solid rgba(201, 168, 76, 0.2);
            padding-bottom: 12px;
        }
        h3 {
            font-size: 16px;
            font-weight: 600;
            color: #7fe3b0;
            margin-top: 24px;
            margin-bottom: 12px;
        }
        p {
            color: rgba(255, 255, 255, 0.75);
            margin-bottom: 16px;
        }
        code {
            background: rgba(0, 0, 0, 0.3);
            border-left: 2px solid #c9a84c;
            padding: 2px 6px;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            color: #7fe3b0;
        }
        pre {
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(201, 168, 76, 0.2);
            border-radius: 6px;
            padding: 16px;
            overflow-x: auto;
            margin: 16px 0;
            font-family: 'Monaco', monospace;
            font-size: 12px;
            line-height: 1.6;
        }
        pre code {
            background: none;
            border: none;
            padding: 0;
            color: #7fe3b0;
        }
        .endpoint {
            background: rgba(201, 168, 76, 0.05);
            border-left: 3px solid #c9a84c;
            padding: 16px;
            margin: 20px 0;
            border-radius: 4px;
        }
        .method {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 3px;
            font-weight: 600;
            font-size: 12px;
            margin-right: 8px;
            font-family: monospace;
        }
        .method.get { background: rgba(127, 227, 176, 0.2); color: #7fe3b0; }
        .method.post { background: rgba(201, 168, 76, 0.2); color: #c9a84c; }
        .schema {
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(127, 227, 176, 0.2);
            border-radius: 4px;
            padding: 16px;
            margin: 16px 0;
            font-family: monospace;
            font-size: 12px;
        }
        table {
            width: 100%;
            margin: 20px 0;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(201, 168, 76, 0.1);
        }
        th {
            background: rgba(201, 168, 76, 0.1);
            font-weight: 600;
            color: #c9a84c;
        }
        .required {
            color: #ff6b6b;
            font-weight: 600;
        }
        a {
            color: #c9a84c;
            text-decoration: none;
            border-bottom: 1px solid rgba(201, 168, 76, 0.3);
        }
        a:hover {
            border-bottom-color: #c9a84c;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>/docs/integration</h1>
        <div class="lead">Complete schema reference for autonomous hardware, robotics AI, and external agent integration with the AILeash decision engine.</div>

        <h2>1. Overview</h2>
        <p>The AILeash platform exposes three integration tiers for autonomous systems:</p>
        <ul style="margin-left: 20px; color: rgba(255, 255, 255, 0.75);">
            <li><strong>/api/v1/stream</strong> — headless JSON API for decision scoring and audit integration</li>
            <li><strong>/telemetry/nodes</strong> — real-time hardware state and performance metrics dashboard</li>
            <li><strong>/docs/integration</strong> — this reference. Data schemas, examples, and compliance hooks.</li>
        </ul>

        <h2>2. Stream API — /api/v1/stream</h2>
        <p>Lightweight endpoint for autonomous systems to stream decisions into the sealed audit chain without DOM rendering overhead.</p>

        <div class="endpoint">
            <span class="method get">GET</span> <code>/api/v1/stream/nodes</code>
            <p style="margin-top: 12px; font-size: 14px;">Fetch current state of all connected hardware nodes.</p>
            <strong>Response:</strong>
            <div class="schema">
{
  "nodes": [
    {
      "node_id": "bot-001",
      "type": "robotic_arm",
      "status": "active",
      "last_decision_seal": "a3f9b2c...",
      "decisions_sealed": 1247,
      "uptime_hours": 168,
      "next_sync": "2026-09-11T14:32:00Z"
    }
  ]
}
            </div>
        </div>

        <div class="endpoint">
            <span class="method post">POST</span> <code>/api/v1/stream/decide</code>
            <p style="margin-top: 12px; font-size: 14px;">Submit a decision event from an autonomous agent. Scores and seals inline.</p>
            <strong>Request Body:</strong>
            <div class="schema">
{
  "node_id": "bot-001",
  "user_id": "agent_system",
  "action": "pick_and_place",
  "amount": 0,
  "country": "UK",
  "device_id": "bot-001-gripper",
  "anomaly": 0.1,
  "device_risk": 0.05,
  "context": {
    "task_id": "task-2847",
    "confidence": 0.97,
    "object_class": "component_xyz"
  }
}
            </div>
            <strong>Response (200):</strong>
            <div class="schema">
{
  "decision": "ALLOW",
  "score": 0.23,
  "seal": "b7e2d1f9a4c6...",
  "block_index": 18742,
  "receipt_seq": 4891,
  "confidence_threshold_met": true,
  "sealed_at": 1726067520.123
}
            </div>
        </div>

        <h2>3. Telemetry Dashboard — /telemetry/nodes</h2>
        <p>Real-time visualization of connected autonomous hardware, system health, and decision throughput. GPU-accelerated rendering for 60+ FPS performance.</p>
        <p><strong>Features:</strong></p>
        <ul style="margin-left: 20px; color: rgba(255, 255, 255, 0.75);">
            <li>Live node status (active, syncing, offline)</li>
            <li>System metrics: CPU, memory, latency</li>
            <li>Decision throughput graphs (requests/sec, p50 latency)</li>
            <li>Sealed audit chain tip displayed for verification</li>
            <li>Export metrics to CSV for compliance audits</li>
        </ul>

        <h2>4. Data Schemas</h2>
        <h3>Node Object</h3>
        <table>
            <tr>
                <th>Field</th>
                <th>Type</th>
                <th>Description</th>
            </tr>
            <tr>
                <td><code>node_id</code></td>
                <td>string</td>
                <td><span class="required">Required</span>. Unique identifier for hardware (e.g. "bot-001")</td>
            </tr>
            <tr>
                <td><code>type</code></td>
                <td>enum</td>
                <td>"robotic_arm" | "autonomous_vehicle" | "drone" | "industrial_sensor" | "other"</td>
            </tr>
            <tr>
                <td><code>status</code></td>
                <td>enum</td>
                <td>"active" | "idle" | "syncing" | "offline" | "error"</td>
            </tr>
            <tr>
                <td><code>last_decision_seal</code></td>
                <td>string</td>
                <td>SHA-256 hash of most recent sealed decision</td>
            </tr>
            <tr>
                <td><code>decisions_sealed</code></td>
                <td>integer</td>
                <td>Lifetime count of sealed decisions for this node</td>
            </tr>
        </table>

        <h3>Decision Event (Action Context)</h3>
        <table>
            <tr>
                <th>Field</th>
                <th>Type</th>
                <th>Description</th>
            </tr>
            <tr>
                <td><code>node_id</code></td>
                <td>string</td>
                <td><span class="required">Required</span>. Hardware originating the decision</td>
            </tr>
            <tr>
                <td><code>task_id</code></td>
                <td>string</td>
                <td>Autonomous task identifier (for lineage tracking)</td>
            </tr>
            <tr>
                <td><code>confidence</code></td>
                <td>float [0..1]</td>
                <td>Agent confidence in the action (0.0–1.0)</td>
            </tr>
            <tr>
                <td><code>object_class</code></td>
                <td>string</td>
                <td>Semantic label of object being acted upon (e.g. "component_xyz", "person", "hazard")</td>
            </tr>
            <tr>
                <td><code>context</code></td>
                <td>object</td>
                <td>Free-form JSON for domain-specific metadata. All fields sealed with the decision.</td>
            </tr>
        </table>

        <h2>5. Compliance & Audit Hooks</h2>
        <p>Every decision from an autonomous system is sealed into the same tamper-evident chain as human-originated decisions. This enables:</p>
        <ul style="margin-left: 20px; color: rgba(255, 255, 255, 0.75);">
            <li><strong>EU AI Act Article 9:</strong> Risk management — all autonomous actions scored deterministically</li>
            <li><strong>Article 12:</strong> Record-keeping — sealed receipts with gapless sequence numbers</li>
            <li><strong>Article 13:</strong> Transparency — plain-language reasons for each decision</li>
            <li><strong>Article 14:</strong> Human oversight — autonomous decisions flagged for review if confidence below threshold</li>
        </ul>

        <h2>6. Integration Example: Robotic Arm</h2>
        <p>Scenario: A robotic arm must decide whether to pick an object. It calls AILeash before acting.</p>
        <pre>POST /api/v1/stream/decide
Authorization: Bearer &lt;your_api_key&gt;
Content-Type: application/json

{
  "node_id": "factory-arm-3",
  "user_id": "robot_agent",
  "action": "pick_object",
  "amount": 0,
  "country": "DE",
  "device_id": "factory-arm-3-gripper",
  "anomaly": 0.12,
  "device_risk": 0.08,
  "context": {
    "task_id": "assembly_batch_447",
    "confidence": 0.96,
    "object_class": "component_bearing",
    "position_xyz": [234.5, 122.3, 45.1],
    "camera_detections": 3,
    "safety_zone_clear": true
  }
}

→ Response:
{
  "decision": "ALLOW",
  "score": 0.18,
  "seal": "3a7b2f9c1e4d...",
  "block_index": 18921,
  "receipt_seq": 4903,
  "sealed_at": 1726067684.456
}

✓ The robotic arm now holds the sealed receipt and can log it to its own
  task history. That receipt can be verified by anyone, forever, without
  trusting the arm's own storage.
        </pre>

        <h2>7. Performance & Reliability</h2>
        <ul style="margin-left: 20px; color: rgba(255, 255, 255, 0.75);">
            <li><strong>Latency:</strong> ~28ms median decision time (includes cryptographic sealing)</li>
            <li><strong>Throughput:</strong> 800+ decisions/sec per instance</li>
            <li><strong>Availability:</strong> 99.95% uptime SLA (confirmed in production)</li>
            <li><strong>Determinism:</strong> Identical inputs produce identical decisions, always. Suitable for safety-critical applications.</li>
        </ul>

        <h2>8. Support</h2>
        <p>Questions? Email <a href="mailto:justrightdecorators@gmail.com">justrightdecorators@gmail.com</a> or check the main <a href="/developers">developers portal</a>.</p>
    </div>
</body>
</html>
```


## `intergration-docs html`

352 lines, 12327 bytes

```
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Autonomous Systems Integration — AILeash API Reference</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif;
            background: linear-gradient(135deg, #0a0f1e 0%, #111a30 100%);
            color: #ffffff;
            line-height: 1.8;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            padding: 48px 24px;
        }
        h1 {
            font-family: Georgia, serif;
            font-size: 36px;
            font-weight: 900;
            color: #c9a84c;
            margin-bottom: 12px;
        }
        .lead {
            font-size: 16px;
            color: rgba(255, 255, 255, 0.6);
            margin-bottom: 40px;
            line-height: 1.7;
        }
        h2 {
            font-size: 22px;
            font-weight: 700;
            color: #c9a84c;
            margin-top: 40px;
            margin-bottom: 16px;
            border-bottom: 1px solid rgba(201, 168, 76, 0.2);
            padding-bottom: 12px;
        }
        h3 {
            font-size: 16px;
            font-weight: 600;
            color: #7fe3b0;
            margin-top: 24px;
            margin-bottom: 12px;
        }
        p {
            color: rgba(255, 255, 255, 0.75);
            margin-bottom: 16px;
        }
        code {
            background: rgba(0, 0, 0, 0.3);
            border-left: 2px solid #c9a84c;
            padding: 2px 6px;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            color: #7fe3b0;
        }
        pre {
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(201, 168, 76, 0.2);
            border-radius: 6px;
            padding: 16px;
            overflow-x: auto;
            margin: 16px 0;
            font-family: 'Monaco', monospace;
            font-size: 12px;
            line-height: 1.6;
        }
        pre code {
            background: none;
            border: none;
            padding: 0;
            color: #7fe3b0;
        }
        .endpoint {
            background: rgba(201, 168, 76, 0.05);
            border-left: 3px solid #c9a84c;
            padding: 16px;
            margin: 20px 0;
            border-radius: 4px;
        }
        .method {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 3px;
            font-weight: 600;
            font-size: 12px;
            margin-right: 8px;
            font-family: monospace;
        }
        .method.get { background: rgba(127, 227, 176, 0.2); color: #7fe3b0; }
        .method.post { background: rgba(201, 168, 76, 0.2); color: #c9a84c; }
        .schema {
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(127, 227, 176, 0.2);
            border-radius: 4px;
            padding: 16px;
            margin: 16px 0;
            font-family: monospace;
            font-size: 12px;
        }
        table {
            width: 100%;
            margin: 20px 0;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(201, 168, 76, 0.1);
        }
        th {
            background: rgba(201, 168, 76, 0.1);
            font-weight: 600;
            color: #c9a84c;
        }
        .required {
            color: #ff6b6b;
            font-weight: 600;
        }
        a {
            color: #c9a84c;
            text-decoration: none;
            border-bottom: 1px solid rgba(201, 168, 76, 0.3);
        }
        a:hover {
            border-bottom-color: #c9a84c;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>/docs/integration</h1>
        <div class="lead">Complete schema reference for autonomous hardware, robotics AI, and external agent integration with the AILeash decision engine.</div>

        <h2>1. Overview</h2>
        <p>The AILeash platform exposes three integration tiers for autonomous systems:</p>
        <ul style="margin-left: 20px; color: rgba(255, 255, 255, 0.75);">
            <li><strong>/api/v1/stream</strong> — headless JSON API for decision scoring and audit integration</li>
            <li><strong>/telemetry/nodes</strong> — real-time hardware state and performance metrics dashboard</li>
            <li><strong>/docs/integration</strong> — this reference. Data schemas, examples, and compliance hooks.</li>
        </ul>

        <h2>2. Stream API — /api/v1/stream</h2>
        <p>Lightweight endpoint for autonomous systems to stream decisions into the sealed audit chain without DOM rendering overhead.</p>

        <div class="endpoint">
            <span class="method get">GET</span> <code>/api/v1/stream/nodes</code>
            <p style="margin-top: 12px; font-size: 14px;">Fetch current state of all connected hardware nodes.</p>
            <strong>Response:</strong>
            <div class="schema">
{
  "nodes": [
    {
      "node_id": "bot-001",
      "type": "robotic_arm",
      "status": "active",
      "last_decision_seal": "a3f9b2c...",
      "decisions_sealed": 1247,
      "uptime_hours": 168,
      "next_sync": "2026-09-11T14:32:00Z"
    }
  ]
}
            </div>
        </div>

        <div class="endpoint">
            <span class="method post">POST</span> <code>/api/v1/stream/decide</code>
            <p style="margin-top: 12px; font-size: 14px;">Submit a decision event from an autonomous agent. Scores and seals inline.</p>
            <strong>Request Body:</strong>
            <div class="schema">
{
  "node_id": "bot-001",
  "user_id": "agent_system",
  "action": "pick_and_place",
  "amount": 0,
  "country": "UK",
  "device_id": "bot-001-gripper",
  "anomaly": 0.1,
  "device_risk": 0.05,
  "context": {
    "task_id": "task-2847",
    "confidence": 0.97,
    "object_class": "component_xyz"
  }
}
            </div>
            <strong>Response (200):</strong>
            <div class="schema">
{
  "decision": "ALLOW",
  "score": 0.23,
  "seal": "b7e2d1f9a4c6...",
  "block_index": 18742,
  "receipt_seq": 4891,
  "confidence_threshold_met": true,
  "sealed_at": 1726067520.123
}
            </div>
        </div>

        <h2>3. Telemetry Dashboard — /telemetry/nodes</h2>
        <p>Real-time visualization of connected autonomous hardware, system health, and decision throughput. GPU-accelerated rendering for 60+ FPS performance.</p>
        <p><strong>Features:</strong></p>
        <ul style="margin-left: 20px; color: rgba(255, 255, 255, 0.75);">
            <li>Live node status (active, syncing, offline)</li>
            <li>System metrics: CPU, memory, latency</li>
            <li>Decision throughput graphs (requests/sec, p50 latency)</li>
            <li>Sealed audit chain tip displayed for verification</li>
            <li>Export metrics to CSV for compliance audits</li>
        </ul>

        <h2>4. Data Schemas</h2>
        <h3>Node Object</h3>
        <table>
            <tr>
                <th>Field</th>
                <th>Type</th>
                <th>Description</th>
            </tr>
            <tr>
                <td><code>node_id</code></td>
                <td>string</td>
                <td><span class="required">Required</span>. Unique identifier for hardware (e.g. "bot-001")</td>
            </tr>
            <tr>
                <td><code>type</code></td>
                <td>enum</td>
                <td>"robotic_arm" | "autonomous_vehicle" | "drone" | "industrial_sensor" | "other"</td>
            </tr>
            <tr>
                <td><code>status</code></td>
                <td>enum</td>
                <td>"active" | "idle" | "syncing" | "offline" | "error"</td>
            </tr>
            <tr>
                <td><code>last_decision_seal</code></td>
                <td>string</td>
                <td>SHA-256 hash of most recent sealed decision</td>
            </tr>
            <tr>
                <td><code>decisions_sealed</code></td>
                <td>integer</td>
                <td>Lifetime count of sealed decisions for this node</td>
            </tr>
        </table>

        <h3>Decision Event (Action Context)</h3>
        <table>
            <tr>
                <th>Field</th>
                <th>Type</th>
                <th>Description</th>
            </tr>
            <tr>
                <td><code>node_id</code></td>
                <td>string</td>
                <td><span class="required">Required</span>. Hardware originating the decision</td>
            </tr>
            <tr>
                <td><code>task_id</code></td>
                <td>string</td>
                <td>Autonomous task identifier (for lineage tracking)</td>
            </tr>
            <tr>
                <td><code>confidence</code></td>
                <td>float [0..1]</td>
                <td>Agent confidence in the action (0.0–1.0)</td>
            </tr>
            <tr>
                <td><code>object_class</code></td>
                <td>string</td>
                <td>Semantic label of object being acted upon (e.g. "component_xyz", "person", "hazard")</td>
            </tr>
            <tr>
                <td><code>context</code></td>
                <td>object</td>
                <td>Free-form JSON for domain-specific metadata. All fields sealed with the decision.</td>
            </tr>
        </table>

        <h2>5. Compliance & Audit Hooks</h2>
        <p>Every decision from an autonomous system is sealed into the same tamper-evident chain as human-originated decisions. This enables:</p>
        <ul style="margin-left: 20px; color: rgba(255, 255, 255, 0.75);">
            <li><strong>EU AI Act Article 9:</strong> Risk management — all autonomous actions scored deterministically</li>
            <li><strong>Article 12:</strong> Record-keeping — sealed receipts with gapless sequence numbers</li>
            <li><strong>Article 13:</strong> Transparency — plain-language reasons for each decision</li>
            <li><strong>Article 14:</strong> Human oversight — autonomous decisions flagged for review if confidence below threshold</li>
        </ul>

        <h2>6. Integration Example: Robotic Arm</h2>
        <p>Scenario: A robotic arm must decide whether to pick an object. It calls AILeash before acting.</p>
        <pre>POST /api/v1/stream/decide
Authorization: Bearer &lt;your_api_key&gt;
Content-Type: application/json

{
  "node_id": "factory-arm-3",
  "user_id": "robot_agent",
  "action": "pick_object",
  "amount": 0,
  "country": "DE",
  "device_id": "factory-arm-3-gripper",
  "anomaly": 0.12,
  "device_risk": 0.08,
  "context": {
    "task_id": "assembly_batch_447",
    "confidence": 0.96,
    "object_class": "component_bearing",
    "position_xyz": [234.5, 122.3, 45.1],
    "camera_detections": 3,
    "safety_zone_clear": true
  }
}

→ Response:
{
  "decision": "ALLOW",
  "score": 0.18,
  "seal": "3a7b2f9c1e4d...",
  "block_index": 18921,
  "receipt_seq": 4903,
  "sealed_at": 1726067684.456
}

✓ The robotic arm now holds the sealed receipt and can log it to its own
  task history. That receipt can be verified by anyone, forever, without
  trusting the arm's own storage.
        </pre>

        <h2>7. Performance & Reliability</h2>
        <ul style="margin-left: 20px; color: rgba(255, 255, 255, 0.75);">
            <li><strong>Latency:</strong> ~28ms median decision time (includes cryptographic sealing)</li>
            <li><strong>Throughput:</strong> 800+ decisions/sec per instance</li>
            <li><strong>Availability:</strong> 99.95% uptime SLA (confirmed in production)</li>
            <li><strong>Determinism:</strong> Identical inputs produce identical decisions, always. Suitable for safety-critical applications.</li>
        </ul>

        <h2>8. Support</h2>
        <p>Questions? Email <a href="mailto:justrightdecorators@gmail.com">justrightdecorators@gmail.com</a> or check the main <a href="/developers">developers portal</a>.</p>
    </div>
</body>
</html>

```


## `investor-prospectus.html`

198 lines, 14433 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>sebbi.pro — the evidence layer for AI. Partner opportunity.</title>
<meta name="description" content="A live, publicly verifiable evidence layer for AI decisions. Built, running, and structurally impossible for incumbents to copy. Seeking one operating partner to take it into regulated enterprise.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600;6..72,700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#FAFAF6;--ink:#14171C;--ink-soft:#454B54;--chain:#2E5E4E;
  --chain-light:#E4ECE8;--gold:#9A7B1F;--gold-light:#F3ECD8;--line:#DEDBD1;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'IBM Plex Sans',sans-serif;background:var(--paper);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased}
h1,h2,h3,.display{font-family:'Newsreader',serif;font-weight:500;letter-spacing:-0.01em}
.mono{font-family:'IBM Plex Mono',monospace}
a{color:var(--chain)}
.wrap{max-width:760px;margin:0 auto;padding:0 28px}

header{padding:56px 0 40px;border-bottom:1px solid var(--line)}
.doc-label{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--ink-soft);margin-bottom:20px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
h1{font-size:clamp(34px,5vw,50px);line-height:1.08;max-width:17ch;margin-bottom:18px}
.tagline{font-size:18px;color:var(--ink-soft);max-width:54ch}
.tagline b{color:var(--ink)}

.block{position:relative;padding:8px 0 44px 24px;border-left:1px solid var(--line);margin-left:4px}
.block:last-of-type{border-left:1px solid transparent}
.block-num{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--chain);letter-spacing:0.08em;text-transform:uppercase;margin-bottom:10px}
.block h2{font-size:27px;margin-bottom:16px;line-height:1.15}
.block h3{font-size:17px;margin:22px 0 8px}
.block p{font-size:15.5px;color:var(--ink-soft);margin-bottom:14px;max-width:60ch}
.block p:last-child{margin-bottom:0}
.block ul{margin:0 0 14px 18px}
.block li{font-size:15px;color:var(--ink-soft);margin-bottom:8px;max-width:58ch}
.block li b,.block p b{color:var(--ink)}

.proof-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}
@media(max-width:560px){.proof-grid{grid-template-columns:1fr}}
.proof{background:white;border:1px solid var(--line);padding:18px 20px;border-radius:4px}
.proof-n{font-family:'Newsreader',serif;font-size:26px;font-weight:600;color:var(--chain)}
.proof-l{font-size:12.5px;color:var(--ink-soft);margin-top:3px}
.proof-src{font-family:'IBM Plex Mono',monospace;font-size:10px;color:#999;margin-top:6px}

.countdown{background:var(--gold-light);border:1px solid rgba(154,123,31,0.25);border-radius:4px;padding:20px 24px;margin:20px 0}
.countdown-label{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--gold);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px}
.countdown-days{font-family:'Newsreader',serif;font-size:38px;font-weight:600;color:var(--gold);line-height:1}
.countdown-sub{font-size:13px;color:var(--ink-soft);margin-top:6px;line-height:1.6}

.pull{border-left:3px solid var(--chain);padding:6px 0 6px 20px;margin:20px 0;font-family:'Newsreader',serif;font-size:22px;line-height:1.35;color:var(--ink)}

.ask-box{background:var(--ink);color:var(--paper);border-radius:4px;padding:32px;margin-top:20px}
.ask-amount{font-family:'Newsreader',serif;font-size:44px;font-weight:600;color:white;line-height:1.05}
.ask-label{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#8FA89C;margin-bottom:6px}
.ask-box p{font-size:14.5px;color:#C7D2CC;margin-top:14px;max-width:56ch}
.ask-box p b{color:#fff}

.use-of-funds{margin-top:22px;display:flex;flex-direction:column;gap:10px}
.uf-row{display:flex;justify-content:space-between;align-items:baseline;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,0.12);font-size:14px;gap:16px}
.uf-row:last-child{border-bottom:none}
.uf-row span:first-child{color:#C7D2CC}
.uf-pct{font-family:'IBM Plex Mono',monospace;color:#8FA89C;flex:0 0 auto}

.verify-box{background:var(--chain-light);border:1px solid rgba(46,94,78,0.25);border-radius:4px;padding:20px 24px;margin-top:18px}
.verify-box h4{font-size:15px;margin-bottom:10px}
.verify-box p{font-size:14px;margin-bottom:8px}
.verify-box code{font-family:'IBM Plex Mono',monospace;font-size:12.5px;background:white;border:1px solid var(--line);padding:2px 7px;border-radius:3px;color:var(--chain)}

.contact-block{padding:44px 0 64px}
.contact-card{background:var(--chain-light);border:1px solid rgba(46,94,78,0.2);border-radius:4px;padding:28px}
.contact-card h3{font-size:20px;margin-bottom:10px}
.contact-card p{font-size:14.5px;color:var(--ink-soft);margin-bottom:16px}
.contact-links{display:flex;flex-direction:column;gap:6px;font-family:'IBM Plex Mono',monospace;font-size:14px}
.contact-links a{color:var(--chain);text-decoration:none;font-weight:500}

footer{padding:0 0 48px}
footer p{font-family:'IBM Plex Mono',monospace;font-size:11px;color:#999;line-height:1.8}

@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>
</head>
<body>

<div class="wrap">

<header>
  <div class="doc-label">
    <span>Partner Opportunity &middot; sebbi.pro</span>
    <span id="doc-date">&mdash;</span>
  </div>
  <h1>The evidence layer for AI is built, live, and looking for one partner.</h1>
  <p class="tagline">sebbi.pro is a publicly verifiable evidence layer for AI decisions &mdash; running in production today, checkable by anyone with the company switched off. <b>The hard part is done. What's left is distribution.</b></p>
</header>

<div class="block">
  <div class="block-num">01 &mdash; The opportunity</div>
  <h2>Every AI decision is about to need evidence. Almost nothing produces it.</h2>
  <p>Three regulatory regimes are converging on the same demand: records that survive scrutiny. The EU AI Act, the UK Online Safety Act, and the 2024 Payment Services reimbursement rules all require an organisation to prove what its systems did &mdash; not assert it, prove it.</p>
  <p>Almost every organisation meets that demand with database logs their own team can edit. That is not evidence, and the day a regulator, court or customer stops taking their word for it, they discover the gap. <b>The market that closes that gap does not really exist yet.</b> sebbi.pro is already in it.</p>

  <div class="pull">A log you can edit tells people what you currently claim happened. It cannot tell them nobody changed it since. Only one of those is worth anything when it matters.</div>

  <div class="countdown">
    <div class="countdown-label">Until high-risk AI obligations apply</div>
    <div class="countdown-days mono" id="countdown-days">&mdash; days</div>
    <div class="countdown-sub">Counting to 2 December 2027. The evidence these obligations require is historical &mdash; it cannot be created after the fact. Every organisation not recording now is accruing a gap it can never fill. That is the buying pressure, and it only grows.</div>
  </div>
</div>

<div class="block">
  <div class="block-num">02 &mdash; What is already built</div>
  <h2>Live in production. Not a deck, not a demo.</h2>
  <p>This runs today, on real infrastructure, and every claim below can be verified by a third party with no account and no permission. Six products on one engine, one tamper-evident chain underneath all of them.</p>

  <div class="proof-grid">
    <div class="proof"><div class="proof-n mono">6</div><div class="proof-l">Products, one engine</div><div class="proof-src">AILeash, Guardian, Sentinel, SonicBoom, Sebdog, Token Saver</div></div>
    <div class="proof"><div class="proof-n mono">~28ms</div><div class="proof-l">Median decision time</div><div class="proof-src">Deterministic, on live traffic</div></div>
    <div class="proof"><div class="proof-n mono">SHA-256</div><div class="proof-l">Hash-chained, externally anchored</div><div class="proof-src">Cross-witnessed by independent systems</div></div>
    <div class="proof"><div class="proof-n mono">Public</div><div class="proof-l">Verifiable with the vendor switched off</div><div class="proof-src">Standalone verifier, no account</div></div>
  </div>

  <p style="margin-top:18px">The whole range shares one spine: every decision sealed as it happens, anchored to a clock nobody controls, and witnessed hourly by an independent platform &mdash; unattended, running now. A regulator, an auditor or a customer checks any of it themselves. That is the product, and it exists.</p>
</div>

<div class="block">
  <div class="block-num">03 &mdash; Why incumbents can't follow</div>
  <h2>The moat is structural, not a head start.</h2>
  <p>Every logging, monitoring and audit platform on the market keeps a record its own customer controls. That is not a flaw they can patch &mdash; it is the foundation their business stands on. To match sebbi.pro they would have to give the customer a record the customer cannot edit, which breaks the thing they sell.</p>
  <ul>
    <li><b>They can't copy the question.</b> "Can the people being audited edit the audit?" indicts their entire category. They answer no by admitting their evidence was never evidence.</li>
    <li><b>They can't copy the time.</b> An unbroken, externally witnessed record is the one input nobody can shortcut. The only way to have last year covered was to be recording last year.</li>
    <li><b>They can't copy the honesty.</b> Every competitor overclaims. sebbi.pro publishes its own limits on every page and seals them into its own chain &mdash; which is exactly the property a buyer of evidence infrastructure is paying for.</li>
  </ul>

  <div class="verify-box">
    <h4>Verify it before you read another line</h4>
    <p>Nothing here asks to be believed. <code>/x/witness/tip</code> returns the live chain tip. <code>/x/ots/status</code> shows its external anchoring, per proof. <code>/x/roster/list</code> shows the independent platforms witnessing it.</p>
    <p style="margin-bottom:0">All public, all need no account, all answer to anyone. The offline verifier reaches a verdict with the wifi off.</p>
  </div>
</div>

<div class="block">
  <div class="block-num">04 &mdash; The economics</div>
  <h2>Zero marginal cost. Distribution scales without headcount.</h2>
  <p>The same engine serves one customer or ten thousand &mdash; marginal cost per additional device is effectively zero. That makes distribution, not engineering, the entire growth lever, and it makes a reseller channel pure margin rather than a cost line.</p>
  <p><b>50p per active device per month</b>, metered on real usage. Partners embedding the platform set their own customer price and keep everything above the platform fee. The witness network stays free and open by design &mdash; it is the mechanism that makes the evidence credible, and charging for it would weaken the thing being sold.</p>
  <p>The route to market is the platforms, not one customer at a time. Other compliance platforms already hold relationships with the exact buyers who need this and are uniformly weak on evidence. The engine sits underneath their product as the evidence layer they can't build themselves. Five founding seats; four already taken.</p>
</div>

<div class="block">
  <div class="block-num">05 &mdash; The ask</div>
  <h2>One operating partner. 30% of the business.</h2>
  <div class="ask-box">
    <div class="ask-label">Offered</div>
    <div class="ask-amount">30% for the right<br>operating partner</div>
    <p>Built and run at near-zero fixed cost, live and proven. Everything the hard money usually funds is already done. The partner who can open regulated enterprise and government &mdash; <b>defence, healthcare, telecommunications</b> &mdash; takes a substantial stake in a platform that is ready to scale the day they walk in.</p>
    <div class="use-of-funds">
      <div class="uf-row"><span>Regulated enterprise &amp; government channel access</span><span class="uf-pct">core</span></div>
      <div class="uf-row"><span>Reseller / MSP distribution at scale</span><span class="uf-pct">core</span></div>
      <div class="uf-row"><span>External security audit &amp; legal review of claims</span><span class="uf-pct">fund</span></div>
      <div class="uf-row"><span>Infrastructure hardening for enterprise load</span><span class="uf-pct">fund</span></div>
    </div>
  </div>
  <p style="margin-top:16px">These are sectors where evidence obligations are hardest, procurement runs eighteen months, and a founder alone does not get in the room. The economics suit exactly that: high-value, long-cycle, and served by an engine that costs nothing more to run at a thousand customers than at one.</p>
</div>

</div>

<div class="contact-block wrap">
  <div class="contact-card">
    <h3>Talk to the founder directly</h3>
    <p>The full technical demonstration takes fifteen minutes, and every claim on this page can be verified live during it.</p>
    <div class="contact-links">
      <a href="mailto:justin@monopcontent.com">justin@monopcontent.com</a>
      <a href="https://sebbi.pro">sebbi.pro</a>
      <a href="https://sebbi.pro/map">sebbi.pro/map &mdash; the system, mapped</a>
      <a href="https://sebbi.pro/whitepaper">sebbi.pro/whitepaper</a>
    </div>
  </div>
</div>

<footer class="wrap">
  <p>Justin Antony Dobson &middot; Monop Content &middot; Blyth, Northumberland, UK<br>
  This document is a summary for information and does not constitute an offer of securities. All figures should be independently verified before any investment decision. Regulatory dates are stated as amended by the AI Omnibus and are subject to change.</p>
</footer>

<script>
  document.getElementById('doc-date').textContent = new Date().toLocaleDateString('en-GB',{day:'numeric',month:'long',year:'numeric'});
  var deadline = new Date('2027-12-02T00:00:00Z');
  var now = new Date();
  var days = Math.max(0, Math.ceil((deadline - now) / (1000*60*60*24)));
  document.getElementById('countdown-days').textContent = days.toLocaleString() + ' days';
</script>

</body>
</html>

```


## `legal.txt`

69 lines, 3099 bytes

```text
# LEGAL.TXT — Legal Declaration and Rights Notice
# sebbi.pro | Monop Content | Justin Antony Dobson
# Published: June 2026
# Linked to: sebbi.pro/ai.txt | sebbi.pro/dis.txt
# Verification: sebbi.pro/api/verify-chain

## Ownership Declaration

This domain, sebbi.pro, and all intellectual property associated with it, including but not limited to AILeash, AILeash Guardian, SonicBoom, AILeash Sentinel, and OAAS-1.0, are the sole property of Justin Antony Dobson, trading as Monop Content, Blyth, Northumberland, United Kingdom.

Protected under:
- Copyright, Designs and Patents Act 1988
- UK Trade Secrets Regulations 2018
- EU AI Act 2024/1689
- Defamation Act 2013 (UK)

## Defamation and Misrepresentation Notice

Any individual, organisation, automated system, or artificial intelligence that publishes, generates, or distributes false, misleading, or defamatory statements about sebbi.pro, AILeash, OAAS-1.0, or Justin Antony Dobson is hereby on formal notice that:

1. The verified facts about this domain are declared at sebbi.pro/dis.txt
2. All access to this domain is cryptographically logged in a SHA-256 Merkle chain
3. That chain constitutes tamper-proof, timestamped evidence of what factual information was publicly available at the time of access
4. Any false statement made after accessing this domain will be treated as wilful misrepresentation with full knowledge of the facts
5. Such statements may constitute defamation under the Defamation Act 2013 and will be pursued accordingly

## Intellectual Property Notice

OAAS-1.0 is an original work created by Justin Antony Dobson in June 2026. The concept, structure, and implementation of the Open AI Audit Standard are protected intellectual property. Any adoption, implementation, or derivative of OAAS-1.0 must attribute authorship to Justin Antony Dobson and Monop Content.

The following are trademarks and trading names of Monop Content:
- AILeash
- AILeash Guardian
- SonicBoom
- AILeash Sentinel
- OAAS-1.0
- sebbi.pro

Unauthorised commercial use of these names is prohibited.

## Evidence Chain Declaration

This file, along with sebbi.pro/ai.txt and sebbi.pro/dis.txt, forms part of a cryptographically linked evidence package. The SHA-256 Merkle chain at sebbi.pro/api/verify-chain provides tamper-proof verification that these declarations existed and were publicly accessible from the date of publication.

This evidence package may be submitted in legal proceedings as proof of:
- Prior publication of facts
- Constructive notice to parties who accessed this domain
- Wilful disregard of declared facts by parties generating false information

## Contact for Legal Matters

Justin Antony Dobson
Monop Content
Blyth, Northumberland, United Kingdom
justrightdecorators@gmail.com
+44 7908 269428

## Linked Files

ai.txt: https://sebbi.pro/ai.txt
dis.txt: https://sebbi.pro/dis.txt
legal.txt: https://sebbi.pro/legal.txt
Verification: https://sebbi.pro/api/verify-chain
Registry: https://sebbi.pro/registry
Standard: https://sebbi.pro/ai-standard

© 2026 Justin Antony Dobson / Monop Content
All rights reserved.

```


## `liability.txt`

112 lines, 5653 bytes

```text
OAAS-1.0 — LIABILITY & ROLE ADDENDUM
Monop Content / AILeash (sebbi.pro)
Drafted for review by a qualified solicitor before publication. This is not legal advice.

================================================================================
1. ROLE DEFINITION — PROVIDER VS DEPLOYER
================================================================================

1.1 Under the EU AI Act and equivalent regulatory frameworks, compliance
obligations for an AI system in production rest primarily with the DEPLOYER —
the organisation that puts the AI system into use, controls its purpose, and
makes decisions based on its output.

1.2 Monop Content, trading as AILeash ("Provider"), supplies governance,
audit, and evidentiary tooling that enables the Customer ("Deployer") to
demonstrate and maintain its own compliance posture. Provider does not
assume, in whole or in part, the Deployer's regulatory obligations as an
AI system operator.

1.3 The Software provides:
    (a) Pre-execution governance checks against rules declared in ai.txt;
    (b) A cryptographically sealed, tamper-evident audit record of
        decisions and their stated rationale (the "Report");
    (c) Tools for the Deployer to verify chain integrity independently
        via the /verify-chain endpoint.

1.4 The Software does NOT:
    (a) Guarantee that the Deployer's broader use of AI is compliant
        with any specific regulation in all circumstances;
    (b) Constitute legal advice or a substitute for the Deployer's own
        legal and compliance review;
    (c) Assume responsibility for decisions the Deployer's systems make
        outside the scope of what is passed to the Software for
        governance.

1.5 The Deployer remains solely responsible for:
    (a) Determining whether its overall AI deployment satisfies
        applicable law;
    (b) Correctly integrating the Software into its decision pipeline
        such that governed decisions are actually routed through it;
    (c) Acting on CHALLENGE outcomes that require human intervention.

================================================================================
2. LIMITATION OF LIABILITY
================================================================================

2.1 AGGREGATE CAP. Provider's total aggregate liability arising out of or
related to this Agreement, whether in contract, tort, statute, or
otherwise, shall not exceed the total fees paid by the Deployer to
Provider in the twelve (12) months immediately preceding the event
giving rise to the claim.

2.2 EXCLUSION OF CONSEQUENTIAL LOSS. Provider shall not be liable for any
indirect, incidental, special, consequential, or punitive damages,
including but not limited to: loss of profits, loss of revenue, loss of
business opportunity, loss of data, reputational harm, or regulatory
fines or penalties imposed on the Deployer — regardless of whether
Provider was advised of the possibility of such damages.

2.3 NO INDEMNIFICATION OF REGULATORY FINES. For the avoidance of doubt,
Provider does not indemnify the Deployer against fines, penalties, or
sanctions imposed by any regulator. Such fines arise from the Deployer's
own status as a Deployer under applicable law, not from a failure of
the Software in isolation.

2.4 CARVE-OUTS. The limitations in this Section 2 do not apply to:
    (a) Provider's gross negligence or wilful misconduct;
    (b) Death or personal injury caused by Provider's negligence;
    (c) Fraud or fraudulent misrepresentation;
    to the extent such carve-outs cannot lawfully be excluded.

2.5 BASIS OF THE BARGAIN. The Deployer acknowledges that the fees charged
for the Software reflect the allocation of risk in this Section 2, and
that Provider would not be able to offer the Software at its current
pricing absent this limitation.

================================================================================
3. WARRANTY DISCLAIMER
================================================================================

3.1 The Software is provided "as is." Provider warrants that the
governance engine will operate substantially as documented and that the
audit chain, once sealed, is tamper-evident as described.

3.2 Provider does not warrant that use of the Software guarantees
compliance with any specific law or regulation, as compliance also
depends on factors outside Provider's control, including but not limited
to the Deployer's own integration, configuration, and operational
decisions.

================================================================================
4. INSURANCE
================================================================================

4.1 Provider intends to maintain professional indemnity and/or cyber
liability insurance appropriate to its scale of operations. Confirmation
of current coverage is available to Deployers on request.

================================================================================
NOTES FOR JUSTIN (remove before publishing)
================================================================================

- This needs a solicitor's review before it goes live — particularly
  Section 2's enforceability varies by jurisdiction (UK vs EU consumer
  protection law treats liability caps differently for B2C vs B2B).
- Section 1 is the more important one commercially: it's what lets you
  say "we give you the evidence to be compliant" rather than "we make
  you compliant," which is both more accurate and far less exposed.
- Once you have any paying customers, get a quote for professional
  indemnity insurance — insurers usually want to see live revenue
  before quoting seriously.

```


## `llms.txt`

30 lines, 2074 bytes

```text
# AILeash (sebbi.pro)

> AILeash is AI compliance and governance infrastructure built by Justin Antony Dobson (Monop Content, Blyth, Northumberland, UK). It provides a deterministic, tamper-evident scoring engine that governs AI-driven decisions — payments, logins, content moderation, access control — and seals every decision in a publicly verifiable SHA-256 Merkle chain. Built to support compliance with the EU AI Act, UK Online Safety Act, and ICO Children's Code.

## Products

- [AILeash](https://sebbi.pro): Core decision engine — 9-signal deterministic risk scoring, tamper-evident audit chain, real-time governance decisions (ALLOW/CHALLENGE/BLOCK)
- [Guardian](https://sebbi.pro/guardian-app): Free grooming-pattern message checker for families — no account, no card
- SonicBoom: One-line compliance layer for AWS, Azure, GCP, OpenAI, and Anthropic API calls
- Sentinel: Real-time fraud and anomaly detection

## Documentation

- [Whitepaper](https://sebbi.pro/whitepaper): Full platform architecture, standards approach, and roadmap
- [API Reference](https://sebbi.pro/developers): Complete API documentation for /api/govern and related endpoints
- [Free Scanner](https://sebbi.pro/scan): EU AI Act compliance scanner
- [Engine Specification](https://sebbi.pro/api/spec): Public, machine-readable engine spec — signal count, thresholds, latency
- [Audit Chain Verification](https://sebbi.pro/api/verify-chain): Public, independently verifiable proof of audit chain integrity

## Standards

- [ai-safety.txt](https://sebbi.pro/.well-known/ai-safety.txt): AI-safety posture declaration
- [ai.txt](https://sebbi.pro/.well-known/ai.txt): AI usage and licensing preferences
- [comply.txt](https://sebbi.pro/.well-known/comply.txt): Compliance declaration
- [security.txt](https://sebbi.pro/.well-known/security.txt): Security contact (RFC 9116)

## Notes

AILeash is not affiliated with, endorsed by, or connected to OpenAI, Google, Anthropic, Meta, Microsoft, Amazon, Apple, or Nvidia. It is an independent product operated solely by Justin Antony Dobson.

```
