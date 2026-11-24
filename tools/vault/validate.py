"""Vault 매니페스트를 공식 고정 chart의 CRD schema와 인계 안전 계약으로 검증한다.

클러스터 접속 없음. 필요: PyYAML, jsonschema, kustomize 또는 kubectl.
"""
import io
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[2]


def build(path):
    command = ['kustomize', 'build'] if shutil.which('kustomize') else ['kubectl', 'kustomize']
    output = subprocess.check_output(command + [str(ROOT / path)], text=True)
    return [doc for doc in yaml.safe_load_all(output) if doc]


def main():
    app = yaml.safe_load((ROOT / 'bootstrap/onprem/applications/gpu-vault-operator.yaml').read_text())
    source = app['spec']['sources'][0]
    assert source['repoURL'] == 'https://helm.releases.hashicorp.com'
    version = source['targetRevision']
    url = f'https://helm.releases.hashicorp.com/vault-secrets-operator-{version}.tgz'
    with urllib.request.urlopen(url, timeout=30) as response:
        chart = response.read()
    schemas = {}
    with tarfile.open(fileobj=io.BytesIO(chart), mode='r:gz') as archive:
        for member in archive.getmembers():
            if '/crds/' not in member.name or not member.name.endswith(('.yaml', '.yml')):
                continue
            stream = archive.extractfile(member)
            if stream is None:
                continue
            for crd in yaml.safe_load_all(stream):
                if not crd or crd.get('kind') != 'CustomResourceDefinition':
                    continue
                for entry in crd['spec']['versions']:
                    schemas[(crd['spec']['names']['kind'], entry['name'])] = entry['schema']['openAPIV3Schema']

    docs = []
    for path in ['common', 'backend-db', 'collector-db', 'cloudflare-dns', 'worker-kubeconfigs', 'ghcr-pull', 'backend-recovery-api']:
        docs.extend(build(f'onprem/platform/vault/{path}'))
    for path in ['connections', 'alertmanager', 'grafana', 'postgres-exporter', 'ghcr-pull']:
        docs.extend(build(f'monitoring/onprem/vault/{path}'))
    count = 0
    for doc in docs:
        if doc['apiVersion'].startswith('secrets.hashicorp.com/'):
            schema = schemas[(doc['kind'], doc['apiVersion'].split('/')[1])]
            jsonschema.Draft7Validator(schema).validate(doc)
            count += 1
        if doc['kind'] == 'VaultConnection':
            assert doc['spec']['address'] == 'https://172.30.0.81:8200'
            assert doc['spec']['skipTLSVerify'] is False
            assert doc['spec']['caCertSecretRef'] == 'vault-vm-ca'
        if doc['kind'] == 'VaultStaticSecret':
            assert doc['spec']['destination']['create'] is False
            assert doc['spec']['destination']['transformation']['excludeRaw'] is True
            assert not doc['spec'].get('rolloutRestartTargets')
            assert doc['spec']['path'] == f"onprem/{doc['metadata']['namespace']}/{doc['spec']['destination']['name']}"
        assert doc['kind'] not in ['Secret', 'Deployment', 'StatefulSet']
        if doc['kind'] == 'ClusterRole':
            assert doc['rules'] == [{'apiGroups': ['authentication.k8s.io'], 'resources': ['tokenreviews'], 'verbs': ['create']}]
    recovery = [d for d in docs if d['kind'] == 'VaultStaticSecret'
                and d['metadata']['name'] == 'backend-recovery-api']
    assert len(recovery) == 1
    assert recovery[0]['metadata']['namespace'] == 'platform'
    assert recovery[0]['spec']['vaultAuthRef'] == 'backend-recovery-api-auth'
    assert recovery[0]['spec']['refreshAfter'] == '60s'
    cloudflare = [doc for doc in docs if doc['kind'] == 'VaultStaticSecret'
                  and doc['metadata']['name'] == 'cloudflare-dns-sync']
    assert len(cloudflare) == 1
    assert cloudflare[0]['metadata']['namespace'] == 'cert-manager'
    issuer = yaml.safe_load((ROOT / 'onprem/platform/cert-manager/issuer/clusterissuer.yaml').read_text())
    token_ref = issuer['spec']['acme']['solvers'][0]['dns01']['cloudflare']['apiTokenSecretRef']
    assert token_ref == {'name': cloudflare[0]['spec']['destination']['name'], 'key': 'api-token'}
    expected = {'eks-a-kubeconfig', 'eks-a-relocator-kubeconfig',
                'eks-b-kubeconfig', 'eks-b-relocator-kubeconfig'}
    worker_secrets = [d for d in docs if d['kind'] == 'VaultStaticSecret'
                      and d['metadata']['namespace'] == 'kueue-system']
    assert {d['spec']['destination']['name'] for d in worker_secrets} == expected
    assert len(worker_secrets) == 4
    for d in worker_secrets:
        name = d['spec']['destination']['name']
        assert d['spec']['vaultAuthRef'] == name + '-sync'
        assert d['spec']['refreshAfter'] == '60s'
    ghcr = [d for d in docs if d['kind'] == 'VaultStaticSecret'
            and d['spec']['destination']['name'] == 'ghcr-pull']
    assert len(ghcr) == 3
    assert {d['metadata']['namespace'] for d in ghcr} == {'platform', 'data-system', 'monitoring'}
    for d in ghcr:
        assert d['spec']['vaultAuthRef'] == 'ghcr-pull-sync'
        assert 'type' not in d['spec']['destination']  # create:false로 기존 타입 유지
        assert not d['spec']['destination'].get('overwrite', False)
    auths = [d for d in docs if d['kind'] == 'VaultAuth'
             and d['metadata']['name'] == 'ghcr-pull-sync']
    assert len(auths) == 3
    assert {d['metadata']['namespace'] for d in auths} == {'platform', 'data-system', 'monitoring'}
    for d in auths:
        assert d['spec']['vaultConnectionRef'] == 'vault-vm'
        assert d['spec']['kubernetes']['role'] == d['metadata']['namespace'] + '-ghcr-pull-sync'
    monitoring = [d for d in docs if d.get('metadata', {}).get('namespace') == 'monitoring']
    syncs = [d for d in monitoring if d['kind'] == 'VaultStaticSecret']
    assert {d['spec']['destination']['name'] for d in syncs} == {
        'alertmanager-secrets', 'grafana-secrets', 'postgres-exporter-secrets', 'ghcr-pull'}
    assert len(syncs) == 4
    assert not any(d['spec']['destination']['name'].endswith('-s3-cert') for d in syncs)
    for d in monitoring:
        if d['kind'] == 'VaultAuth':
            assert d['spec']['mount'] == 'monitoring'  # separate API/CA from auth/onprem
            assert d['spec']['kubernetes']['role'] == 'monitoring-' + d['metadata']['name']
    service_accounts = {d['metadata']['name'] for d in monitoring if d['kind'] == 'ServiceAccount'}
    assert service_accounts == {d['spec']['vaultAuthRef'] for d in syncs}
    binding = next(d for d in docs if d['kind'] == 'ClusterRoleBinding'
                   and d['metadata']['name'] == 'vault-monitoring-tokenreview')
    assert {s['name'] for s in binding['subjects']} == service_accounts
    assert all(s['namespace'] == 'monitoring' for s in binding['subjects'])
    project = yaml.safe_load((ROOT / 'bootstrap/onprem/project-monitoring-vault.yaml').read_text())
    assert {d['name'] for d in project['spec']['destinations']} == {'monitoring'}
    assert {d['namespace'] for d in project['spec']['destinations']} == {
        'monitoring', 'vault-secrets-operator-system'}
    assert count == 33
    apps = [doc for doc in build('bootstrap/onprem/applications')
            if doc['kind'] == 'Application' and doc['metadata']['name'].startswith(
                ('gpu-vault-', 'gpu-monitoring-vault-'))]
    assert len(apps) == 14
    for application in apps:
        assert 'automated' not in application['spec'].get('syncPolicy', {})
        assert not application['metadata'].get('finalizers')
        if application['metadata']['name'].startswith('gpu-monitoring-vault-'):
            assert application['spec']['destination']['name'] == 'monitoring'
            assert application['spec']['project'] == 'gpu-monitoring-vault'
    remote_operator = next(a for a in apps if a['metadata']['name'] == 'gpu-monitoring-vault-operator')
    assert remote_operator['spec']['sources'][0]['targetRevision'] == version
    remote_values = yaml.safe_load((ROOT / 'monitoring/onprem/vault/operator/values.yaml').read_text())
    assert remote_values['defaultVaultConnection']['enabled'] is False
    print(f'Vault CRD {count}개 공식 chart {version} schema 검증 및 수동 인계 계약 통과')


if __name__ == '__main__':
    main()
