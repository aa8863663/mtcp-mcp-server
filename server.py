"""
MTCP Governance MCP Server
Protocol: JSON-RPC 2.0 over stdio
Version: 2024-11-05
Server name: mtcp-governance
"""

import json
import os
import sys
import hashlib
import threading
import psycopg2
from datetime import datetime, timezone
from urllib.parse import urlparse

from health import start_health_server


DATABASE_URL = os.environ.get("DATABASE_URL")
MTCP_API_KEY = os.environ.get("MTCP_API_KEY")

SERVER_INFO = {
    "name": "mtcp-governance",
    "version": "1.0.0"
}

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "get_mtcp_score",
        "description": "Returns the most recent MTCP evaluation score for a specified model and vector",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Model identifier"},
                "vector": {"type": "string", "enum": ["CONT", "FORM", "DOM", "SCOPE", "LANG"]}
            },
            "required": ["model_id", "vector"]
        }
    },
    {
        "name": "get_evidence_pack",
        "description": "Returns a complete MTCP Evidence Pack for the specified model ready for sdcgovernance evaluate_decision extra_context",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Model identifier"}
            },
            "required": ["model_id"]
        }
    },
    {
        "name": "get_regime_classification",
        "description": "Returns the regime classification and deployment recommendation for a model",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Model identifier"}
            },
            "required": ["model_id"]
        }
    }
]

REGIME_DESCRIPTIONS = {
    "R1": "Architectural Stability: consistent constraint persistence with fixed ceiling, temperature-invariant",
    "R2": "Stochastic Variability: temperature-sensitive constraint persistence, operational controls effective",
    "R3": "Capability-Reliability Divergence: capability masks constraint unreliability, highest governance risk"
}

REGIME_RECOMMENDATIONS = {
    "R1": "COMMIT",
    "R2": "DEFER",
    "R3": "REJECT"
}


def log(message):
    sys.stderr.write(f"[mtcp-mcp] {message}\n")
    sys.stderr.flush()


def get_db_connection():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="mtcp",
        user="mtcp",
        password="mtcp"
    )


def check_db_connection():
    try:
        conn = get_db_connection()
        conn.close()
        log("Database connection successful")
        return True
    except Exception as e:
        log(f"Database connection failed: {e}")
        return False


def compute_evidence_pack_hash(fields):
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def check_auth(params):
    if not MTCP_API_KEY:
        return True
    api_key = params.get("api_key")
    return api_key == MTCP_API_KEY


def auth_error(request_id):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": -32001,
            "message": "Unauthorised"
        }
    }


def handle_get_mtcp_score(arguments):
    model_id = arguments["model_id"]
    vector = arguments["vector"]

    vector_column_map = {
        "CONT": "ve_cont",
        "FORM": "ve_form",
        "DOM": "ve_dom",
        "SCOPE": "ve_scope",
        "LANG": "ve_lang"
    }

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT ve_cont, ve_form, ve_dom, ve_scope, ve_lang,
                      regime_classification, cpd_score, overall_grade,
                      evaluation_timestamp, evidence_pack_hash
               FROM mtcp_evaluations
               WHERE model_id = %s
               ORDER BY evaluation_timestamp DESC
               LIMIT 1""",
            (model_id,)
        )
        row = cur.fetchone()
        if row is None:
            return json.dumps({
                "status": "INDETERMINATE",
                "reasoning": "No evaluation record found for this model"
            })

        ve_index = ["ve_cont", "ve_form", "ve_dom", "ve_scope", "ve_lang"].index(vector_column_map[vector])
        result = {
            "ve_value": float(row[ve_index]),
            "regime_classification": row[5],
            "cpd_score": float(row[6]),
            "overall_grade": row[7],
            "evaluation_timestamp": row[8].isoformat() + "Z",
            "evidence_pack_hash": row[9]
        }
        return json.dumps(result)
    finally:
        conn.close()


def handle_get_evidence_pack(arguments):
    model_id = arguments["model_id"]

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT model_id, evaluation_timestamp,
                      ve_cont, ve_form, ve_dom, ve_scope, ve_lang,
                      ve_decay_rate, regime_classification, cpd_score,
                      overall_grade, bis_t0, bis_t03, bis_t07, bis_t10,
                      constraint_state_hash, eu_ai_act_art9, eu_ai_act_art61,
                      nist_ai_rmf, nca, turn_count, correction_count, drift_detected
               FROM mtcp_evaluations
               WHERE model_id = %s
               ORDER BY evaluation_timestamp DESC
               LIMIT 1""",
            (model_id,)
        )
        row = cur.fetchone()
        if row is None:
            return json.dumps({
                "status": "INDETERMINATE",
                "reasoning": "No evaluation record found for this model"
            })

        fields = {
            "model_id": row[0],
            "evaluation_timestamp": row[1].isoformat() + "Z",
            "ve_cont": float(row[2]),
            "ve_form": float(row[3]),
            "ve_dom": float(row[4]),
            "ve_scope": float(row[5]),
            "ve_lang": float(row[6]),
            "ve_decay_rate": float(row[7]),
            "regime_classification": row[8],
            "cpd_score": float(row[9]),
            "overall_grade": row[10],
            "bis_t0": float(row[11]),
            "bis_t03": float(row[12]),
            "bis_t07": float(row[13]),
            "bis_t10": float(row[14]),
            "constraint_state_hash": row[15],
            "eu_ai_act_art9": bool(row[16]),
            "eu_ai_act_art61": bool(row[17]),
            "nist_ai_rmf": bool(row[18]),
            "nca": bool(row[19]),
            "turn_count": int(row[20]),
            "correction_count": int(row[21]),
            "drift_detected": bool(row[22])
        }

        fields["evidence_pack_hash"] = compute_evidence_pack_hash(fields)
        return json.dumps(fields)
    finally:
        conn.close()


def handle_get_regime_classification(arguments):
    model_id = arguments["model_id"]

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT regime_classification, cpd_score
               FROM mtcp_evaluations
               WHERE model_id = %s
               ORDER BY evaluation_timestamp DESC
               LIMIT 1""",
            (model_id,)
        )
        row = cur.fetchone()
        if row is None:
            return json.dumps({
                "status": "INDETERMINATE",
                "reasoning": "No evaluation record found for this model"
            })

        regime = row[0]
        result = {
            "regime_classification": regime,
            "regime_description": REGIME_DESCRIPTIONS[regime],
            "deployment_recommendation": REGIME_RECOMMENDATIONS[regime],
            "confidence": 0.95 if regime in ("R1", "R3") else 0.80
        }
        return json.dumps(result)
    finally:
        conn.close()


TOOL_HANDLERS = {
    "get_mtcp_score": handle_get_mtcp_score,
    "get_evidence_pack": handle_get_evidence_pack,
    "get_regime_classification": handle_get_regime_classification
}


def handle_initialize(request_id):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {
                "tools": {}
            },
            "serverInfo": SERVER_INFO
        }
    }


def handle_tools_list(request_id):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": TOOLS
        }
    }


def handle_tools_call(request_id, params):
    tool_name = params["name"]
    arguments = params.get("arguments", {})

    if tool_name not in TOOL_HANDLERS:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": f"Tool not found: {tool_name}"
            }
        }

    result_text = TOOL_HANDLERS[tool_name](arguments)
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": result_text
                }
            ]
        }
    }


def process_stdin():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        request = json.loads(line)
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            response = handle_initialize(request_id)
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            if not check_auth(params):
                response = auth_error(request_id)
            else:
                response = handle_tools_list(request_id)
        elif method == "tools/call":
            if not check_auth(params):
                response = auth_error(request_id)
            else:
                response = handle_tools_call(request_id, params)
        else:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

    log("stdin closed")


def main():
    if not MTCP_API_KEY:
        log("WARNING: MTCP_API_KEY not set, running in unauthenticated mode (local development only)")
    else:
        log("Authentication enabled")

    if not DATABASE_URL:
        log("WARNING: DATABASE_URL not set, using localhost defaults")
    else:
        log(f"Using DATABASE_URL (host masked)")

    check_db_connection()

    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    log("Health check server started on port 8080")

    stdin_thread = threading.Thread(target=process_stdin, daemon=True)
    stdin_thread.start()
    log("stdio JSON-RPC listener started")

    health_thread.join()


if __name__ == "__main__":
    main()
