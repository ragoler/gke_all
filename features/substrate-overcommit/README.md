# Agent Substrate — Overcommit (suspend/resume)

A live, **interactive** Hub playroom for Agent Substrate's headline capability:
**overcommit** — packing many logical actors onto a small shared worker pool by
suspending idle sessions to snapshots and resuming them on demand with in-memory
state intact.

The playroom runs **10 actor lanes on a 2-worker pool**. Each actor is a tiny
in-RAM counter; *Touch* bumps it. Suspend a lane (full snapshot, worker slot
freed), resume it — or just Touch it, which transparently resumes it on connect
— and the count picks up exactly where it left off. That continuing count is
the visible proof the actor's memory state survived the round-trip through a
snapshot while its worker slot was serving someone else.

## How it differs from `substrate-basic`

| | `substrate-basic` | `substrate-overcommit` (this) |
|---|---|---|
| Posture | read-only reconcile viewer | interactive — every button mutates actor state |
| Plane | CORE only (controller + atelet) | **FULL** (adds `ate-api-server`, `valkey`, `atenet-router` + dns) |
| API used | K8s API (CRs + Deployments) | ate control plane **gRPC** + atenet data path |
| Snapshots | none | Full snapshots to GCS on suspend |

## Architecture

- **Control plane calls** — the Hub router (`hub_router.py`) speaks gRPC to the
  in-cluster `ate-api-server` (`api.ate-system.svc:443`): `CreateActor` /
  `SuspendActor` / `ResumeActor` / `DeleteActor` / `ListActors` / `ListWorkers`,
  scoped to this feature's own atespace (`overcommit`). Auth is the api-server's
  `jwt` mode: the Hub mints a TokenRequest token for the `ate-client`
  ServiceAccount (audience `api.ate-system.svc`) and verifies TLS against the
  install-time static CA (Secret `ate-system/servicedns-ca`).
- **Data path** — *Touch* goes through the `atenet-router` instead: a plain HTTP
  GET with Host `lane-N.overcommit.actors.resources.substrate.ate.dev`. The
  router proxies to the actor, **transparently resuming it if suspended**
  (resume-on-connect), and the actor returns its bumped `{"count": N}`.
- **The actor** — a digest-pinned busybox loop serving one HTTP request per
  iteration and incrementing a shell variable (see `infra/actortemplate.yaml`).
  The count lives only in process memory — that's the point.
- **Snapshots** — `snapshotsConfig: { onPause: Full }` writes actor snapshots
  (memory included) to `gs://<project>-substrate-snapshots/substrate-overcommit/`.

## Prerequisite — one-time FULL-plane install (needs `ko`)

Unlike `substrate-basic` (core reconcile only), this feature needs the full ate
plane. Upstream's install path for that plane assumes alpha
`certificates.k8s.io/v1beta1` APIs (PodCertificate / ClusterTrustBundle) that a
plain GKE Standard cluster does not serve — so the prerequisite script installs
the same plane using **static openssl-minted certs** instead. See
[`cluster/README.md`](cluster/README.md) and run
[`cluster/install-substrate-overcommit-prereq.sh`](cluster/install-substrate-overcommit-prereq.sh)
once per cluster before deploying this feature from the Hub.

## What the Hub applies

Once the prerequisite is in place, deploying from the Hub applies the two
`ate.dev` CRs from `infra/` — the 2-replica `WorkerPool` and the counter
`ActorTemplate` — templated with `NAMESPACE` / `PROJECT_NAME` / `REGION` /
`ARTIFACT_REGISTRY_REPO`. The `ate-controller` reconciles the pool into
`substrate-overcommit-deployment` (the feature's `deployment_name`, so the
Hub's readiness poll is the reconcile signal). Actors are then created lazily,
one per lane, when you press *Run*.

## Hub-side requirements

- `grpcio` + `protobuf>=6.31.0` (vendored `ateapipb/` stubs are gencode 6.31) —
  in `showcase_admin/requirements-dev.txt`.
- The Hub ClusterRole needs `serviceaccounts/token` `create` (TokenRequest for
  the `ate-client` SA) — in `infra/main-app.yaml`.
