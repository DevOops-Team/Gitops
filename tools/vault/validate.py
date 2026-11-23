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
    for path in ['common', 'backend-db', 'collector-db', 'cloudflare-dns']:
        docs.extend(build(f'onprem/platform/vault/{path}'))
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
    cloudflare = [doc for doc in docs if doc['kind'] == 'VaultStaticSecret'
                  and doc['metadata']['name'] == 'cloudflare-dns-sync']
    assert len(cloudflare) == 1
    assert cloudflare[0]['metadata']['namespace'] == 'cert-manager'
    issuer = yaml.safe_load((ROOT / 'onprem/platform/cert-manager/issuer/clusterissuer.yaml').read_text())
    token_ref = issuer['spec']['acme']['solvers'][0]['dns01']['cloudflare']['apiTokenSecretRef']
    assert token_ref == {'name': cloudflare[0]['spec']['destination']['name'], 'key': 'api-token'}
    assert count == 9
    apps = [doc for doc in build('bootstrap/onprem/applications')
            if doc['kind'] == 'Application' and doc['metadata']['name'].startswith('gpu-vault-')]
    assert len(apps) == 5
    for application in apps:
        assert 'automated' not in application['spec'].get('syncPolicy', {})
        assert not application['metadata'].get('finalizers')
    print(f'Vault CRD {count}개 공식 chart {version} schema 검증 및 수동 인계 계약 통과')


if __name__ == '__main__':
    main()
