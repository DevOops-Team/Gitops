# bootstrap

Argo CD root · AppProject와 Application 목록. 담당: 노찬경 (부 한송이)

Argo CD는 온프레미스 매니저 클러스터에만 있다. EKS에는 Argo CD를 두지 않고, 온프레미스 Argo CD가 허브로 EKS에 원격 배포한다.

- `onprem/`: `root.yaml`(gpu-root) · `project.yaml`(gpu-platform). IaC `register-root.yml`이 `onprem/kustomization.yaml`을 적용한다. AppProject는 gpu-root 밖이라 바꾸면 `register-root`를 다시 실행해야 반영된다
- `onprem/root.yaml`(gpu-root)은 automated(prune · selfHeal): `applications/`의 Application 추가·변경·삭제가 main 머지 후 자동 반영. 각 자식 Application의 sync 방식은 각자 정의를 따름
- `onprem/applications/`: 배포할 Application 정의. Application 하나 = 디렉토리 경로 하나
- EKS 배포(GPU-133): AppProject `gpu-eks`(목적지 `name: eks-*`)와 ApplicationSet을 `onprem/`에 둔다. ApplicationSet은 Argo CD 클러스터 Secret(IaC가 EKS 생성·삭제 때 등록·삭제, GPU-126)을 보고 `eks/scheduling/overlays/<클러스터>`를 가리키는 Application을 만들고 지운다
- 최초 bootstrap은 노찬경이 개인 PC에서 수동 실행 (ADR-11, ADR-21)
