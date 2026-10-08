# fiap-lambda

Lambdas e API Gateway da oficina.

- **lambda-email** (`codeemail/`): envia e-mails via SMTP, invocada pela API.
- **lambda-token** (`codetoken/`): mantém o login administrativo por e-mail/senha (bcrypt) na tabela `users` e autentica Customers por CPF na tabela `customers`. Ambos emitem JWT **RS256**.
- **API Gateway HTTP** (`api-gateway.tf`): `POST /auth/login` e `POST /auth/customer` chegam à lambda-token sem authorizer. As rotas públicas da API passam direto; todo o resto exige um token válido, checado pelo authorizer JWT nativo.

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

## Autenticação de Customer por CPF

`POST /auth/customer` recebe CPF com ou sem pontuação. A Lambda valida os dígitos
verificadores, normaliza para 11 dígitos e consulta `customers.cnpj_cpf` com query
parametrizada. Apenas Customers com status `ACTIVE` recebem token. CPF inválido retorna
`400`, cadastro inexistente `401` e Customer inativo `403`; a resposta de cadastro
inexistente é genérica para não expor a existência de uma conta.

```json
{
  "cpf": "<CPF-DE-TESTE>"
}
```

Resposta em caso de sucesso:

```json
{
  "accessToken": "<JWT-RS256>",
  "expiresAt": 0,
  "tokenType": "Bearer"
}
```

O token mantém `iss`, `aud`, `sub`, `iat`, `exp` e `roles`; para Customer, `roles` contém
`CUSTOMER`, e `sub`/`customerId` contêm o UUID do cadastro. O CPF não é incluído no JWT.
O fluxo é: CPF → Lambda → PostgreSQL (`customers`) → JWT RS256/JWKS. A migration Flyway
normaliza documentos existentes, adiciona status `ACTIVE` e uma constraint de unicidade.
Ela aborta sem apagar dados se encontrar documentos inválidos ou duplicados após
normalização; resolva esses registros e confirme que a API aplicou a migration antes de
habilitar o novo fluxo.

## Deploy

Ordem entre os repositórios: **fiap-k8s → fiap-database → fiap-lambda → fiap-k8s de novo**.

1. `fiap-k8s` e `fiap-database`: `terraform apply` (cria as tags de subnet e o `postgres-internal`).
2. Implante/inicie a aplicação para que o Flyway aplique as migrations antes de habilitar a autenticação de Customer.
3. Gere as chaves (uma vez; rodar de novo invalida os tokens já emitidos):
   ```bash
   python3 keys/generate-keys.py
   ```
4. Monte a layer com wheels de Linux (as libs têm partes compiladas):
   ```bash
   rm -rf layer/python
   pip install -r requirements.txt -t layer/python \
     --platform manylinux2014_x86_64 --only-binary=:all: \
     --python-version 3.11 --implementation cp
   ```
5. Preencha o `terraform.tfvars` a partir do `terraform.tfvars.example`:
   - `db_host`: `kubectl -n prod get svc postgres-internal -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'`
   - `api_url`: `terraform output api_public_url` no fiap-k8s
6. `terraform apply` aqui.
7. Copie `terraform output jwt_issuer` para `jwtIssuer` no `terraform.tfvars` do fiap-k8s e aplique lá. Os pods da API reiniciam sozinhos e passam a aceitar só os tokens RS256.

## Testando

```bash
URL=$(terraform output -raw api_gateway_url)

TOKEN=$(curl -s -X POST "$URL/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"admin@oficina.com","password":"sua-senha"}' | jq -r .accessToken)

curl -i "$URL/service-orders" -H "Authorization: Bearer $TOKEN"   # 200
curl -i "$URL/service-orders"                                      # 401 (barrado no gateway)
```

Para testar o fluxo de Customer, faça `POST "$URL/auth/customer"` com `{"cpf":"<CPF-DE-TESTE>"}` e use o campo `accessToken` em `GET "$URL/service-orders/my-orders"` como `Authorization: Bearer <accessToken>`. Não use CPF real em exemplos, logs ou testes compartilhados.

Execute os testes da Lambda com `python -m unittest discover -s tests -p "test_*.py"`.
