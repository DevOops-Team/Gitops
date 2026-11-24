# 기존 워커 kubeconfig 4개 Vault 인계 (GPU-241)

대상 namespace는 `kueue-system`, 기존 Secret key는 모두 `kubeconfig`다.
`eks-a-kubeconfig`, `eks-a-relocator-kubeconfig`, `eks-b-kubeconfig`, `eks-b-relocator-kubeconfig`를 각각 별도 KV·읽기 정책·인증 SA로 연결한다.
새 EKS 계정 발급이나 kubeconfig 재작성은 하지 않는다. Argo의 `argocd/cluster-*` Secret은 별도 대상이다.

## 1. master1: 기존 값의 안전한 복사

관리 클러스터 context를 확인한다. 같은 Secret을 갱신하는 담당자와 인계 시간을 맞춘다.
아래 명령은 비밀값을 화면에 출력하지 않으며 임시 디렉터리에만 저장한다.

```bash
kubectl config current-context
umask 077
export KC_TRANSFER_DIR=$(mktemp -d "$HOME/kubeconfig-vault.XXXXXX")
python3 - <<'PY'
import base64, json, os, pathlib, subprocess
root = pathlib.Path(os.environ['KC_TRANSFER_DIR'])
names = ('eks-a-kubeconfig', 'eks-a-relocator-kubeconfig',
         'eks-b-kubeconfig', 'eks-b-relocator-kubeconfig')
for name in names:
    s = json.loads(subprocess.check_output(['kubectl', '-n', 'kueue-system', 'get', 'secret', name, '-o', 'json']))
    if s.get('immutable') or s['metadata'].get('ownerReferences'):
        raise SystemExit('중단: 변경 불가 또는 기존 소유자 확인 필요: ' + name)
    if s.get('type', 'Opaque') != 'Opaque' or set(s.get('data', {})) != {'kubeconfig'}:
        raise SystemExit('중단: Secret 종류/key가 예상과 다름: ' + name)
    v = {'kubeconfig': base64.b64decode(s['data']['kubeconfig'], validate=True).decode('utf-8')}
    (root / (name + '.original.json')).write_text(json.dumps(s))
    (root / (name + '.values.json')).write_text(json.dumps(v))
print('4개 원본 백업 및 변환 완료. 비밀값은 출력하지 않았습니다.')
PY
```

위 검사가 모두 성공한 뒤 전송한다.

```bash
ssh vault1@172.30.0.81 'umask 077; mkdir -p "$HOME/vault-import/kubeconfigs"; chmod 700 "$HOME/vault-import/kubeconfigs"'
scp "$KC_TRANSFER_DIR/"*.values.json vault1@172.30.0.81:vault-import/kubeconfigs/
```

## 2. vault1: KV·정책·인증 role 생성

Vault가 unseal되고 관리 CLI 로그인이 된 상태에서 실행한다. `-cas=0`은 최초 생성만 허용한다.
이미 있는 경로는 덮어쓰지 말고 기존 Vault 값과 Kubernetes 원본을 비교한다.

```bash
(
set -eu
umask 077
export VAULT_ADDR=https://172.30.0.81:8200
export VAULT_CACERT="$HOME/vault-ca.crt"
for name in eks-a-kubeconfig eks-a-relocator-kubeconfig eks-b-kubeconfig eks-b-relocator-kubeconfig; do
  vault kv put -cas=0 "devoops/onprem/kueue-system/$name" @"$HOME/vault-import/kubeconfigs/$name.values.json"
  vault kv get -format=json "devoops/onprem/kueue-system/$name" > "$HOME/vault-import/kubeconfigs/$name.stored.json"
  python3 - "$name" <<'PY'
import json, pathlib, sys
p = pathlib.Path.home() / 'vault-import/kubeconfigs'
n = sys.argv[1]
if json.loads((p / (n + '.values.json')).read_text()) != json.loads((p / (n + '.stored.json')).read_text())['data']['data']:
    raise SystemExit('중단: 원본과 Vault 불일치: ' + n)
print(n + ': 원본과 Vault 값 일치')
PY
  vault policy write "$name-read" - <<POLICY
path "devoops/data/onprem/kueue-system/$name" {
  capabilities = ["read"]
}
POLICY
  vault write "auth/onprem/role/$name-sync" \
    bound_service_account_names="$name-sync" \
    bound_service_account_namespaces=kueue-system \
    token_policies="$name-read" token_ttl=10m token_max_ttl=1h
done
)
```

중간 실패 시 Sync하지 않는다. 성공한 경로는 남을 수 있으므로 전체 루프를 무조건 재실행하지 말고 실패 지점부터 원본 일치를 확인한다.

## 3. master1: 공개 CA 준비

제공된 Secret 목록에는 `kueue-system/vault-vm-ca`가 없었으므로 준비한다.
이미 있다면 내용과 소유자를 검토하고 같은 CA인지 확인한다. 개인키를 복사하지 않는다.

```bash
scp vault1@172.30.0.81:vault-ca.crt "$KC_TRANSFER_DIR/vault-ca.crt"
kubectl -n kueue-system create secret generic vault-vm-ca \
  --from-file=ca.crt="$KC_TRANSFER_DIR/vault-ca.crt" \
  --dry-run=client -o yaml | kubectl apply -f -
```

## 4. 코드 반영과 수동 Sync

Argo는 main을 읽는다. PR 리뷰·main 반영 후 새 `gpu-vault-worker-kubeconfigs` Application의 Diff를 확인한다.
KV 4개·role 4개·공개 CA를 모두 준비한 뒤에만 수동 Sync한다. 기존 common Application을 먼저 Sync할 필요는 없다.
새 앱 안에 kueue-system VaultConnection 1개, 인증 SA/Auth/최소 TokenReview 권한 4벌과 VaultStaticSecret 4개가 함께 있다.
`create:false`, `excludeRaw:true`, `refreshAfter:60s`이며 자동 Sync·prune·rollout 재시작은 없다.

Sync 직전과 SecretSynced 확인 후 다음 비교를 각각 실행한다. Secret UID·type·모든 key와 값이 같아야 한다.

```bash
python3 - <<'PY'
import json, os, pathlib, subprocess
root = pathlib.Path(os.environ['KC_TRANSFER_DIR'])
for backup in sorted(root.glob('*.original.json')):
    a = json.loads(backup.read_text())
    name = a['metadata']['name']
    b = json.loads(subprocess.check_output(['kubectl', '-n', 'kueue-system', 'get', 'secret', name, '-o', 'json']))
    if (a['metadata']['uid'], a.get('type'), a.get('data')) != (b['metadata']['uid'], b.get('type'), b.get('data')):
        raise SystemExit('중단: 원본과 현재 Secret 불일치: ' + name)
    print(name + ': UID/type/key/값 유지')
PY
kubectl -n kueue-system get vaultstaticsecrets
kubectl get multikueueclusters
```

각 VSS의 Ready/SecretSynced와 MultiKueue·relocator의 EKS 재연결도 확인한다.
Secret 동기화 성공만으로 장기 실행 클라이언트가 바뀐 파일을 재읽었다고 가정하지 않는다.
후속 kubeconfig 갱신 시 발급·만료 관리와 소비자의 재연결 방법을 별도로 시험한다.

## 관리 주체와 복구

- 기존 kubeconfig 생성/회전 자동화가 같은 Secret을 다시 쓰지 않도록 담당자와 인계한다. Secret 동기화는 토큰을 자동 재발급하지 않는다.
- IaC의 VSO 관리 대상 보호 설정에도 이 4개 목적지를 반영한다. 이번 Gitops 변경이 IaC 실행 설정을 자동 변경하지는 않는다.
- 문제 발생 시 해당 VSS 동기화를 중단하고 보안 백업으로 원본과 대조한다. CR 삭제는 값 복원이 아니며 기존 Secret을 삭제하지 않는다.
- 이관·검증 후 비밀값 임시 파일과 원격 복사본은 팀의 보관/삭제 절차로 정리한다. Git·채팅·로그에 붙이지 않는다.
