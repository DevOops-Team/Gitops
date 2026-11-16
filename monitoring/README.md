# monitoring

모니터링 배포. 담당: 이태림 (부 김성모). ADR-18 기준

- `onprem/`: 저장 층 (Mimir · Loki · Tempo)
- `eks/`: 수집 층 (Prometheus Agent · Fluent Bit · OTel Collector)

## 실제 배포 위치

이 디렉토리에는 매니페스트를 두지 않는다. 모니터링 매니페스트 · 차트 values의 정본은 Monitoring 레포이고, 여기(Gitops)에는 그것을 가리키는 Application만 있다(ADR-21 모니터링 예외).

| 층 | 클러스터 | Application (`bootstrap/onprem/applications/`) | project | sync |
|---|---|---|---|---|
| 수집 층 | 관리 클러스터 | `gpu-monitoring-agents` → Monitoring `deploy/agents/overlays/onprem` | `gpu-platform` | automated |
| 저장 층 | 모니터링 클러스터(원격, 이름 `monitoring`) | `gpu-monitoring-base`(Monitoring `deploy/base`) + 차트 8개 `gpu-monitoring-{local-path,node-exporter,kube-state-metrics,loki,tempo,blackbox,alertmanager,grafana}`(values = Monitoring `deploy/values/`) | `gpu-monitoring` | 수동 |

- 모니터링 클러스터 등록은 IaC `ansible/playbooks/bootstrap/register-monitoring-cluster.yml`(GPU-177)
- Secret(S3 인증서 · Slack · Grafana)은 Git에 없다. Monitoring 레포 `scripts/create-secrets.sh`로 넣는다
- 관리 클러스터가 죽어 Argo CD를 못 쓸 때는 Monitoring 레포 `scripts/deploy-k8s.sh`(비상용). 차트 버전은 Application의 `targetRevision`과 Monitoring `deploy/versions.env` 두 곳을 같이 고친다
