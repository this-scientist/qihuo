# MySQL Primary Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dashboard use MySQL as the primary persisted data source, with missing dates fetched from the market API and then stored in MySQL.

**Architecture:** Keep the existing CSV-based collector as a temporary compute pipeline, but stop using dashboard snapshots as the runtime source of truth. Store complete API payloads in MySQL `api_cache`; read `/api/data`, `/api/snapshots`, scanner, and option payloads from MySQL first. Add local Docker Compose config for MySQL.

**Tech Stack:** Python, PyMySQL, MySQL 8 Docker, existing dashboard collector and frontend.

---

### Task 1: Local MySQL Configuration

**Files:**
- Create: `docker-compose.mysql.yml`
- Modify: `.env.example`
- Modify: `.env`

- [x] Add a MySQL 8 compose service on `127.0.0.1:3306`.
- [x] Add default `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE` settings.

### Task 2: MySQL Cache Helpers

**Files:**
- Modify: `期货/mysql_store.py`

- [x] Add helpers to list cached dashboard dates.
- [x] Add a safe connection probe for runtime fallback.

### Task 3: Runtime DB-First Server

**Files:**
- Modify: `期货/research_server.py`

- [x] Load active payload from MySQL `api_cache` if present.
- [x] Return cached dates from MySQL for `/api/snapshots`.
- [x] On `/api/update`, collect into a temporary source, build payload, write it to MySQL, then make it active.
- [x] Avoid publishing dashboard snapshot bundles in the update path.

### Task 4: Verification

**Files:**
- Test via existing Python imports and local HTTP endpoints.

- [x] Run syntax/import checks.
- [x] Start MySQL with Docker Compose.
- [x] Ensure schema exists.
- [x] Confirm empty server starts and can later write payloads after update.
