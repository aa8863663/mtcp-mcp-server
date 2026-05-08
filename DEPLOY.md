# Deployment Guide

## Prerequisites

- Fly.io CLI installed (`brew install flyctl`)
- Fly.io account authenticated (`fly auth login`)
- PostgreSQL database accessible from Fly.io (e.g. Fly Postgres or external)
- API key generated for MTCP_API_KEY

## First-Time Setup

```bash
cd ~/Projects/mtcp-mcp-server

# Create the Fly.io app (already configured in fly.toml)
fly launch --name mtcp-mcp-server --region lhr --no-deploy

# Set secrets
fly secrets set DATABASE_URL="postgresql://user:password@host:5432/mtcp"
fly secrets set MTCP_API_KEY="your-secure-api-key"

# Deploy
fly deploy
```

## Subsequent Deploys

```bash
cd ~/Projects/mtcp-mcp-server
fly deploy
```

## Verify Deployment

```bash
curl https://mtcp-mcp-server.fly.dev/health
```

Expected response:

```json
{"status": "ok", "server": "mtcp-mcp-server", "version": "1.0.0", "database_connected": true}
```

## Secrets Management

```bash
# List current secrets
fly secrets list

# Update database URL
fly secrets set DATABASE_URL="postgresql://new-connection-string"

# Rotate API key
fly secrets set MTCP_API_KEY="new-key-value"
```

## Scaling

The app runs with 1 machine minimum (configured in fly.toml). To scale:

```bash
# Add machines in another region
fly scale count 2 --region lhr

# Check status
fly status
```

## Logs

```bash
# Stream live logs
fly logs

# Check recent startup
fly logs --instance latest
```

## Rollback

```bash
# List recent deployments
fly releases

# Rollback to previous version
fly deploy --image registry.fly.io/mtcp-mcp-server:previous-tag
```

## Connecting sdcgovernance

Timothy Cook's sdcgovernance instance connects by configuring the MCP client with the shared MTCP_API_KEY. Every JSON-RPC request must include the api_key in params:

```json
{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"api_key": "shared-key", "name": "get_evidence_pack", "arguments": {"model_id": "gpt-4o"}}}
```

## Database Requirements

The server expects a PostgreSQL database with the `mtcp_evaluations` table containing all Evidence Pack fields. This is the same database used by the MTCP evaluation pipeline at mtcp.live.
