# Agent Operational Rules & Guidelines: GKE Feature Showcase Hub

This document defines mandatory operational rules, security policies, and quality standards for any AI agent or subagent executing development milestones on the GKE Feature Showcase Hub repository.

---

## Rule 1: Mandatory Test-Driven Execution & Verification
Every development milestone or feature task **MUST** conclude with robust automated verification before being marked as complete.

### Operational Requirements
1. **Test Authoring**: For every new feature, endpoint, or architectural change, the executing agent must author accompanying unit tests (`/tests/unit`) or integration tests (`/tests/integration`).
2. **Coverage Requirement**: Tests must cover both positive success paths and negative error/rejection handling (e.g., basic auth failures, JWT expiration, k8s exceptions, invalid namespaces).
3. **Execution Verification**: Before marking any task or milestone as `[x]` in `plan.md`, the agent **MUST** execute the entire pytest suite inside the virtual environment:
   ```bash
   .venv/bin/python3 -m pytest tests/
   ```
4. **Zero Tolerance**: The test suite must pass with 100% success (zero failures or errors) before the agent concludes its turn.

---

## Rule 2: Mandatory Documentation & Specification Synchronization
Before concluding any milestone or marking it as complete (`[x]`), the executing agent **MUST** ensure all primary project documentation is perfectly synchronized with the codebase:

1. **`README.md`**: Must be updated with any new setup instructions, environment variables, CLI flags, or architectural descriptions introduced during the milestone.
2. **`design.md`**: Must be updated if any conceptual topology, database schema, or component interactions evolved.
3. **`plan.md`**: Must be updated to reflect granular task progress, marking active tasks as `[/]` and completed, pytest-verified tasks as `[x]`.

---

## Rule 3: Infrastructure-as-Code (IaC) & Reproducibility Mandate
To guarantee that the application remains 100% reproducible across any GCP environment:

1. **Prohibition of Direct `gcloud` CLI Execution**: Agents must **NEVER** alter GKE cluster configurations, node pools, IAM bindings, or cloud infrastructure by running manual or one-off `gcloud` terminal commands.
2. **Centralized Scripting**: All infrastructure modifications, permissions, or registry configurations must be explicitly authored inside the master infrastructure scripts:
   *   `build_infra.sh`: Master GKE cluster bootstrap and base resource provisioning.
   *   `scripts/build_and_push.sh`: Multi-stage container compilation and Artifact Registry deployment.
3. **Reproducible Execution**: Whenever infrastructure modifications are required, agents must update these master scripts and execute them directly to ensure complete reproducibility.

---

## Rule 4: Strict Code Formatting & Type Hinting
1. **Type Annotations**: All new Python functions, methods, and variables **MUST** include explicit type hints (e.g., `def get_feature_status(name: str) -> dict:`).
2. **Pristine Formatting**: Agents must ensure all code adheres to PEP8 formatting guidelines (verifiable via `ruff` or `black`). Unused imports, unformatted lines, or dangling variables are strictly prohibited.

---

## Rule 5: Robust Error Handling & Structured Logging
1. **Prohibition of Silent Failures**: Bare `except:` blocks or silent `except Exception: pass` statements are strictly prohibited. 
2. **Contextual Logging**: All exceptions must be captured and logged with rich context using `logger.error(..., exc_info=True)` or `logger.warning()`.
3. **Structured HTTP Exceptions**: FastAPI REST controllers must return explicit, descriptive `HTTPException` models with appropriate HTTP status codes (400, 401, 403, 404, 500) rather than allowing internal exceptions to bubble up as generic 500 errors.

---

## Rule 6: Strict Security & Plaintext Secret Prohibition
1. **Zero Plaintext Credentials**: Agents must **NEVER** hardcode plaintext secrets, API keys, passwords, or secure connection tokens inside source code, test mock strings, or manifest files.
2. **Environment Management**: All credentials and confidential variables must be strictly loaded from local `.env` configurations or environment variables (`os.getenv`).

---

## Rule 7: Mandatory Docstrings & OpenAPI/Swagger Integrity
1. **Google-Style Docstrings**: Every new public function, class, and API controller must include a clear Google-style Python docstring documenting parameters, return types, and potential exceptions.
2. **High-Fidelity Swagger UI**: FastAPI endpoint routers must include detailed `summary`, `description`, and `response_model` parameters to guarantee that the interactive API documentation at `/docs` remains completely accurate and professional.

---

## Rule 8: Pinned Dependency Management
1. **No Wildcard Packages**: When introducing a new Python dependency (such as `pyjwt` or `pytest-cov`), agents are strictly prohibited from running unpinned installations.
2. **Explicit Version Pinning**: All new packages must be explicitly pinned to their tested version inside `showcase_admin/requirements-dev.txt` or the showcase's local `requirements.txt` (e.g., `pyjwt>=2.8.0`).

---

## Rule 9: Modular Isolation & Approach B Compliance
1. **Repository Modularity**: When adding new feature showcases, agents must adhere strictly to **Approach B**. All backend manifests (`/infra`) and standalone frontend UI assets (`/frontend`) must be co-located within `/features/<feature-name>/`.
2. **Decentralized Gateways**: Every showcase feature must deploy with its own standalone Kubernetes `Gateway` and external IP.
3. **CORS Enforcement**: All feature backend API servers must be equipped with standard CORS headers (`Access-Control-Allow-Origin: *`) to permit direct cross-origin REST API calls from client browsers.

---

## Rule 10: Atomic Task Execution & Changelist Hygiene
1. **Atomic Units of Work**: Agents must execute work in small, focused increments. An agent must never attempt to solve multiple unrelated milestones simultaneously.
2. **Changelist Descriptions**: Every commit or changelist must include a clean, professional semantic commit message (e.g., `feat:`, `fix:`, `test:`, `docs:`, `refactor:`).
