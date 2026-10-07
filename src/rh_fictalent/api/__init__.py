"""A API REST dos indicadores: a gold servida pelo warehouse, com o banco decidindo quem vê o quê.

Quatro decisões, aprovadas em 06/10/2026 (ADR-0009 e o desenho do card 8.1):

1. **A API lê o warehouse, e o banco decide quem vê o quê.** Cada consumidor é um papel do
   Postgres criado pelo rito do `docs/17` (o perfil de negócio e as filiais). A API entra com
   o usuário `api`, membro desses papéis, e a cada pedido faz `SET LOCAL ROLE <papel>`: o DCL
   e o RLS da v0.7.0 valem sem uma linha de código a mais, e o acesso negado é o do banco.
2. **Token por consumidor, guardado como senha.** `acesso.token` (hash SHA-256 do token, o
   papel, a validade) só o administrador escreve; a API só pergunta "de quem é este hash" por
   uma função `SECURITY DEFINER`. Os tokens reais o administrador gera e cadastra; este código
   nunca os vê em claro, só os recebe no cabeçalho.
3. **O contrato `/v1`, poucos e conhecidos:** o resultado de uma filial, o Pareto dos clientes
   do ano, o ponto de um posto no mês, o funil por trimestre e o mercado; modelos pydantic,
   OpenAPI gerada do código; `/saude` sem token.
4. **Um serviço `api` no Compose**, só em `127.0.0.1`, com healthcheck no `/saude`.
"""
