# relocator (재배치 실행기)

관리 클러스터 `platform/relocator`. 로직은 K8s `scheduling/relocator`(김성모), 배포는 여기서 한다 (GPU-173).

## 미리 만드는 Secret: `platform/relocator-aws`

Roles Anywhere 인증서와 AWS 이름들이다. 개인 키 · 계정 ID가 들어 있어 Git에 두지 않는다.

| 키 | 값 | 어디서 |
|---|---|---|
| `client.pem` · `client.key` | relocator 인증서 (CN `devoops-prod-relocator`) | IaC `bootstrap/certs.sh relocator` → `~/.devoops/rolesanywhere/prod/relocator/` |
| `trust_anchor_arn` | 인증서를 발급한 CA의 anchor | IaC `terraform/run.sh output base -- trust_anchor_arns` (새 CA = `v2`) |
| `profile_arn` · `role_arn` | relocator profile · 역할 | `... output base -- workloads`의 `relocator` |
| `ckpt_bucket` | 체크포인트 버킷 이름 | `... output base -- checkpoint_bucket` |

```shell
D=~/.devoops/rolesanywhere/prod/relocator
kubectl -n platform create secret generic relocator-aws \
  --from-file=client.pem=$D/client.pem --from-file=client.key=$D/client.key \
  --from-literal=trust_anchor_arn=... --from-literal=profile_arn=... --from-literal=role_arn=... \
  --from-literal=ckpt_bucket=... --dry-run=client -o yaml | kubectl apply -f -
kubectl -n platform rollout restart deployment/relocator   # 인증서를 바꿨을 때
```

인증서 유효기간은 60일이다. `bootstrap/certs.sh --renew relocator`로 갱신한 뒤 위 명령으로 Secret을 덮어쓰고 재시작한다.

## 확인

```shell
kubectl -n platform logs deploy/relocator -c aws-auth   # serve 시작 · 첫 자격 증명
kubectl -n platform logs deploy/relocator -c main       # 리더 선출 · 워커 kubeconfig 경고 없음
```

`워커 eks-x kubeconfig 못 읽음` 경고가 나오면 IaC가 그 EKS의 `kueue-system/eks-x-relocator-kubeconfig`를 등록했는지 확인한다.
