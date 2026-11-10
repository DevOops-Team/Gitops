# eks

EKS 워커 클러스터(eks-a · eks-b · eks-c)에 배포되는 것. 담당: 김성모 (+ 박기현)

- `scheduling/base/`: 워커 Kueue · JobSet · 큐 · relocator RBAC. 클러스터 이름을 넣지 않는다
- `scheduling/overlays/eks-{a,b,c}/`: 클러스터별로 다른 값만
