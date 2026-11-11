# bootstrap

Argo CD root · AppProject와 클러스터별 Application 목록. 담당: 노찬경 (부 한송이)

- `onprem/` · `eks-{a,b,c}/`: `root.yaml` · `project.yaml` (IaC `register-root.yml`이 최초 한 번 등록)
- `onprem/root.yaml`(gpu-root)은 automated(prune · selfHeal): `applications/`의 Application 추가·변경·삭제가 main 머지 후 자동 반영. 각 자식 Application의 sync 방식은 각자 정의를 따름
- `<cluster>/applications/`: 해당 클러스터에 배포할 Application 정의. Application 하나 = 디렉토리 경로 하나
- 최초 bootstrap은 노찬경이 개인 PC에서 수동 실행 (ADR-11, ADR-21)

운영 전환 시 IaC의 `gitops_repo_url`은 `https://github.com/DevOops-Team/Gitops.git`으로, `gitops_root_dir`은 해당 `bootstrap/<대상>`의 절대 경로로 설정합니다. Gitops main에 반영하고 Argo CD의 기존 Application source를 전환한 뒤 K8s에서 기존 경로를 제거합니다.
