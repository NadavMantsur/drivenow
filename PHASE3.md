# DriveNow Phase 3 — CI/CD + Kubernetes (full README comes next)

## GitHub Actions

Workflow: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)

On push/PR it:
1. Installs deps and runs **fleet** + **rental** pytest suites
2. Builds both Docker images (`drivenow/fleet:ci`, `drivenow/rental:ci`)

## Kubernetes (Phase 1 stack)

Manifests live under [`k8s/`](../k8s/) (namespace `drivenow`: postgres, fleet, rental).

### Build images (local kind / minikube)

```bash
cd /home/my/drivenow
docker build -f services/fleet_service/Dockerfile -t drivenow/fleet:latest .
docker build -f services/rental_service/Dockerfile -t drivenow/rental:latest .

# kind example:
# kind load docker-image drivenow/fleet:latest
# kind load docker-image drivenow/rental:latest
```

### Apply

```bash
kubectl apply -k k8s/
kubectl -n drivenow get pods,svc
```

### Access (NodePort)

| Service | URL (typical local NodePort) |
|---------|------------------------------|
| Fleet   | http://localhost:30001/docs  |
| Rental  | http://localhost:30002/docs  |

Or port-forward:

```bash
kubectl -n drivenow port-forward svc/fleet 8001:8000
kubectl -n drivenow port-forward svc/rental 8002:8000
```

Demo DB credentials are in `k8s/postgres/secret.yaml` — replace before any shared/cluster use.
