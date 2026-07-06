# One-time cluster prerequisite — Agent Substrate FULL plane (static certs)

Run this **once per cluster**, before deploying the `substrate-overcommit`
feature. It installs the **full** ate plane — everything `substrate-basic`'s
core install brings up (CRDs, `ate-controller`, `atelet`, gVisor
`SandboxConfig`, `ateom-gvisor` worker image) **plus** the components
suspend/resume needs:

- **`ate-api-server`** — the gRPC control plane the Hub router calls
  (`CreateActor` / `SuspendActor` / `ResumeActor` / `DeleteActor`).
- **`valkey-cluster`** — the api-server's session/state store.
- **`atenet-router` + `dns`** — the data path; proxies *Touch* requests to
  actors and transparently resumes suspended actors on connect.
- **snapshot bucket** — `gs://${PROJECT_NAME}-substrate-snapshots`, where
  `SuspendActor` writes Full snapshots; the node service account gets
  `objectAdmin` on it, and on Workload Identity clusters the WI principal
  for `ns/ate-system/sa/atelet` gets the same grant (the atelet DaemonSet
  does the upload and its GCS calls carry the WI identity, not the node SA).

It is kept out of the Hub's automatic `cluster_dir` apply for the same reasons
as `substrate-basic`'s prerequisite: the operator images are built from
upstream Go source with [`ko`](https://ko.build) (no Dockerfiles upstream), and
this is an operator-run bootstrap, not a per-deploy manifest.

```bash
export PROJECT_NAME=<your-gcp-project>
export CLUSTER=<your-gke-cluster>
export REGION=<your-region>                 # e.g. us-central1
export ARTIFACT_REGISTRY_REPO=gke-showcase  # must match the feature's ateomImage repo

bash install-substrate-overcommit-prereq.sh
```

## Why static certs — the alpha-API problem

Upstream's full-plane install (`install-ate.sh --deploy-ate-system`) assumes the
alpha **agent-identity data plane**: every serving component mounts its TLS
identity from `PodCertificate` projected volumes, rooted in alpha
`certificates.k8s.io/v1beta1` `ClusterTrustBundle` resources. Those APIs are
served only on a GKE **alpha** cluster — on a plain Standard cluster the
projected volumes can never resolve and the plane blocks forever.

This install deploys the **same plane** on a stock Standard cluster by swapping
the certificate *source*, not the plane:

1. **Mint at install time** — one ECDSA P-256 CA + one leaf whose SANs cover
   every serving identity (`api.ate-system.svc`, `atenet-router...`, the valkey
   cluster + per-pod wildcard names). The leaf carries both `serverAuth` and
   `clientAuth` EKUs because the same credential bundle doubles as the
   api-server's valkey client cert.
   - *Key format is load-bearing:* the api-server's `credbundle.Parse` accepts
     only PKCS8 (`PRIVATE KEY`) blocks — hence `openssl genpkey`, never
     `openssl ecparam` (SEC1). Bundle order: key, leaf, CA.
2. **Publish as Secrets** — `servicedns-static-certs` (the bundle),
   `servicedns-ca` / `workerpool-ca-certs` (trust anchors), `valkey-ca-certs`.
3. **Apply the `static-certs/` kustomize overlay** (in this directory) — it
   patches every alpha `PodCertificate` volume in the upstream manifests to
   mount the minted Secrets instead. Applied with
   `--load-restrictor LoadRestrictionsNone` after being copied into the
   upstream tree (its `../*.yaml` refs resolve there).

Nothing else diverges from upstream: the api-server still runs `--auth-mode=jwt`
(verifying K8s SA tokens from the cluster issuer, audience
`api.ate-system.svc`), the router still resolves actor hosts the same way, and
the controller/atelet install is identical to `substrate-basic`'s.

## What the script does (10 steps)

0. Cluster credentials + Artifact Registry docker auth.
1. Clone upstream `agent-substrate/substrate` (or reuse `UPSTREAM_DIR=`).
2. Apply the `ate.dev` CRDs; wait `Established`.
3. Apply SandboxConfig validation policy + default gVisor class + `ate-system`
   namespace.
4. Mint the static CA + leaf and create the 4 cert Secrets (skipped if already
   present).
5. Ensure the session-id jwt + CA pool Secrets (`kubectl-ate admin make-*-pool`).
6. Ensure the `ate-api-server-envvars` ConfigMap (valkey address + TLS name,
   K8s JWT issuer URL for this cluster).
7. Ensure the snapshot bucket `gs://${PROJECT_NAME}-substrate-snapshots` and
   grant `objectAdmin` on it to the cluster's node service account AND — when
   the cluster has a Workload Identity pool — to the WI principal
   `ns/ate-system/sa/atelet` (the atelet DaemonSet performs the snapshot
   upload; under GKE_METADATA its GCS calls carry the WI identity, so a
   node-SA-only grant 403s every suspend and wedges actors in SUSPENDING).
8. Apply the full plane via the `static-certs/` overlay (`kustomize | ko
   resolve | kubectl apply`). The immutable `valkey-cluster-init` Job is
   deleted first; it no-ops if the valkey cluster is already formed.
9. Wait for all rollouts (api-server, controller, router, dns, valkey, atelet)
   + valkey init Job completion.
10. `ko build` + push `ateom-gvisor:latest` to
    `${REGION}-docker.pkg.dev/${PROJECT_NAME}/${ARTIFACT_REGISTRY_REPO}`.

Idempotent-ish: mint/pool/ConfigMap/bucket steps are only-if-absent; manifest
applies and `ko` pushes are safe to re-run.

## Requirements on the operator machine

`gcloud`, `kubectl`, `ko`, `git`, `go` (the pool mint runs `go run
./cmd/kubectl-ate`), `openssl`.

## After the install

Deploy the `substrate-overcommit` feature from the Hub. The Hub applies the
`WorkerPool` + `ActorTemplate` from `../infra/`; the playroom's buttons then
drive the plane you just installed.
