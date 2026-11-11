# onprem

온프레미스 매니저 클러스터에 배포되는 것. 매니페스트는 노찬경, 로직 · 이미지는 `K8s` 레포 담당자 (ADR-21).

| 디렉토리 | 내용 | 로직 담당 |
|---|---|---|
| `platform/` | namespace · Traefik · cert-manager(+ ClusterIssuer) · frontend(+ Ingress · Certificate) · backend | - |
| `multikueue/{kueue,jobset}/` | 매니저 Kueue · JobSet: 공식 Helm 차트(OCI)의 `values.yaml`(설정 · `dispatcherName` 포함) + 차트 밖 Namespace · MAP | - |
| `multikueue/queues/` | ResourceFlavor · ClusterQueue · LocalQueue · WorkloadPriorityClass · AdmissionCheck · MultiKueueConfig · MultiKueueCluster | 김성모 |
| `controllers/scheduling-common/` | RelocationRequest CRD · admission policy (dispatcher · relocator · recovery-controller 공용) | 김성모 |
| `controllers/dispatcher/` | dispatcher (`base` + `overlays/onprem`) | 김성모 |
| `controllers/relocator/` | relocator (`base` + `overlays/onprem`) | 김성모 |
| `controllers/recovery-controller/` | 복구 컨트롤러 (`base` + `overlays/onprem`) | 한송이 |

이미지는 GHCR에 있고, 이곳에는 이미지를 띄우는 매니페스트만 둔다.
컨트롤러 이미지 digest는 K8s CI 봇이 `controllers/<이름>/overlays/onprem/kustomization.yaml`의 `images:`에 커밋한다 (ADR-23, K8s Variable `DEPLOY_IMAGES`에 든 것만).
MultiKueue kubeconfig Secret(`kueue-system/eks-*-kubeconfig`)은 IaC가 등록하고 여기에는 이름만 둔다.
