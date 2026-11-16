# recovery-controller (복구 컨트롤러)

관리 클러스터 `platform/recovery-controller`. 로직은 K8s `recovery-controller`(한송이), 배포는 여기서 한다 (GPU-173).

**지금은 `replicas: 0`이다.** RBAC · Lease · ConfigMap만 올라가고 Pod는 돌지 않는다.
설정은 사건을 받지 않는 안전한 기본값(`observe` · `event_source: disabled`)이다.

## 켜는 조건

| 필요한 것 | 상태 | 담당 |
|---|---|---|
| recovery_table (DynamoDB inbox · 진행 기록) | IaC에 없음 | GPU-113 (한송이) |
| IAM: recovery_table GetItem · PutItem · UpdateItem · Scan | 지금은 펜싱 테이블 GetItem · UpdateItem만 | IaC `live/base/onprem-roles.tf` |
| Kafka 브로커 주소 · 인증 → Secret `platform/recovery-controller-credentials` (`KAFKA_CLIENT_CONFIG_JSON`) | 미정 | 데이터 파트 |
| Secret `platform/recovery-controller-aws` (인증서 · ARN, relocator와 같은 형식) | 없음 | `bootstrap/certs.sh recovery` |
| relocator 배포 | `../relocator` | |

준비되면 overlay에서 ConfigMap을 Kafka 관찰 모드(`event_source: kafka`, `mode: observe`)로 바꾸고 `replicas: 3`으로 올린다.
실행 모드(`execute`)는 `scheduler_policy_confirmed: true` 검토 뒤에 켠다. 설정 항목은 K8s `recovery-controller/examples/config.kafka.example.json`을 본다.

## Secret: `platform/recovery-controller-aws`

키는 relocator와 같다 (`client.pem` · `client.key` · `trust_anchor_arn` · `profile_arn` · `role_arn`). `../relocator/README.md`를 본다.
역할 · profile은 IaC `output base -- workloads`의 `recovery`, 인증서 CN은 `devoops-prod-recovery`다.
