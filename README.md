# ProcureLens - RFP Vendor Evaluation Agent

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Sentence Transformers](https://img.shields.io/badge/Sentence--Transformers-Embeddings-5B4BDB)](https://www.sbert.net/)
[![Groq](https://img.shields.io/badge/Groq-Grounded%20Assistant-F55036)](https://groq.com/)
[![CI](https://github.com/Nour-Elrouby/rfp-vendor-evaluation-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Nour-Elrouby/rfp-vendor-evaluation-agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

ProcureLens is a secure, evidence-led platform for comparing vendor proposals
against RFP requirements. It extracts proposal content, matches each requirement
to supporting evidence, produces reproducible scores, ranks vendors, and keeps
an auditable record of every evaluation.

Scoring, ranking, and audit verification run locally using sentence embeddings.
Groq is reserved for the RFP assistant, where only locally shortlisted passages
are sent to the language model. This hybrid design reduces token use and limits
the proposal content shared with an external inference service.

> [!IMPORTANT]
> ProcureLens is decision-support software. Its evidence scores do not constitute
> legal, compliance, security, or procurement approval. A qualified reviewer
> should validate the matched evidence before making a purchasing decision.

## Interface

### Decision dashboard

<p align="center">
  <img src="docs/images/dashboard-overview.png" alt="ProcureLens decision dashboard" width="100%">
</p>

### Evaluation workspace

<p align="center">
  <img src="docs/images/dashboard-workspace.png" alt="ProcureLens proposal evaluation workspace" width="100%">
</p>

## Core capabilities

- Extracts text from PDF, DOCX, and XLSX proposals
- Scores every RFP criterion against its strongest proposal evidence
- Combines dense cosine similarity with lexical overlap
- Returns similarity, hybrid relevance, calibrated score, and matched evidence
- Ranks validated vendor results without LLM calls
- Recomputes scores independently for audit consistency
- Answers RFP questions using local retrieval plus grounded Groq generation
- Stores SHA-256 document fingerprints instead of full proposal text
- Provides bounded, newest-first audit pagination
- Includes a responsive light/dark web dashboard

## Production safeguards

- Optional API-key authentication locally; mandatory in production
- Constant-time credential comparison and trusted-host enforcement
- Request, upload, text, ranking, pagination, and concurrency limits
- Per-process rate limiting
- PDF/DOCX/XLSX signature validation
- Content Security Policy and standard security headers
- Sanitized external-service and unexpected-error responses
- Liveness and readiness endpoints
- Fail-fast production configuration validation
- Non-root Docker image, CI tests, dependency audit, and Dependabot

## Architecture

```text
Proposal file
    |
    v
Secure upload validation
    |
    v
PDF / DOCX / XLSX extraction
    |
    v
Local sentence embeddings
    |
    +--> Hybrid criterion-to-evidence scoring
    |        |
    |        +--> Deterministic ranking
    |        +--> Independent consistency check
    |        `--> JSONL audit record
    |
    `--> Local RFP passage retrieval
             |
             `--> Shortlisted evidence only --> Groq answer
```

Uploaded files are held temporarily during extraction and then deleted. The
default audit record contains the criteria, evidence excerpts, scores,
reasoning, consistency status, and SHA-256 fingerprints—not the complete
extracted proposal.

## Technology

| Component | Purpose |
| --- | --- |
| FastAPI | API, validation, and OpenAPI documentation |
| Sentence Transformers | Local dense embeddings |
| `all-MiniLM-L6-v2` | Default embedding model |
| NumPy | Similarity calculations |
| Groq | Grounded natural-language RFP answers |
| pdfplumber | PDF extraction |
| python-docx | DOCX extraction |
| openpyxl | XLSX extraction |
| Docker | Reproducible non-root deployment |
| pytest | API, security, and scoring tests |

## Quick start

### 1. Clone the repository

```bash
git clone https://github.com/Nour-Elrouby/rfp-vendor-evaluation-agent.git
cd rfp-vendor-evaluation-agent
```

### 2. Create a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Create a local `.env`

```dotenv
GROQ_API_KEY=your_current_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile

EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
MIN_SIMILARITY=0.24

# Optional during local development
API_AUTH_TOKEN=generate_a_random_access_token
```

The embedding settings are optional. `GROQ_API_KEY` is needed only for the RFP
assistant; scoring, ranking, and auditing work without Groq. The `.env` file is
ignored by Git and must never be committed.

Generate a secure application token:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 5. Run the application

```bash
uvicorn main:app --reload
```

Open:

- Dashboard: <http://127.0.0.1:8000>
- API documentation: <http://127.0.0.1:8000/docs>
- Liveness: <http://127.0.0.1:8000/health/live>
- Readiness: <http://127.0.0.1:8000/health/ready>

Swagger documentation is enabled by default in development and disabled by
default in production.

## Authentication

When `API_AUTH_TOKEN` is configured, protected requests require:

```http
X-API-Key: your-access-token
```

The dashboard prompts for the key on its first protected request and stores it
only in browser session storage. Static assets and health endpoints remain
public.

For the command-line examples, set:

```bash
export PROCURELENS_API_KEY="your-access-token"
```

Windows PowerShell:

```powershell
$env:PROCURELENS_API_KEY = "your-access-token"
```

## API reference

| Method | Endpoint | Authentication | Purpose |
| --- | --- | --- | --- |
| `GET` | `/` | Public | Web dashboard |
| `GET` | `/health/live` | Public | Process liveness |
| `GET` | `/health/ready` | Public | Configuration and model status |
| `POST` | `/score-vendor` | Protected | Evaluate a proposal |
| `POST` | `/rank-vendors` | Protected | Rank validated vendor scores |
| `POST` | `/chat` | Protected | Ask a grounded RFP question |
| `GET` | `/audit-trail` | Protected | Retrieve paginated audit records |

### Evaluate a proposal

```bash
curl -X POST "http://127.0.0.1:8000/score-vendor" \
  -H "X-API-Key: $PROCURELENS_API_KEY" \
  -F "file=@sample_vendor_proposal.pdf" \
  -F "rfp_criteria=Complete migration within 16 weeks; maintain PCI-DSS compliance; provide 24/7 support; guarantee 99.9% uptime; keep first-year cost below 200000 dollars."
```

The response contains:

- Overall score from 0 to 100
- Evidence-backed reasoning
- Per-criterion similarity, relevance, and score
- Independent consistency status
- Audit ID and timestamp
- Proposal and criteria SHA-256 fingerprints

### Rank vendors

```bash
curl -X POST "http://127.0.0.1:8000/rank-vendors" \
  -H "X-API-Key: $PROCURELENS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '[
    {"name":"Vendor A","score":92,"reasoning":"Strong evidence coverage"},
    {"name":"Vendor B","score":78,"reasoning":"Several evidence gaps"}
  ]'
```

Ranking is deterministic and consumes no Groq tokens.

### Ask about an RFP

```bash
curl -X POST "http://127.0.0.1:8000/chat" \
  -H "X-API-Key: $PROCURELENS_API_KEY" \
  -F "question=What is the required implementation timeline?" \
  -F "rfp_text=The selected vendor must complete implementation within 16 weeks."
```

The endpoint retrieves up to four relevant passages locally and sends only
qualifying evidence to Groq.

### Retrieve audit records

```bash
curl \
  -H "X-API-Key: $PROCURELENS_API_KEY" \
  "http://127.0.0.1:8000/audit-trail?offset=0&limit=50"
```

Filter by exact filename:

```bash
curl \
  -H "X-API-Key: $PROCURELENS_API_KEY" \
  "http://127.0.0.1:8000/audit-trail?vendor_name=sample_vendor_proposal.pdf"
```

## Production deployment

Production mode requires a strong access token, explicit hosts, and a Groq key:

```dotenv
APP_ENV=production
API_AUTH_TOKEN=your_generated_access_token
ALLOWED_HOSTS=procurelens.example.com
GROQ_API_KEY=your_current_groq_key
GROQ_MODEL=llama-3.3-70b-versatile
AUDIT_LOG_FILE=/app/data/audit_log.jsonl
ENABLE_DOCS=false
```

Build and run:

```bash
docker build -t procurelens .
docker run --rm -p 8000:8000 \
  --env-file .env \
  -v procurelens-data:/app/data \
  procurelens
```

Terminate TLS at a managed load balancer or reverse proxy. Use one application
worker per container because every worker loads its own embedding model.

See [Production Deployment](docs/production.md) for operating limits, scaling,
storage requirements, and the commercial-release checklist.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `APP_ENV` | `development` | `development`, `test`, or `production` |
| `API_AUTH_TOKEN` | Unset | Access token; required in production |
| `ALLOWED_HOSTS` | `*` | Comma-separated trusted hosts |
| `ENABLE_DOCS` | Environment-dependent | Enables `/docs` and `/openapi.json` |
| `GROQ_API_KEY` | Unset | Required for chat and production startup |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq chat model |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence Transformer model |
| `MIN_SIMILARITY` | `0.24` | Chat evidence threshold |
| `AUDIT_LOG_FILE` | `audit_log.jsonl` | Audit storage path |
| `MAX_UPLOAD_BYTES` | `15728640` | Maximum proposal upload |
| `MAX_REQUEST_BYTES` | Upload limit + 1 MB | Maximum request body |
| `MAX_CRITERIA_CHARS` | `20000` | Maximum criteria input |
| `MAX_EXTRACTED_CHARS` | `1000000` | Maximum extracted proposal text |
| `MAX_CHAT_RFP_CHARS` | `200000` | Maximum chat RFP text |
| `MAX_QUESTION_CHARS` | `2000` | Maximum chat question |
| `MAX_RANK_VENDORS` | `500` | Maximum vendors per ranking request |
| `MAX_AUDIT_PAGE_SIZE` | `200` | Maximum audit page size |
| `RATE_LIMIT_PER_MINUTE` | `60` | Per-process client request limit |
| `MAX_CONCURRENT_EVALUATIONS` | `2` | Concurrent scoring operations |
| `LOG_LEVEL` | `INFO` | Application log level |

## Testing

```bash
python -m pip install -r requirements-dev.txt
python -m compileall -q .
pytest -q
python -m pip check
python -m pip_audit -r requirements.txt
```

The suite covers API behavior, security headers, production authentication,
configuration validation, file signatures, grounded retrieval, audit
pagination, and hybrid scoring.

## Project structure

```text
.
|-- main.py                       # FastAPI application and endpoints
|-- config.py                     # Validated runtime configuration
|-- security.py                   # Authentication, limits, and headers
|-- embedding_client.py           # Local embeddings and relevance
|-- scoring.py                    # Per-criterion evidence scoring
|-- ranking.py                    # Deterministic vendor ranking
|-- chatbot.py                    # Local retrieval and grounded generation
|-- groq_client.py                # Groq JSON client
|-- reader.py                     # PDF, DOCX, and XLSX extraction
|-- audit.py                      # Consistency and JSONL audit trail
|-- static/                       # Dashboard HTML, CSS, JS, and favicon
|-- tests/                        # Automated test suite
|-- docs/
|   |-- images/                   # Interface screenshots
|   `-- production.md             # Production operating guide
|-- .github/                      # CI and dependency updates
|-- Dockerfile                    # Non-root production image
|-- requirements.txt              # Runtime dependencies
|-- requirements-dev.txt          # Test and audit dependencies
|-- LICENSE                       # MIT license
`-- sample_vendor_proposal.pdf    # Local evaluation example
```

## Privacy and operating limits

- Local scoring avoids sending proposals to Groq.
- Chat sends only passages selected by local retrieval.
- Evidence excerpts and criteria stored in the audit log may be sensitive.
- The JSONL audit log and in-memory limiter target one application instance.
- Multi-instance deployments require shared rate limiting and durable,
  access-controlled audit storage.
- Define retention, deletion, backup, and incident-response policies before
  processing customer procurement data.

## Market readiness

The repository is suitable for a secured single-tenant MVP or controlled
customer pilot. It is not a finished multi-tenant SaaS product or an autonomous
procurement decision system.

Before broad commercial release, complete:

- Procurement scoring validation against a representative labeled dataset
- Independent penetration testing and threat modeling
- Accessibility testing
- Legal, privacy, processing, and retention reviews
- Tenant isolation and identity-provider integration
- Managed storage, backups, monitoring, alerting, and disaster recovery
- A customer support and incident-response process

## Contributing

Issues and pull requests are welcome. Keep changes focused, never commit
credentials or audit data, and run the complete test suite before submission.

## License

Released under the [MIT License](LICENSE).
