# fiap-lambda

Funções Python de autenticação por CPF ou e-mail/senha, emissão de JWT RS256 e adaptador de notificações por e-mail.

📚 **[Documentação principal — fiap-docs](https://github.com/FIAP-GRUPO05/fiap-docs)** · [Guia das Lambdas](https://github.com/FIAP-GRUPO05/fiap-docs/blob/main/guides/lambda.md)

## Requisitos

- Python 3.12 e pip para desenvolvimento e testes.
- Docker, Terraform e AWS CLI somente para as etapas administrativas descritas na documentação central.

## Testar localmente

Na raiz deste repositório:

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Os testes unitários usam dependências simuladas. Testes externos exigem um ambiente provisionado e dados de teste; sem configuração, ficam explicitamente ignorados.

As funções são handlers Lambda, não um servidor HTTP local. Rotas de autenticação, cobertura, empacotamento e integração estão no [guia central](https://github.com/FIAP-GRUPO05/fiap-docs/blob/main/guides/lambda.md).
Antes de qualquer operação AWS, consulte o [estado da infraestrutura](https://github.com/FIAP-GRUPO05/fiap-docs/blob/main/operations/infrastructure-state.md).
