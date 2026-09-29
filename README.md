# fiap-lambda

Lambdas e API Gateway da oficina.

- **lambda-email** (`codeemail/`): envia e-mails via SMTP, invocada pela API.
- **lambda-token** (`codetoken/`): login. Confere e-mail e senha (bcrypt) na tabela `users` e devolve um JWT **RS256**.
- **API Gateway HTTP** (`api-gateway.tf`): porta de entrada pública. `POST /auth/login` vai para a lambda-token; as rotas públicas da API passam direto; todo o resto exige um token válido, checado pelo authorizer JWT nativo.

## Como o token é validado

```
keys/private.pem ──► bucket privado  fiap-jwt-keys-<conta>   (lido pela lambda-token para assinar)
keys/jwks.json   ──► bucket público  fiap-jwt-jwks-<conta>/.well-known/
                       ├── openid-configuration  (issuer + jwks_uri)
                       └── jwks.json             (chave pública)
```

O `issuer` do token é a URL HTTPS do bucket público. O authorizer do API Gateway busca
`{issuer}/.well-known/openid-configuration`, encontra o `jwks_uri` e valida assinatura,
`iss`, `aud` e `exp`. A API Spring valida de novo com o mesmo JWKS, para quem chamar o
Load Balancer direto.

A lambda-token roda dentro da VPC do EKS e alcança o Postgres pelo service
`postgres-internal` (Load Balancer interno, criado no fiap-database). Para ler a chave
no S3, a VPC recebe um VPC endpoint de S3.

## Deploy

Ordem entre os repositórios: **fiap-k8s → fiap-database → fiap-lambda → fiap-k8s de novo**.

1. `fiap-k8s` e `fiap-database`: `terraform apply` (cria as tags de subnet e o `postgres-internal`).
2. Gere as chaves (uma vez; rodar de novo invalida os tokens já emitidos):
   ```bash
   python3 keys/generate-keys.py
   ```
3. Monte a layer com wheels de Linux (as libs têm partes compiladas):
   ```bash
   rm -rf layer/python
   pip install -r requirements.txt -t layer/python \
     --platform manylinux2014_x86_64 --only-binary=:all: \
     --python-version 3.11 --implementation cp
   ```
4. Preencha o `terraform.tfvars` a partir do `terraform.tfvars.example`:
   - `db_host`: `kubectl -n prod get svc postgres-internal -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'`
   - `api_url`: `terraform output api_public_url` no fiap-k8s
5. `terraform apply` aqui.
6. Copie `terraform output jwt_issuer` para `jwtIssuer` no `terraform.tfvars` do fiap-k8s e aplique lá. Os pods da API reiniciam sozinhos e passam a aceitar só os tokens RS256.

## Testando

```bash
URL=$(terraform output -raw api_gateway_url)

TOKEN=$(curl -s -X POST "$URL/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"admin@oficina.com","password":"sua-senha"}' | jq -r .accessToken)

curl -i "$URL/service-orders" -H "Authorization: Bearer $TOKEN"   # 200
curl -i "$URL/service-orders"                                      # 401 (barrado no gateway)
```
