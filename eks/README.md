# eks

EKS 워커 클러스터(eks-a · eks-b · eks-c)에 배포되는 것. 매니페스트는 노찬경, 로직 담당 김성모 (+ 박기현).

EKS에는 Argo CD가 없다. 온프레미스 Argo CD가 AppProject `gpu-eks` · ApplicationSet으로 원격 배포한다 (`bootstrap/README.md`).

- `scheduling/base/`: 워커 Kueue · JobSet · 큐(관리 클러스터와 같은 LocalQueue 이름) · dispatcher 읽기 RBAC. 클러스터 이름을 넣지 않는다
- `scheduling/overlays/eks-{a,b,c}/`: 클러스터별로 다른 값만 (GPU 쿼터 · `waitForPodsReady` 시간 등)

IaC Ansible(`multikueue-access.yml`)이 `kueue-system` 네임스페이스와 `kueue-system/multikueue-sa`(MultiKueue용 SA · 토큰)를 먼저 만든다.
이 SA에는 잡 생성 권한만 있으므로, dispatcher가 쓰는 nodes · pods 읽기 권한은 여기서 별도 ClusterRole로 같은 SA에 묶는다.
