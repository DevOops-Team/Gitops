# monitoring

모니터링 배포. 담당: 이태림 (부 김성모). ADR-18 기준

- `onprem/`: 저장 층 (Mimir · Loki · Tempo) · 분류기 overlay(`onprem/classifier`)
- `eks/`: 수집 층 (Prometheus Agent · kube-state-metrics · Fluent Bit · OTel Collector · node-exporter · dcgm-exporter)

## 실제 배포 위치

분류기를 빼면 이 디렉토리에는 매니페스트를 두지 않는다. 모니터링 매니페스트 · 차트 values의 정본은 Monitoring 레포이고, 여기(Gitops)에는 그것을 가리키는 Application만 있다(ADR-21 모니터링 예외).

| 층 | 클러스터 | Application (`bootstrap/onprem/applications/`) | project | sync |
|---|---|---|---|---|
| 수집 층 | 관리 클러스터 | `gpu-monitoring-agents` → Monitoring `deploy/agents/overlays/onprem` | `gpu-platform` | automated |
| 수집 층 | EKS 워커(`eks-*`, 켜져 있을 때만) | ApplicationSet `gpu-eks-monitoring` → `gpu-eks-monitoring-<클러스터>` → Monitoring `deploy/agents/overlays/eks`. 클러스터 이름은 ApplicationSet이 ConfigMap `monitoring-cluster-info`에 넣는다(GPU-186) | `gpu-eks-monitoring` | automated |
| 저장 층 | 모니터링 클러스터(원격, 이름 `monitoring`) | `gpu-monitoring-base`(Monitoring `deploy/base`) + 차트 8개 `gpu-monitoring-{local-path,node-exporter,kube-state-metrics,loki,tempo,blackbox,alertmanager,grafana}`(values = Monitoring `deploy/values/`) | `gpu-monitoring` | 수동 |
| 분류기 | 모니터링 클러스터 | `gpu-monitoring-classifier` → 이 레포 `monitoring/onprem/classifier`(base는 Monitoring `deploy/classifier/base`를 릴리스 태그로 참조, 이미지 태그도 여기서 고정) | `gpu-monitoring` | automated |

- 모니터링 클러스터 등록은 IaC `ansible/playbooks/bootstrap/register-monitoring-cluster.yml`(GPU-177)
- Secret(S3 인증서 · Slack · Grafana)은 Git에 없다. Monitoring 레포 `scripts/create-secrets.sh`로 넣는다
- 관리 클러스터가 죽어 Argo CD를 못 쓸 때는 Monitoring 레포 `scripts/deploy-k8s.sh`(비상용). 차트 버전은 Application의 `targetRevision`과 Monitoring `deploy/versions.env` 두 곳을 같이 고친다
