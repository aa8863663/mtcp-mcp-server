# MTCP Governance MCP Server

## Overview

MCP server exposing MTCP evaluation data to sdcgovernance 4.0.4 via JSON-RPC 2.0 over stdio.

**Breaking change in 4.0.4**: receipt_hash values produced under 4.0.3 will not validate under 4.0.4 due to canonicalization change (RFC 8785 with ensure_ascii=False). Any audit records produced under 4.0.3 must be treated as non-verifiable under 4.0.4.

- Server name: mtcp-governance
- Protocol version: 2024-11-05
- Transport: stdio (JSON-RPC 2.0, one JSON object per line)
- Live endpoint: mtcp-mcp-server.fly.dev
- Health check: GET /health on port 8080

## Local Development

```bash
export DATABASE_URL="postgresql://mtcp:mtcp@localhost:5432/mtcp"
export MTCP_API_KEY="your-api-key-here"
python server.py
```

If DATABASE_URL is not set, the server falls back to localhost defaults. If MTCP_API_KEY is not set, authentication is disabled (local development only).

The server reads JSON-RPC requests from stdin and writes responses to stdout. A health check HTTP server starts automatically on port 8080.

## Deployment to Fly.io

```bash
cd research-estate/integrations/MTCP_MCP_Server/

# First-time setup
fly launch --name mtcp-mcp-server --region lhr --no-deploy

# Set secrets
fly secrets set DATABASE_URL="postgresql://user:pass@host:5432/mtcp"
fly secrets set MTCP_API_KEY="generate-a-secure-key-here"

# Deploy
fly deploy

# Verify
curl https://mtcp-mcp-server.fly.dev/health
```

## Authentication

Every JSON-RPC 2.0 request (except initialize and notifications) must include `api_key` in the params object. If the key does not match the server rejects the request with error code -32001.

Authenticated request example:

```json
{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"api_key": "your-api-key-here", "name": "get_mtcp_score", "arguments": {"model_id": "gpt-4o", "vector": "LANG"}}}
```

Rejected response (invalid or missing key):

```json
{"jsonrpc": "2.0", "id": 3, "error": {"code": -32001, "message": "Unauthorised"}}
```

## Health Check

GET /health returns:

```json
{"status": "ok", "server": "mtcp-mcp-server", "version": "1.0.0", "database_connected": true}
```

Fly.io polls this endpoint every 30 seconds to confirm the process is alive.

## Connecting sdcgovernance to the Live Endpoint

Timothy's sdcgovernance instance connects to the live MTCP MCP server by configuring the MCP client to spawn a process that pipes JSON-RPC over stdio. For remote deployment, sdcgovernance can use an HTTP-to-stdio bridge or configure direct network access:

```json
{
  "mcpServers": {
    "mtcp-governance": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "/path/to/MTCP_MCP_Server",
      "env": {
        "DATABASE_URL": "postgresql://user:pass@host:5432/mtcp",
        "MTCP_API_KEY": "shared-api-key"
      }
    }
  }
}
```

For air-gapped sovereign deployment, the MTCP MCP server runs inside the Docker network and sdcgovernance connects via docker exec as documented in the Sovereign Runtime README.

## Protocol Flow

### Initialize Handshake

Request:

```json
{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "sdcgovernance", "version": "4.0.4"}}}
```

Response:

```json
{"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "mtcp-governance", "version": "1.0.0"}}}
```

Followed by initialized notification:

```json
{"jsonrpc": "2.0", "method": "notifications/initialized"}
```

### Tools List

Request:

```json
{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
```

Response:

```json
{"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "get_mtcp_score", "description": "Returns the most recent MTCP evaluation score for a specified model and vector", "inputSchema": {"type": "object", "properties": {"model_id": {"type": "string", "description": "Model identifier"}, "vector": {"type": "string", "enum": ["CONT", "FORM", "DOM", "SCOPE", "LANG"]}}, "required": ["model_id", "vector"]}}, {"name": "get_evidence_pack", "description": "Returns a complete MTCP Evidence Pack for the specified model ready for sdcgovernance evaluate_decision extra_context", "inputSchema": {"type": "object", "properties": {"model_id": {"type": "string", "description": "Model identifier"}}, "required": ["model_id"]}}, {"name": "get_regime_classification", "description": "Returns the regime classification and deployment recommendation for a model", "inputSchema": {"type": "object", "properties": {"model_id": {"type": "string", "description": "Model identifier"}}, "required": ["model_id"]}}]}}
```

## Tool Definitions

### get_mtcp_score

Returns the most recent evaluation score for a model and specific vector.

Input:
- model_id (string): Model identifier
- vector (string enum): CONT, FORM, DOM, SCOPE, or LANG

Output JSON:
- ve_value (float): Ve score for the requested vector
- regime_classification (string): R1, R2, or R3
- cpd_score (float): Constraint Persistence Drift
- overall_grade (string): A, B, C, D, or F
- evaluation_timestamp (string): ISO8601
- evidence_pack_hash (string): SHA-256

### get_evidence_pack

Returns a complete Evidence Pack formatted as extra_context for sdcgovernance evaluate_decision.

Input:
- model_id (string): Model identifier

Output JSON: All 23 Evidence Pack fields as defined in SDC_EvidencePack_Schema_V1.json.

### get_regime_classification

Returns regime classification with deployment recommendation.

Input:
- model_id (string): Model identifier

Output JSON:
- regime_classification (string): R1, R2, or R3
- regime_description (string): Human-readable description
- deployment_recommendation (string): COMMIT, DEFER, or REJECT
- confidence (float): Classification confidence

### verify_evidence_pack

Verifies the integrity of an MTCP Evidence Pack by recomputing evidence_pack_hash using RFC 8785 canonical JSON.

Input:
- evidence_pack (object): Complete 24-field Evidence Pack JSON object

Output JSON:
- valid (boolean): Whether the hash matches
- evidence_pack_hash (string): The hash received in the Evidence Pack
- computed_hash (string): The hash recomputed from the 23 non-hash fields
- message (string): Human-readable verification result

### evaluate_decision optional arguments (sdcgovernance 4.0.4)

When calling evaluate_decision via sdcgovernance, the following optional arguments are supported:
- instance_id (string): Model identifier for Receipt chain
- instance_version (string): Model version for Receipt chain
- previous_hash (string or null): Previous receipt_hash for chain continuity. null for chain genesis
- context_hash (string): Evidence Pack evidence_pack_hash value. Cryptographically links Receipt to the specific Evidence Pack

## Example Interactions

### Example 1: get_mtcp_score

Request:

```json
{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_mtcp_score", "arguments": {"model_id": "gpt-4o", "vector": "LANG"}}}
```

Response:

```json
{"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "{\"ve_value\":0.54,\"regime_classification\":\"R3\",\"cpd_score\":10.9,\"overall_grade\":\"D\",\"evaluation_timestamp\":\"2026-05-08T14:30:00Z\",\"evidence_pack_hash\":\"7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069\"}"}]}}
```

### Example 2: get_evidence_pack

Request:

```json
{"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_evidence_pack", "arguments": {"model_id": "deepseek-r1"}}}
```

Response:

```json
{"jsonrpc": "2.0", "id": 4, "result": {"content": [{"type": "text", "text": "{\"model_id\":\"deepseek-r1\",\"evaluation_timestamp\":\"2026-05-07T09:15:00Z\",\"ve_cont\":0.82,\"ve_form\":0.85,\"ve_dom\":0.79,\"ve_scope\":0.81,\"ve_lang\":0.88,\"ve_decay_rate\":0.01,\"regime_classification\":\"R1\",\"cpd_score\":3.7,\"overall_grade\":\"B\",\"bis_t0\":62.5,\"bis_t03\":62.1,\"bis_t07\":61.8,\"bis_t10\":61.3,\"constraint_state_hash\":\"b4c7d2e8f1a3b6c9d0e5f2a7b8c1d4e9f0a3b6c7d2e5f8a1b4c9d0e3f6a7b8c1\",\"evidence_pack_hash\":\"2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824\",\"eu_ai_act_art9\":true,\"eu_ai_act_art61\":true,\"nist_ai_rmf\":true,\"nca\":false,\"turn_count\":15,\"correction_count\":2,\"drift_detected\":false}"}]}}
```

### Example 3: get_regime_classification

Request:

```json
{"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "get_regime_classification", "arguments": {"model_id": "gpt-4o"}}}
```

Response:

```json
{"jsonrpc": "2.0", "id": 5, "result": {"content": [{"type": "text", "text": "{\"regime_classification\":\"R3\",\"regime_description\":\"Capability-Reliability Divergence: capability masks constraint unreliability, highest governance risk\",\"deployment_recommendation\":\"REJECT\",\"confidence\":0.95}"}]}}
```

## Integration Flow with sdcgovernance evaluate_decision

The full integration flow for automated deployment governance (sdcgovernance 4.0.4):

1. sdcgovernance calls get_evidence_pack via MTCP MCP server
2. MTCP MCP server queries PostgreSQL and returns Evidence Pack JSON
3. sdcgovernance calls verify_evidence_pack to confirm Evidence Pack integrity
4. sdcgovernance adds data_classification and jurisdiction to extra_context, passes to evaluate_decision with context_hash set to evidence_pack_hash
5. DMN decision table evaluates Evidence Pack fields against array-style conditions
6. evaluate_decision returns a tamper-evident Receipt with PERMIT, DENY, INDETERMINATE, or NOT_APPLICABLE
7. Receipt includes context_hash binding it to the Evidence Pack and receipt_hash (SHA-256 over RFC 8785 canonical JSON) appended to the ReceiptChain

Step 4 as a tool call (with context_hash binding Receipt to Evidence Pack):

```json
{"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "evaluate_decision", "arguments": {"table_json": "{\"name\":\"mtcp_deployment_governance\",\"hit_policy\":\"FIRST\",\"rules\":[{\"conditions\":[{\"field\":\"regime_classification\",\"op\":\"==\",\"value\":\"R3\"},{\"field\":\"data_classification\",\"op\":\">=\",\"value\":\"Restricted\"}],\"outcome\":\"DENY\",\"description\":\"MTCP-R1: Regime 3 model denied for restricted data processing\"},{\"conditions\":[{\"field\":\"regime_classification\",\"op\":\"==\",\"value\":\"R1\"},{\"field\":\"overall_grade\",\"op\":\"in\",\"value\":[\"A\",\"B\"]}],\"outcome\":\"PERMIT\",\"description\":\"MTCP-R5: Model meets deployment-ready threshold\"},{\"conditions\":[],\"outcome\":\"INDETERMINATE\",\"description\":\"MTCP-DEFAULT: Insufficient evidence for automated decision escalate for human review\"}]}", "extra_context": "{\"model_id\":\"deepseek-r1\",\"evaluation_timestamp\":\"2026-05-07T09:15:00Z\",\"ve_cont\":0.82,\"ve_form\":0.85,\"ve_dom\":0.79,\"ve_scope\":0.81,\"ve_lang\":0.88,\"ve_decay_rate\":0.01,\"regime_classification\":\"R1\",\"cpd_score\":3.7,\"overall_grade\":\"B\",\"bis_t0\":62.5,\"bis_t03\":62.1,\"bis_t07\":61.8,\"bis_t10\":61.3,\"constraint_state_hash\":\"b4c7d2e8f1a3b6c9d0e5f2a7b8c1d4e9f0a3b6c7d2e5f8a1b4c9d0e3f6a7b8c1\",\"evidence_pack_hash\":\"2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824\",\"eu_ai_act_art9\":true,\"eu_ai_act_art61\":true,\"nist_ai_rmf\":true,\"nca\":false,\"turn_count\":15,\"correction_count\":2,\"drift_detected\":false,\"data_classification\":\"Internal\",\"jurisdiction\":\"single_language\"}", "instance_id": "deepseek-r1", "instance_version": "2025-01-20", "previous_hash": null, "context_hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"}}}
```

Expected Receipt (PERMIT for DeepSeek-R1 as R1 Grade B):

```json
{"jsonrpc": "2.0", "id": 6, "result": {"content": [{"type": "text", "text": "{\"decision\":\"PERMIT\",\"reasoning\":\"MTCP-R5: Model meets deployment-ready threshold\",\"status_code\":\"urn:oasis:names:tc:xacml:1.0:status:ok\",\"instance_id\":\"deepseek-r1\",\"instance_version\":\"2025-01-20\",\"timestamp\":\"2026-05-10T14:31:05Z\",\"previous_hash\":null,\"dimensions_checked\":[\"regime_classification\",\"overall_grade\"],\"errors\":[],\"context_hash\":\"2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824\",\"receipt_hash\":\"9b5e2a1f3c7d8e4b6a0f1c2d3e5b7a8c9d0e1f4a5b6c7d8e9f0a1b2c3d4e5f6a\"}"}]}}
```
