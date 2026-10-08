<a id="topo"></a>

# Auditoria · onde está cada trilha e como perguntar a ela

<!-- nav:start -->
[Home](../README.md) | [← Monitoramento e Healthcheck](09_monitoramento_e_healthcheck.md) | [Ingestão →](11_ingestao.md)
<!-- nav:end -->

> Auditoria aqui é a pergunta que um auditor faz depois do fato: quem entrou, quem alterou o quê, quem exportou, o que foi apagado, o que o pipeline rodou, quem pode entrar no warehouse, quem pediu o quê à API. O pipeline grava tudo isto desde as primeiras versões, em quatro lugares e sem dado pessoal; este documento diz onde cada trilha mora, quais são as treze perguntas prontas (`rh_fictalent.trilha`), como respondê-las em tabela ou em relatório, e o que a base de hoje responde. É diferente da **auditoria de qualidade** da bronze ([Bronze](12_bronze.md), [Catálogo de achados](13_catalogo_de_achados.md)), que pergunta se o dado está certo; esta pergunta quem fez o quê. Todo número foi medido na base completa em 08/10/2026.

## 1. Onde cada trilha mora

| trilha | o que registra | onde | desde |
|---|---|---|---|
| log de auditoria do sistema do cliente | cada `LOGIN`, `CRIAR`, `EDITAR`, `EXCLUIR` e `EXPORTAR` feito por um usuário interno, com módulo, tabela e instante | `silver.seguranca.log_auditoria`, com `silver.seguranca.usuario`, `usuario_perfil` e `perfil` | v0.4.0 (gerador, etapa 6); na silver desde a v0.6.0 |
| matriz de permissão | o que cada perfil pode em cada módulo; a marca `q_seg_01` no log diz quando a ação não tinha permissão vigente | `silver.seguranca.permissao`; a marca vem do [catálogo, SEG-01](13_catalogo_de_achados.md#seg-01) | v0.6.0 |
| trilha de exclusões da réplica | cada `DELETE` na réplica, pelo gatilho `BEFORE DELETE` de cada tabela: banco, tabela, id, instante, usuário de banco | `meta.exclusao_auditoria`, na bronze (não passa pela silver: não é dado do cliente a conformar) | v0.2.0; na bronze desde a v0.5.0 |
| execuções do pipeline | cada execução e cada passo do Dagster: job, status, duração, linhas, erro | `observabilidade.execucao` e `execucao_passo`, no warehouse, gravadas pelos sensores de fim de execução | v0.3.0 |
| descartes de dado pessoal | cada descarte na bronze: tabela, linhas eliminadas e vencidas, regra, e o efeito em cada regra da silver (a cadeia de custódia) | `lgpd.descarte`, no warehouse | v0.6.0 |
| quem lê o warehouse | os papéis do banco, o perfil de cada um, as filiais, se a API o assume | `pg_roles`, `pg_auth_members`, `acesso.filial_do_papel` | v0.7.0 |
| a API | cada token (só o hash, o papel, a validade) e cada pedido a `/v1` (papel ou nulo sem token válido, caminho, código) | `acesso.token` e `acesso.pedido`, no warehouse | v1.0.0 |

Nenhuma trilha tem dado pessoal. Na silver o login virou chave (HMAC) de propósito, para a auditoria de acesso poder agrupar por usuário sem saber quem é ([Silver, seção 3](14_silver.md)), e o valor alterado (`valor_anterior`, `valor_novo` do log) não entra, porque pode carregar o dado pessoal da linha alterada. O token da API é guardado só como SHA-256. O que se vê é a chave, o perfil, a filial, o módulo, a ação, o instante.

## 2. As treze perguntas prontas

`rh_fictalent.trilha.consultas` declara cada pergunta com a fonte, o grão da resposta e o SQL. Sete rodam no lake, pelo DuckDB, sobre a silver de segurança (só linhas vivas) e a trilha de exclusões da bronze; seis rodam no warehouse, como o administrador. Os parâmetros são sempre a janela (`desde`, `ate`).

| consulta | pergunta | fonte |
|---|---|---|
| `acessos_por_perfil_e_mes` | quem entrou no sistema, por perfil e filial, mês a mês | lake |
| `usuarios_ativos_sem_acesso` | que contas ativas não entram há mais de 90 dias, ou nunca entraram | lake |
| `alteracoes_por_modulo_e_mes` | o que foi criado, editado e excluído, por módulo e tabela, mês a mês | lake |
| `acoes_sem_permissao` | que ações foram feitas sem permissão vigente (SEG-01), por quem e onde | lake |
| `exportacoes_por_usuario_e_mes` | quem exportou planilhas, quanto e de que módulo, mês a mês | lake |
| `acoes_fora_do_horario` | que alterações e exportações aconteceram antes das 7h, depois das 20h ou no fim de semana | lake |
| `exclusoes_na_replica` | o que foi apagado na réplica, por banco, tabela e usuário de banco, mês a mês | lake |
| `execucoes_por_job` | o que rodou no pipeline, com que resultado e em quanto tempo, por job | warehouse |
| `passos_que_falharam` | que passos falharam, em que execução, com que erro | warehouse |
| `descartes_lgpd` | que descartes de dado pessoal foram feitos, quando, de que tabela e por que regra | warehouse |
| `papeis_do_warehouse` | quem pode entrar no warehouse e com que perfil e filiais | warehouse |
| `tokens_da_api` | que tokens da API existem, de quem, com que validade e último uso (nunca o token) | warehouse |
| `pedidos_da_api_por_dia` | quem pediu o quê à API, dia a dia, e quantas vezes foi recusado | warehouse |

O usuário aparece sempre pelo mesmo recorte sem identidade (a chave do login, o perfil vigente, a filial), que é uma view temporária criada ao abrir e lida pelas sete consultas do lake. A pergunta "quem é essa chave" só o cliente responde, no sistema dele, com o segredo da pseudonimização: a auditoria aponta a conta; a identificação é ato do controlador.

## 3. Como perguntar

Da raiz do projeto, com a plataforma de pé e o `.env` preenchido:

```bash
.venv/bin/python -m rh_fictalent.trilha --lista
```

```bash
.venv/bin/python -m rh_fictalent.trilha --consulta acoes_sem_permissao --desde 2025-01-01
```

```bash
.venv/bin/python -m rh_fictalent.trilha --consulta execucoes_por_job --dias 30
```

`--desde` e `--ate` recebem datas; `--dias N` é o atalho para os últimos N dias. Para um relatório inteiro, todas as consultas em CSV numa pasta, com um `relatorio.md` que diz o que cada arquivo responde e quantas linhas tem:

```bash
.venv/bin/python -m rh_fictalent.trilha --relatorio dados/auditoria/trilha
```

O relatório é o que se entrega a um auditor: ele lê a pergunta, abre o CSV e não precisa de acesso a banco nenhum. A pasta não tem dado pessoal e pode ser versionada ou enviada.

## 4. O que a base de hoje responde

A base é sintética, e o gerador plantou nela uma história de acesso ([Entendimento do Negócio](01_entendimento_negocio.md), [Arquitetura, seção 3](03_arquitetura.md)): o autoatendimento em três níveis, a matriz de permissão por módulo, e exportações de planilha que crescem com a degradação da empresa. As perguntas prontas contam essa história sem saber que ela foi plantada, e isso é o teste delas.

**Quem entra.** 35.114 logins em 105 meses, por perfil e filial; nenhuma conta ativa sem acesso há mais de 90 dias.

**Ações sem permissão vigente.** 22 combinações de usuário, módulo e ação somam **4.092 eventos sem permissão** de 2018 a 2026. O grosso é exportação: assistentes exportando da folha (1.629 vezes, sete contas) e do comercial (1.475 vezes, duas contas), coordenadores exportando da folha (300) e do comercial (210). Há também criações e edições no comercial por quem não tinha o direito, inclusive por sócios (43 eventos), e **uma conta sem perfil vigente que exportou a folha 127 vezes**: a vigência do perfil acabou e a conta continuou ativa e em uso. É o achado SEG-01 do catálogo respondido por quem, de onde e quando; na base real do cliente, cada linha dessa tabela seria uma conversa.

**Exportações.** Crescem ano a ano: 372 em 2018, 831 em 2021, 2.615 em 2023, 5.121 em 2024, 7.296 em 2025 (e 5.536 até setembro de 2026). É a degradação vista por outro ângulo: quando o sistema deixa de responder às perguntas, as pessoas levam o dado para a planilha.

**Fora do horário.** 14.497 ações de 24 usuários fora do horário comercial, todas em fim de semana, nenhuma de madrugada: a operação de terceirização trabalha sábado, e a pergunta separa o hábito do negócio do que seria estranho.

**Exclusões na réplica.** Nenhuma até hoje. A trilha existe, os 75 gatilhos estão armados ([Manual de Operação, seção 3](08_manual_de_operacao.md)), e a resposta vazia também é informação: o que a bronze marca como excluído veio de outra via (o descarte da LGPD, que não apaga linha, apaga dado pessoal e registra em `lgpd.descarte`).

**O pipeline e o warehouse.** Dez combinações de job e status, dois passos que falharam no histórico (os das rodadas de desenvolvimento), quatro descartes registrados, três papéis no warehouse (o `api`, o `grafana_leitor` e o sócio cadastrado pelo Tiago), dois tokens e 23 linhas de pedidos à API por dia, papel e caminho, com os 401 sem token e os 403 do banco contados.

## 5. O que ainda não existe

- **Quem acessou o warehouse pelo DBeaver ou pelo Power BI.** O Postgres não registra consultas por padrão; os pedidos pela API ficam em `acesso.pedido`, os diretos ao banco não. Ligar `log_statement` ou `pgaudit` é decisão de produção, com custo de disco.
- **Quem leu o lake.** O SeaweedFS tem log de acesso ao S3, mas ele não é recolhido.
- **A auditoria do próprio administrador.** Quem roda a CLI com `DW_ADMIN_PASSWORD` não deixa trilha além do histórico do shell. Em produção, o administrador é uma conta nominal e o banco registra as sessões dela.
- **Alertas sobre a trilha.** Uma ação sem permissão ou um pico de exportações não acendem nada no Grafana; as perguntas são respondidas sob demanda. Um painel da trilha é da fase de consumo.

---

[Início](#topo)
