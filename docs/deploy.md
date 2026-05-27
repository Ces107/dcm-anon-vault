# Deploy guide

`dcm-anon-vault` ships as a single FastAPI process. Below: docker-compose
for VPS / on-prem, and a minimal Kubernetes manifest set.

## docker-compose

The repo root contains [`docker-compose.yml`](../docker-compose.yml). Edit
`.env` and run:

```bash
cp .env.example .env
# fill DCM_API_KEYS, STRIPE_*, OIDC_* as needed
docker compose up -d
curl http://localhost:8080/health
```

Volumes:

- `sqlite_data` — persistent SQLite database file. For Postgres,
  override `DCM_DB_URL` and remove the volume.

## Fly.io

See README §4 for the 5-minute Fly recipe. `fly.toml` is checked in.

## Kubernetes (single-pod)

The manifests below assume `kubectl apply` against an existing
namespace with cert-manager + nginx-ingress (or equivalent). Tune
resources for your DICOM throughput; the bottleneck is the
PS3.15 dataset scan, not memory.

```yaml
# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: dcm-vault-secrets
type: Opaque
stringData:
  DCM_API_KEYS: "tenant1:REPLACE_RANDOM_HEX_32"
  STRIPE_API_KEY: "sk_live_REPLACE"
  STRIPE_PRICE_ID: "price_REPLACE"
  STRIPE_PRICE_ID_ANNUAL: "price_REPLACE"
  STRIPE_WEBHOOK_SECRET: "whsec_REPLACE"
  DCM_DB_URL: "postgresql+psycopg://user:pass@pg-host:5432/dcm_vault"
  # OIDC (optional):
  # OIDC_DISCOVERY_URL: "https://keycloak.acme/realms/r/.well-known/openid-configuration"
  # OIDC_AUDIENCE: "dcm-anon-vault"
  # OIDC_ISSUER: "https://keycloak.acme/realms/r"
  # Admin (for /v1/audit/verify, /v1/webhooks/deadletter, retention sweep):
  DCM_ADMIN_KEYS: "tenant1"
```

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dcm-anon-vault
  labels: { app: dcm-anon-vault }
spec:
  replicas: 1   # SQLite single-pod; Postgres allows scale-out
  selector: { matchLabels: { app: dcm-anon-vault } }
  template:
    metadata:
      labels: { app: dcm-anon-vault }
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
      containers:
      - name: app
        image: ghcr.io/ces107/dcm-anon-vault:0.3.0
        ports: [{ containerPort: 8080 }]
        envFrom:
        - secretRef: { name: dcm-vault-secrets }
        env:
        - { name: DCM_LOG_LEVEL, value: "INFO" }
        - { name: DCM_RATE_LIMIT_FREE, value: "60" }
        - { name: DCM_RATE_LIMIT_PRO,  value: "600" }
        readinessProbe:
          httpGet: { path: /health, port: 8080 }
          periodSeconds: 10
        livenessProbe:
          httpGet: { path: /health, port: 8080 }
          periodSeconds: 30
        resources:
          requests: { cpu: "200m", memory: "256Mi" }
          limits:   { cpu: "2",    memory: "1Gi" }
        volumeMounts:
        - { name: data, mountPath: /data }
      volumes:
      - name: data
        persistentVolumeClaim: { claimName: dcm-vault-data }
```

```yaml
# pvc.yaml (only needed if using SQLite, not Postgres)
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: dcm-vault-data }
spec:
  accessModes: [ReadWriteOnce]
  resources: { requests: { storage: 5Gi } }
```

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata: { name: dcm-anon-vault }
spec:
  selector: { app: dcm-anon-vault }
  ports: [{ port: 80, targetPort: 8080, name: http }]
```

```yaml
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: dcm-anon-vault
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/proxy-body-size: "200m"   # > 100 MB upload cap
spec:
  ingressClassName: nginx
  tls:
  - hosts: [vault.example.com]
    secretName: dcm-anon-vault-tls
  rules:
  - host: vault.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service: { name: dcm-anon-vault, port: { number: 80 } }
```

### Prometheus scrape

If you run `kube-prometheus-stack` or similar, add a `ServiceMonitor`:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata: { name: dcm-anon-vault }
spec:
  selector: { matchLabels: { app: dcm-anon-vault } }
  endpoints:
  - port: http
    path: /metrics
    interval: 30s
```

The `/metrics` endpoint is open by design. If your cluster does not
restrict pod-to-pod traffic via NetworkPolicy, mount the metrics route
behind an auth proxy (e.g. oauth2-proxy with the cluster IdP).

### Retention CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata: { name: dcm-vault-retention }
spec:
  schedule: "17 3 * * *"  # daily 03:17 UTC
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
          - name: curl
            image: curlimages/curl:8
            command: ["sh", "-c"]
            args:
            - |
              curl -fsSL -X POST \
                -H "X-API-Key: $ADMIN_API_KEY" \
                http://dcm-anon-vault/v1/admin/retention/sweep
            env:
            - name: ADMIN_API_KEY
              valueFrom: { secretKeyRef: { name: dcm-vault-admin, key: api_key } }
```

## Production checklist

- [ ] Persistent volume (PVC or managed Postgres via `DCM_DB_URL`).
- [ ] TLS termination at the ingress / load balancer (never serve PHI
      over plain HTTP).
- [ ] Stripe webhook URL registered with the correct event types and
      the signing secret deployed as `STRIPE_WEBHOOK_SECRET`.
- [ ] Backup the `customers` and `anonymization_events` tables daily;
      these hold the only persistent record of who is paying and what
      they processed.
- [ ] Run `/v1/audit/verify` from CI / monitoring; alert on
      `"broken"`.
- [ ] Set `DCM_OPEN_DOCS` only in non-production environments.
- [ ] Set `DCM_ADMIN_KEYS` to a SINGLE long-lived ops-only key. Rotate
      separately from customer keys.
- [ ] Configure log shipping (Loki / Elastic / Datadog) to parse the
      JSON lines emitted on stdout.
