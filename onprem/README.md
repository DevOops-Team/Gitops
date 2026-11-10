# onprem

온프레미스 매니저 클러스터에 배포되는 것.

| 디렉토리 | 내용 | 담당 (부) |
|---|---|---|
| `platform/` | namespace · Traefik · cert-manager(+ ClusterIssuer) · frontend(+ Ingress · Certificate) · backend | 노찬경 (한송이) |
| `controllers/recovery-controller/` | 복구 컨트롤러 | 한송이 (박기현) |
| `controllers/scheduling-controllers/` | dispatcher · relocator · RelocationRequest CRD · admission policy | 김성모 (김현수) |
| `multikueue/` | 매니저 Kueue · JobSet · 큐(ClusterQueue · MultiKueue · ResourceFlavor · PriorityClass) | 김성모 (김현수) |

이미지는 GHCR에 있고, 이곳에는 이미지를 띄우는 매니페스트만 둔다.
