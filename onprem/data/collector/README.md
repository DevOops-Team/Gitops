# collector (수집기)

관리 클러스터 `data-system/collector`, Pod 1개. 로직은 Data `collector/`(김현수), 배포는 여기서 한다 (GPU-178).
Kafka 토픽 5개를 읽어 데이터 DB(`172.30.0.50`, `gpuf_data`)의 `data` 스키마에 저장한다.

## 미리 필요한 것

**1. Secret `data-system/collector-db`** (DB 계정 `data_collector` 비밀번호, Git 밖)

```shell
kubectl -n data-system create secret generic collector-db --from-literal=PGPASSWORD=... \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n data-system rollout restart deployment/collector   # 비밀번호를 바꿨을 때
```

**2. DB `pg_hba.conf`: 워커 노드 IP 허용** (db VM, `SELECT pg_reload_conf();`)

Pod가 DB로 나가는 트래픽은 **워커 노드 IP로 바뀌어** 도착한다 (Pod 대역 10.233.x.x가 아님).

```text
host gpuf_data data_collector 172.30.0.21/32 scram-sha-256
host gpuf_data data_collector 172.30.0.22/32 scram-sha-256
host gpuf_data data_collector 172.30.0.23/32 scram-sha-256
```

없으면 로그에 `no pg_hba.conf entry for host "172.30.0.2x"`가 나오고, 사건은 Kafka에 쌓인 채 저장되지 않는다 (재시도 반복).

## 확인

```shell
kubectl -n data-system logs deploy/collector                  # 저장 · 커밋 로그, DB 연결 오류 없음
# Kafka VM에서: 컨슈머 그룹 data-collector의 LAG이 0 근처
/opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server 172.30.0.40:9092 --describe --group data-collector
```

1대로 둔다: 멈춰도 사건은 Kafka에 7일 남고 다시 뜨면 이어서 저장한다. 여러 대는 파생 갱신의 동시성이 보장되지 않는다.
