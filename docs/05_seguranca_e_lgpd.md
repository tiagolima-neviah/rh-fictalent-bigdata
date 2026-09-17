<a id="topo"></a>

# Segurança e LGPD · o que protege o quê, e como conferir

<!-- nav:start -->
[Home](../README.md) | [← Modelo de Dados](04_modelo_dados_staging.md) | [Instalação e Reprodução →](07_instalacao_e_reproducao.md)
<!-- nav:end -->

> Este documento consolida, num lugar só, cada controle de segurança e de proteção de dados do projeto: contra o que ele protege, onde está implementado e **o comando que prova que funciona**. O que ainda não existe aparece como previsto, com a versão em que entra. Nada aqui substitui o aviso do README: é um projeto de estudo, sem auditoria independente.

## 1. Postura

Os dados são **fictícios e sintéticos**: nenhuma pessoa real está neste repositório, então a LGPD não alcança o dado. Alcança o **desenho**: RH é o domínio do dado pessoal por excelência, e a arquitetura é a que um caso real exigiria. O que é de laboratório (chave de cifra em arquivo, senhas em `.env`, sem TLS entre containers na mesma máquina) está dito como tal, e o que mudaria em produção está na seção 5.

Dois regimes: repositório público é estudo; produto em cliente é repositório privado, com KMS, TLS, auditoria e contrato de tratamento de dados.

## 2. Modelo de ameaça, camada a camada

| ameaça | controle | onde | provado por |
|---|---|---|---|
| segredo no repositório | todo segredo vem do `.env` (nunca versionado); o compose se recusa a subir sem ele (`${VAR:?}`); gitleaks varre o histórico a cada PR | `compose.yaml`, `.gitignore`, CI | `tests/test_compose.py`, trilho `seguranca` da CI |
| serviço exposto na rede | toda porta publicada só em `127.0.0.1` | `compose.yaml` | `tests/test_compose.py` |
| escalada dentro do container | `no-new-privileges`; Dagster, Grafana e MySQL rodam sem root (uid 10001, 472, 999); imagens com versão exata | `compose.yaml`, `infra/dagster/Dockerfile` | `tests/test_compose.py`; `docker exec <container> id -u` |
| leitura do disco, volume ou backup da réplica | cifra em repouso de todos os tablespaces, redo, undo e binlog; chave mestra em keyring fora dos dados e do repositório | `staging/ddl`, `infra/mysql`, `compose.yaml` | `tests/test_cifra_aplicada.py`: CPF gravado não aparece no `.ibd` |
| usuário de banco lendo o que não deve | papéis por função na réplica: pipeline só lê; relatórios do cliente leem sem dado pessoal, coluna a coluna; replicação escreve o negócio e nada mais | `staging/ddl/13_papeis.sql` (gerado), `14_usuarios.sh` | `tests/test_dcl_aplicada.py`: passa quando o acesso indevido falha |
| exclusão sem rastro | gatilho `BEFORE DELETE` em toda tabela de negócio grava banco, tabela, id e usuário em `meta.exclusao_auditoria` | `staging/ddl/12_gatilhos_exclusao.sql` (gerado) | `tests/test_ddl_aplicada.py`: apaga e vê o rastro |
| dado pessoal sem classificação | etiqueta LGPD no comentário de cada coluna; dicionário gerado do banco com o inventário | `staging/ddl`, `docs/dicionario` | `tests/test_dicionario.py` |
| dependência ou imagem vulnerável | pip-audit sobre o lock, trivy no repositório, bandit no código | CI e `scripts/esteira.sh` | trilho `seguranca` da CI |
| painel de monitoramento aberto | Grafana sem acesso anônimo, sem cadastro, lendo os bancos com papel só de leitura | `compose.yaml`, `infra/grafana`, `infra/postgres/*` | `curl` anônimo devolve 401 (manual, seção 3) |

## 3. Como conferir, na sua máquina

Tudo de uma vez (réplica de pé):

```bash
bash scripts/esteira.sh
```

Peça por peça:

| garantia | comando | esperado |
|---|---|---|
| nenhuma porta na rede | `docker compose ps` | toda porta como `127.0.0.1:...` |
| ninguém é root | `for c in fictalent_dagster_web fictalent_grafana fictalent_mysql_staging; do docker exec $c id -u; done` | `10001`, `472`, `999` |
| relatório não lê CPF | `.venv/bin/pytest -q tests/test_dcl_aplicada.py` | todos passam |
| CPF não está em claro no disco | `.venv/bin/pytest -q tests/test_cifra_aplicada.py` | todos passam |
| exclusão deixa rastro | `.venv/bin/pytest -q tests/test_ddl_aplicada.py -k rastro` | passa |
| dicionário bate com o banco | `.venv/bin/pytest -q tests/test_dicionario.py` | todos passam |
| nenhum segredo no histórico | `docker run --rm -v "$PWD:/repo:ro" zricethezav/gitleaks:v8.21.2 detect --source /repo --no-banner` | `no leaks found` |
| Grafana fechado | `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3011/api/datasources` | `401` |

## 4. LGPD: princípio por princípio

| princípio (art. 6º) | como o projeto responde | onde |
|---|---|---|
| finalidade e adequação | a réplica existe para uma pergunta contratada (margem por cliente); o **mapa de escopo** diz que schema serve a que pergunta | [Arquitetura, seção 3](03_arquitetura.md) |
| necessidade (minimização) | **réplica parcial por pertinência** como regra da casa; relatórios do cliente só veem colunas sem dado pessoal; a gold não terá nome nem CPF | ADR-0001, `13_papeis.sql`, silver (v0.6.0) |
| segurança | cifra em repouso, controle de acesso por função, containers sem root, portas fechadas, CI de segurança | seção 2 |
| prevenção | tudo acima é verificado a cada PR, não uma vez | CI |
| transparência e prestação de contas | dicionário de dados com inventário de dado pessoal; ADRs com o porquê de cada escolha; trilha de exclusões; este documento | `docs/dicionario`, `docs/adr` |
| não discriminação | dado sensível (saúde) fica fora de qualquer indicador de pessoa; a gold mede postos, contratos e prazos, não pessoas | gold (v0.7.0) |

**Dado pessoal sensível.** O projeto tem quatro colunas de saúde (CID do afastamento, resultado do ASO, tipo e gravidade do acidente), etiquetadas `[LGPD:sensivel]`. Elas nunca chegam ao relatório do cliente nem à gold; servem só a indicadores agregados de absenteísmo e segurança, sem chave de pessoa.

**Direitos do titular.** Eliminação e correção acontecem no sistema do cliente e chegam à réplica pela replicação; a trilha de exclusões prova que a eliminação foi aplicada, e a marcação lógica na bronze preserva o histórico agregado sem manter o dado identificável (v0.6.0). Na silver, pessoa vira chave derivada, irreversível sem o segredo, que fica fora do repositório.

**Retenção.** Candidato não contratado tem prazo declarado em `cadastro.parametro`; o descarte é executado por job do Dagster e registrado (v0.6.0).

## 5. O que ainda não existe, e o que mudaria em produção

| item | versão | observação |
|---|---|---|
| pseudonimização na silver (chave derivada com segredo fora do repositório) | v0.6.0 | |
| job de retenção e descarte, com registro | v0.6.0 | |
| isolamento por filial no warehouse (RLS do Postgres) com teste | v0.7.0 | os leitores de BI vivem no warehouse, não na réplica |
| papéis de leitura por área no warehouse, sem dado pessoal | v0.7.0 | |
| token por consumidor e `/saude` na API | v1.0.0 | |
| backup e restauração da réplica **junto com o keyring** | v1.0.0 | sem o keyring o dado é irrecuperável |
| auditoria de acesso à réplica (quem consultou o quê) | v1.0.0 | o MySQL Community não tem plugin de auditoria; a decisão (log geral, proxy ou trilha na aplicação) entra com ADR |
| em produção: chave em KMS ou HSM, TLS entre serviços, senhas em cofre, contrato de tratamento de dados | fora deste repositório | o desenho é o mesmo; troca o backend |

## 6. Se algo vazar

| incidente | resposta |
|---|---|
| a chave mestra da réplica foi exposta | `ALTER INSTANCE ROTATE INNODB MASTER KEY` (manual, seção 8); a chave antiga deixa de abrir os tablespaces |
| a senha de um usuário de serviço vazou | troque no `.env` e rode `bash scripts/aplicar_ddl.sh`: as senhas de `pipeline`, `relatorios_cliente` e `replicador` acompanham o `.env` |
| a senha do root vazou | troque dentro do banco (`ALTER USER 'root'@'%' ...` e `'root'@'localhost'`) e depois no `.env` |
| um segredo entrou no git | o gitleaks barra o PR; se já foi mesclado, o segredo está comprometido: rotacione primeiro, reescreva o histórico depois |

---

[Início](#topo)
