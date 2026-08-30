# Sterish — Verification API Specification

> REST API for querying skill audit status from the on-chain registry.

Base URL: `http://localhost:8000`

---

## Endpoints

### `GET /check/{skill_id}`

Query the audit status of a single skill by its identifier.

**Path Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `skill_id` | string | Unique skill identifier (e.g. `web-search-tool`) |

**Response 200 — Skill found:**

```json
{
  "skill_id": "web-search-tool",
  "verdict": "SAFE",
  "trust_score": 92,
  "evidence": "https://stellar.expert/testnet/tx/abc...",
  "audit_timestamp": "2026-08-20T14:30:00Z",
  "auditor": "GCBYXEE..."
}
```

| Field | Type | Description |
|---|---|---|
| `skill_id` | string | The queried skill identifier |
| `verdict` | string | One of: `UNAUDITED`, `SAFE`, `DANGEROUS`, `WARNING` |
| `trust_score` | integer | Composite trust score, 0–100 |
| `evidence` | string | URL to audit evidence / transaction on stellar.expert |
| `audit_timestamp` | string | ISO 8601 timestamp of the last audit |
| `auditor` | string | Stellar public key of the auditor who submitted the verdict |

**Response 404 — Skill not registered:**

```json
{
  "detail": "Skill 'xxx' not found"
}
```

---

### `GET /skills`

List all registered skills with pagination.

**Query Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `start` | integer | `0` | Pagination offset |
| `limit` | integer | `20` | Number of results (1–100) |

**Response 200:**

```json
[
  {
    "skill_id": "web-search-tool",
    "verdict": "SAFE",
    "trust_score": 92,
    "versions": ["1.0.0"]
  },
  {
    "skill_id": "file-manager",
    "verdict": "WARNING",
    "trust_score": 64,
    "versions": ["1.2.0", "1.1.0"]
  }
]
```

| Field | Type | Description |
|---|---|---|
| `skill_id` | string | Unique skill identifier |
| `verdict` | string | One of: `UNAUDITED`, `SAFE`, `DANGEROUS`, `WARNING` |
| `trust_score` | integer | Composite trust score, 0–100 |
| `versions` | array of string | All registered versions of this skill |

---

### `GET /health`

Health check endpoint for monitoring and load balancers.

**Response 200:**

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` if service is healthy |
| `version` | string | Current API version |

---

## Error Codes

| Status | Code | Meaning |
|---|---|---|
| 404 | `NOT_FOUND` | Skill ID not registered in the on-chain registry |
| 500 | `INTERNAL` | RPC failure, contract invocation error, or unexpected server error |

All error responses follow this schema:

```json
{
  "detail": "Human-readable error description"
}
```

---

## Notes

- The API reads directly from the Soroban registry contract via Stellar RPC.
- No authentication is required — all data is public on-chain.
- Rate limiting: 100 requests/minute per IP (configurable).