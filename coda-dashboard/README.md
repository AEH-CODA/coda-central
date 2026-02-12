# CODA Platform

A modular, containerized platform for data discovery over knowledge graphs and federated learning workflows.

This repository currently contains a **local Docker-based simulation** of the core components.

---

## Current Components

### 1. API Gateway
- Central orchestration service
- Exposes a single HTTP API for the UI
- Forwards natural language queries to internal services
- Acts as the system boundary for future governance, auth, and auditing

**Tech:** FastAPI, Uvicorn

---

### 2. NL → SPARQL Service
- Internal microservice
- Converts natural language queries into SPARQL
- Not exposed outside Docker network

**Tech:** FastAPI

---

### 3. Data Discovery UI
- Lightweight web UI for submitting natural language queries
- Communicates only with the API Gateway

**Tech:** Static HTML + JavaScript (served via container)

---

All services run as **separate Docker containers** and communicate over a private Docker network.

---

## Prerequisites

- Docker
- Docker Compose

---

## How to Run

From the repository root:

```bash
docker compose up --build
```

Once running:

- UI: http://localhost:5000
- API Gateway health check: http://localhost:8000

Enter a natural language query in the UI to see the end-to-end flow.
