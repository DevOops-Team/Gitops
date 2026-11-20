# recovery-controller (복구 컨트롤러)

관리 클러스터 `platform/recovery-controller`. 로직은 K8s `recovery-controller`(한송이), 배포는 여기서 한다 (GPU-173 · GPU-222).

온프레 overlay는 Pod 3개 중 Lease 리더 하나가 Kafka 사건을 수신한다. **현재는 observe로 수신·DynamoDB inbox 기록만 시험하며, 새 복구 동작을 실행하지 않는다.** base의 replicas 0·event_source disabled는 유지한다. Argo CD는 Gitops main을 참조하므로 feature 브랜치 push만으로 배포되지는 않는다.

## 온프레 설정

`overlays/onprem/config.json`을 `/etc/recovery/config.json`으로 마운트한다.

| 항목 | 값 |
|---|---|
| 입력 / 모드 / 실행 | `event_source: kafka` / `mode: observe` / `execution_enabled: false` |
| 스케줄링 정책 확인 | `scheduler_policy_confirmed: false` (실제 실행 전 재확인) |
| 리전 / 복구 테이블 / 펜싱 | `us-east-2` / `devoops-prod-recovery` / `devoops-prod-fencing` |
| 브로커 | `172.30.0.40:9092,172.30.0.41:9092,172.30.0.42:9092` |
| 입력 / 출력 | `gpu.fault` + `job.lifecycle` / `recovery.action` |
| consumer group / 학습 namespace | `recovery-controller-v1` / `training` |

`job.lifecycle`은 코드에서 고정 구독한다. Kafka PLAINTEXT 구성에서는 인증 Secret이 없어도 되며, 인증 도입 시 기존 `recovery-controller-credentials`의 `KAFKA_CLIENT_CONFIG_JSON`을 사용한다. 기존 Roles Anywhere 인증 사이드카·Secret, RECOVERY_POD_UID, Lease·RelocationRequest RBAC와 이미지 tag/digest는 유지한다.

설정 변경 시 Pod가 재시작해 새 파일을 읽도록 overlay의 `devoops/config-sha256`을 설정한다. config.json 수정 시 아래 SHA-256으로 annotation도 갱신한다.

```shell
shasum -a 256 onprem/controllers/recovery-controller/overlays/onprem/config.json
kubectl kustomize onprem/controllers/recovery-controller/overlays/onprem
```

## 적용 전 확인

- IaC main의 `terraform/live/base/storage.tf`에는 복구 테이블(PK `pk` 문자열), `onprem-roles.tf`에는 recovery 역할의 해당 테이블 GetItem/PutItem/UpdateItem/Scan이 있다. fencing GetItem/UpdateItem은 유지한다. 실제 생성·정책 적용·Pod의 접근 성공은 별도로 확인한다. 이름은 `terraform/run.sh output base -- recovery_table`로 대조한다.
- Secret `platform/recovery-controller-aws`와 인증 사이드카가 정상인지, Pod에서 Kafka 브로커 advertised 주소와 DynamoDB에 접근 가능한지 확인한다. observe도 영속 inbox가 필요하다.
- 기존 consumer group과 offset은 보존한다. offset 없는 그룹은 earliest로 과거 사건을 읽을 수 있다. 기존 OBSERVED 사건은 execute 전환만으로 자동 재실행되지 않는다.
- Watchdog·스트래글러 자동 이전·fencing 진행 증거 입력은 이번 수신 시험에서 활성화하지 않는다. 진행 중인 relocator 작업이 있다면 observe 전환이 이를 취소한다고 가정하지 않고 실제 상태를 따로 확인한다.

## observe 시험

```shell
kubectl -n platform rollout status deployment/recovery-controller
kubectl -n platform get lease recovery-controller -o yaml
kubectl -n platform logs deployment/recovery-controller -c controller --tail=100
```

Pod의 `/healthz`·`/readyz`에서 event_source=kafka·execution_enabled=false를 확인한다. Lease 대기 replica도 ready일 수 있으므로 리더의 Kafka 연결·worker 상태를 함께 확인한다.
전용 시험의 새 event_id로 입력하고, `devoops-prod-recovery`의 inbox 기록·OBSERVED 상태와 이 시험으로 생성된 새 RelocationRequest·세대 증가가 없는지 확인한다. ckpt-init/job.failed 등 lifecycle 분기는 별도 사건 처리 규칙을 따르므로 모든 lifecycle 입력이 OBSERVED가 된다고 가정하지 않는다. 결과 기록·Kafka 전송 성공은 학습 복구 성공과 구분한다.

실제 복구 시험은 별도 합의 후 mode=execute·execution_enabled=true·scheduler_policy_confirmed=true 및 checksum을 변경한다. 그 전에 원본 JobSet 등록, relocator·CRD·워커 연결, 신뢰된 새 배치·복원·첫 step 증거와 이미지 기능을 확인한다. 수신 시험에서 처리된 사건은 새 시험 사건으로 대체한다.

## Secret: platform/recovery-controller-aws

키는 relocator와 같다 (`client.pem` · `client.key` · `trust_anchor_arn` · `profile_arn` · `role_arn`). `../relocator/README.md`를 본다. 역할·profile은 IaC `output base -- workloads`의 recovery, 인증서 CN은 `devoops-prod-recovery`다. 개인 키와 인증서는 Git에 넣지 않는다.
