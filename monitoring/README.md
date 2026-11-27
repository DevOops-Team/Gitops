# monitoring

모니터링 배포. 담당: 이태림 (부 김성모). ADR-18 기준

- `onprem/`: 저장 층 (Mimir · Loki · Tempo) · 분류기 overlay(`onprem/classifier`)
- `eks/`: 수집 층 (Prometheus Agent · kube-state-metrics · Fluent Bit · OTel Collector · node-exporter · dcgm-exporter)

## 실제 배포 위치

분류기 overlay와 Vault 연동(`onprem/vault`)을 제외한 모니터링 워크로드 매니페스트·차트 values의 정본은 Monitoring 레포다(ADR-21). Vault 연동은 기존 워크로드를 바꾸지 않고 Secret 공급만 담당한다.

| 층 | 클러스터 | Application (`bootstrap/onprem/applications/`) | project | sync |
|---|---|---|---|---|
| 수집 층 | 관리 클러스터 | `gpu-monitoring-agents` → Monitoring `deploy/manager-cluster` | `gpu-platform` | automated |
| 수집 층 | EKS 워커(`eks-*`, 켜져 있을 때만) | ApplicationSet `gpu-eks-monitoring` → `gpu-eks-monitoring-<클러스터>` → Monitoring `deploy/eks`. 클러스터 이름은 ApplicationSet이 ConfigMap `monitoring-cluster-info`에 넣는다(GPU-186) | `gpu-eks-monitoring` | automated |
| 저장 층 | 모니터링 클러스터(원격, 이름 `monitoring`) | `gpu-monitoring-base`(Monitoring `deploy/monitoring-cluster/storage`) + 차트 8개 `gpu-monitoring-{local-path,node-exporter,kube-state-metrics,loki,tempo,blackbox,alertmanager,grafana}`(values = Monitoring `deploy/monitoring-cluster/values/`) | `gpu-monitoring` | 수동 |
| 분류기 | 모니터링 클러스터 | `gpu-monitoring-classifier` → 이 레포 `monitoring/onprem/classifier`(base는 Monitoring `deploy/monitoring-cluster/classifier`를 릴리스 태그로 참조, 이미지 태그도 여기서 고정) | `gpu-monitoring` | automated |

- 모니터링 클러스터 등록은 IaC `ansible/playbooks/bootstrap/register-monitoring-cluster.yml`(GPU-177)
- Secret 값은 Git에 없다. Slack/Grafana/Postgres exporter/GHCR의 Vault 인계 매니페스트와 수동 준비 절차는 [onprem/vault/README.md](onprem/vault/README.md)를 따른다. 인계 전에는 기존 생성 도구를 사용하고, 인계 뒤 `create-secrets.sh`로 덮어쓰지 않는다. 실제 인계는 별도 확인이 필요하다.
- 관리 클러스터가 죽어 Argo CD를 못 쓸 때는 Monitoring 레포 `scripts/deploy-k8s.sh`(비상용). 차트 버전은 Application의 `targetRevision`과 Monitoring `deploy/versions.env` 두 곳을 같이 고친다
