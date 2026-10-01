<a id="topo"></a>

# Silver · a bronze conformada, pseudonimizada e com prestação de contas

<!-- nav:start -->
[Home](../README.md) | [← Catálogo de achados](13_catalogo_de_achados.md) | [Bibliografia →](bibliografia.md)
<!-- nav:end -->

> A silver é a camada que o resto do pipeline lê. Ela tem as mesmas 76 tabelas da [Bronze](12_bronze.md), linha a linha, com três mudanças: o dado pessoal sai ou vira chave, cada regra aprovada no [Catálogo de achados](13_catalogo_de_achados.md) acrescenta as suas colunas, e nada é publicado sem prova. Este documento explica o que ela faz, o que ela nunca faz, como cada tabela se prova sozinha e como a camada presta contas dos números que o catálogo aprovou. Todo número foi medido na base completa em 01/10/2026.

## 1. O que a silver é, e o que ela nunca faz

A silver tem o **mesmo grão da bronze**: uma linha da réplica, uma linha da silver, no mesmo arquivo por ano (`silver/<modulo>/<tabela>/ano=AAAA.parquet`). Quem conta linhas na silver conta as mesmas linhas da bronze. São 525 arquivos, 103 MB.

O que ela acrescenta é informação **ao lado** do dado, nunca no lugar dele. Um CPF que não passa no dígito verificador continua lá, agora com a marca que diz isso. A decisão do que fazer com a linha marcada (contar, descontar, mostrar os dois números) é da gold, que conhece a pergunta.

Por isso a silver tem uma lista curta de coisas que nunca faz, e ela vem do catálogo:

- **não funde** cadastros duplicados: marca o grupo e aponta o cadastro canônico;
- **não preenche** o que falta: ausência é informação;
- **não apaga** linha: a excluída e a descartada seguem, identificadas;
- **não corrige** o valor de origem: a correção é do cliente, no sistema dele;
- **não implementa** regra que o catálogo não aprovou.

A última é conferida por teste: a regra cuja entrada não está aprovada reprova a prestação de contas.

## 2. As colunas que as regras acrescentam

Das 40 entradas aprovadas do catálogo, **34 viram coluna na silver**. As outras seis são da gold ou só documentação, e o código guarda o motivo de cada uma (`FORA_DA_SILVER`, em `src/rh_fictalent/silver/regras.py`): a coluna nunca preenchida do endereço e o telefone repetido ficam como estão; os dois achados do consolidado gerencial e o do último acesso são série ou derivação da gold; o usuário sem vínculo com colaborador é decisão de modelagem do cliente.

Três convenções valem para todas as colunas novas:

- **`q_<codigo>`** é a marca de um achado, com o código da entrada do catálogo. `TRUE` quer dizer que a linha tem o achado; `FALSE`, que foi avaliada e não tem; **nulo, que não foi avaliada** (seção 5).
- **Coluna derivada** tem nome próprio e convive com a original: `situacao_derivada` ao lado de `status`, `dt_prevista_termino_derivada` ao lado de `dt_prevista_termino`.
- **As colunas novas vêm depois das originais**, na ordem do catálogo.

| tabela da silver | colunas novas | regra | o que o catálogo chama de |
|---|---|---|---|
| `cadastro.funcao` | `q_cad_01` | [CAD-01](13_catalogo_de_achados.md#cad-01) | Funções sem o código de ocupação |
| `comercial.contrato` | `situacao_derivada`, `q_com_01` | [COM-01](13_catalogo_de_achados.md#com-01) | Contrato vencido que continua ativo |
| `comercial.posto` | `q_com_02` | [COM-02](13_catalogo_de_achados.md#com-02) | Postos que podem ser o mesmo posto |
| `comercial.contrato_ocorrencia` | `q_com_03` | [COM-03](13_catalogo_de_achados.md#com-03) | Reclamação depois do fim do contrato |
| `ats.candidato` | `q_ats_01`, `grupo_pessoa`, `cadastro_canonico` | [ATS-01](13_catalogo_de_achados.md#ats-01) | A mesma pessoa cadastrada mais de uma vez |
| `ats.candidato` | `q_ats_02` | [ATS-02](13_catalogo_de_achados.md#ats-02) | Mesmo nome e nascimento, CPFs diferentes |
| `ats.candidato` | `q_ats_03` | [ATS-03](13_catalogo_de_achados.md#ats-03) | CPF inválido |
| `ats.candidato` | `q_ats_04` | [ATS-04](13_catalogo_de_achados.md#ats-04) | Data de nascimento impossível |
| `ats.candidato` | `q_ats_05` | [ATS-05](13_catalogo_de_achados.md#ats-05) | Nome escrito de vários jeitos |
| `ats.candidato` | `q_ats_06` | [ATS-06](13_catalogo_de_achados.md#ats-06) | Candidato sem CPF |
| `ats.candidato_experiencia` | `q_ats_08` | [ATS-08](13_catalogo_de_achados.md#ats-08) | Experiência antes dos 14 anos |
| `pessoas.contrato_trabalho` | `dias_de_vinculo`, `dias_alem_do_prazo`, `q_pes_01` | [PES-01](13_catalogo_de_achados.md#pes-01) | Temporário além do prazo legal |
| `pessoas.contrato_trabalho` | `dias_de_atraso_do_lancamento`, `q_pes_02` | [PES-02](13_catalogo_de_achados.md#pes-02) | Admissão lançada depois do fato |
| `pessoas.contrato_trabalho` | `dt_prevista_termino_derivada`, `q_pes_03` | [PES-03](13_catalogo_de_achados.md#pes-03) | Temporário sem data prevista de término |
| `pessoas.afastamento` | `q_pes_04` | [PES-04](13_catalogo_de_achados.md#pes-04) | Afastamentos sobrepostos |
| `pessoas.alocacao` | `q_fin_06` | [FIN-06](13_catalogo_de_achados.md#fin-06) | Alocação sem faturamento |
| `pessoas.alocacao` | `q_tss_01` | [TSS-01](13_catalogo_de_achados.md#tss-01) | Pessoa em campo com ASO vencido |
| `pessoas.alocacao` | `cursos_obrigatorios_sem_certificado`, `q_tss_06` | [TSS-06](13_catalogo_de_achados.md#tss-06) | Curso obrigatório sem certificado válido |
| `ponto.apontamento` | `q_pon_01` | [PON-01](13_catalogo_de_achados.md#pon-01) | A batida que falta |
| `ponto.apontamento` | `q_pon_03` | [PON-03](13_catalogo_de_achados.md#pon-03) | Horas noturnas acima das trabalhadas |
| `ponto.marcacao` | `q_pon_02`, `batida_valida` | [PON-02](13_catalogo_de_achados.md#pon-02) | A batida repetida |
| `ponto.marcacao` | `q_pon_04` | [PON-04](13_catalogo_de_achados.md#pon-04) | A batida solta |
| `folha.rateio_custo` | `diferenca_rateio_folha`, `q_fol_01` | [FOL-01](13_catalogo_de_achados.md#fol-01) | O rateio não fecha com a folha |
| `folha.rateio_custo` | `q_fol_03` | [FOL-03](13_catalogo_de_achados.md#fol-03) | Rateio zerado |
| `folha.provisao` | `q_fol_02` | [FOL-02](13_catalogo_de_achados.md#fol-02) | Provisão que não encadeia |
| `financeiro.fatura` | `q_fin_03` | [FIN-03](13_catalogo_de_achados.md#fin-03) | Fatura depois do fim do contrato |
| `financeiro.fatura_item` | `q_fin_07` | [FIN-07](13_catalogo_de_achados.md#fin-07) | Item de fatura que não fecha |
| `financeiro.titulo_receber` | `situacao_derivada` | [FIN-04](13_catalogo_de_achados.md#fin-04) | Título vencido que continua aberto |
| `financeiro.titulo_receber` | `diferenca_pagamento`, `q_fin_05` | [FIN-05](13_catalogo_de_achados.md#fin-05) | Valor pago diferente do título |
| `sst.aso` | `aso_valido`, `dias_para_vencer` | [TSS-01](13_catalogo_de_achados.md#tss-01) | Pessoa em campo com ASO vencido |
| `sst.aso` | `dias_de_atraso_do_admissional`, `q_tss_02` | [TSS-02](13_catalogo_de_achados.md#tss-02) | Admissional depois da admissão |
| `sst.cat` | `dias_alem_do_prazo_da_cat`, `q_tss_03` | [TSS-03](13_catalogo_de_achados.md#tss-03) | CAT fora do prazo |
| `sst.programa_sst` | `programa_vigente`, `q_tss_04` | [TSS-04](13_catalogo_de_achados.md#tss-04) | Programa legal vencido em contrato ativo |
| `treinamento.turma` | `q_tss_05` | [TSS-05](13_catalogo_de_achados.md#tss-05) | Turmas que podem ser a mesma turma |
| `treinamento.certificado` | `certificado_valido` | [TSS-06](13_catalogo_de_achados.md#tss-06) | Curso obrigatório sem certificado válido |
| `seguranca.log_auditoria` | `q_seg_01` | [SEG-01](13_catalogo_de_achados.md#seg-01) | Ação sem permissão vigente |

Quatro escolhas de implementação ficam ditas, porque a regra aprovada deixava margem:

- **A marca mora onde a linha existe.** O posto com gente alocada e sem fatura (FIN-06) e a pessoa com ASO vencido (TSS-01) não têm linha própria: a marca fica na alocação. O curso obrigatório que falta (TSS-06) também, com a lista dos cursos em `cursos_obrigatorios_sem_certificado`.
- **Regra com prazo vale na data de referência.** "Vencido", "além do prazo" e "vigente" são medidos no "hoje" do dado, que é o dia da carga mais recente. A silver é uma foto: refeita amanhã, o ASO que vence hoje aparece vencido.
- **Derivação sem marca.** A regra aprovada do título a receber (FIN-04) só deriva a situação; não há `q_fin_04`.
- **A duplicidade olha a tabela inteira.** O cadastro repetido atravessa os anos, por isso os assets da silver não são particionados, embora o arquivo continue sendo um por ano.

## 3. A pseudonimização

A LGPD chama de pseudonimização o tratamento depois do qual o dado não pode ser associado a uma pessoa "senão pelo uso de informação adicional mantida separadamente" (art. 13, § 4º). Na silver, a informação adicional é um segredo, `PSEUDONIMIZACAO_SEGREDO`, que mora no `.env` e em nenhum outro lugar.

**A chave.** O documento da pessoa vira o HMAC-SHA256 do valor normalizado (só letras e dígitos) com o segredo: 64 dígitos hexadecimais numa coluna `<coluna>_chave`. Com o segredo, o mesmo CPF dá sempre a mesma chave, e a gold conta pessoas e junta tabelas sem ver documento. Sem ele, a chave não volta ao CPF, nem testando os 100 bilhões de CPFs possíveis, porque quem ataca não sabe com o que combiná-los. Um hash simples, sem segredo, não teria essa propriedade: bastaria calcular o hash de todos os CPFs.

**O domínio.** A chave leva o nome do domínio do valor (`cpf`, `pis`, `documento`, `login`). O CPF do candidato e o do colaborador estão no mesmo domínio e dão a mesma chave: os 15.558 colaboradores têm a `cpf_chave` igual à do candidato de origem. Um PIS que fosse igual a um CPF não daria.

**Uma decisão por coluna.** Cada coluna que a DDL etiqueta como dado pessoal tem uma decisão escrita, com o motivo, em `src/rh_fictalent/silver/pseudonimizacao.py`. Um teste reprova coluna pessoal nova na DDL até alguém decidir o que fazer com ela.

| tabela | coluna na bronze | classe | tratamento | na silver | motivo |
|---|---|---|---|---|---|
| `cadastro.endereco` | `logradouro` | pessoal | remover | não entra | com o número, localiza a casa de quem mora; o município basta |
| `cadastro.endereco` | `cep` | pessoal | remover | não entra | localiza a rua; o município basta |
| `comercial.cliente_contato` | `nome` | pessoal | remover | não entra | identifica a pessoa e não serve a indicador nenhum |
| `comercial.cliente_contato` | `email` | pessoal | remover | não entra | contato da pessoa; nenhum indicador usa |
| `comercial.cliente_contato` | `telefone` | pessoal | remover | não entra | contato da pessoa; nenhum indicador usa |
| `ats.candidato` | `nome` | pessoal | remover | não entra | identifica a pessoa; a conformação do ATS-05 virou recomendação ao cliente na origem |
| `ats.candidato` | `cpf` | pessoal | chave | `cpf_chave` | identificador de pessoa: vira chave para a gold contar e juntar sem ver o documento |
| `ats.candidato` | `dt_nascimento` | pessoal | ano | `ano_nascimento` | o ano basta para faixa etária |
| `ats.candidato` | `sexo` | pessoal | manter | `sexo` | indicador de diversidade do funil; sozinho não identifica |
| `ats.candidato` | `telefone` | pessoal | remover | não entra | contato da pessoa; nenhum indicador usa |
| `ats.candidato` | `email` | pessoal | remover | não entra | contato da pessoa; nenhum indicador usa |
| `pessoas.colaborador` | `nome` | pessoal | remover | não entra | identifica a pessoa e não serve a indicador nenhum |
| `pessoas.colaborador` | `cpf` | pessoal | chave | `cpf_chave` | identificador de pessoa |
| `pessoas.colaborador` | `dt_nascimento` | pessoal | ano | `ano_nascimento` | o ano basta para faixa etária |
| `pessoas.colaborador` | `endereco_id` | pessoal | manter | `endereco_id` | chave interna; o endereço que ela aponta já sai sem logradouro e sem CEP |
| `pessoas.colaborador` | `pis` | pessoal | chave | `pis_chave` | identificador de pessoa |
| `pessoas.colaborador_documento` | `numero` | pessoal | chave | `numero_chave` | identificador de pessoa |
| `pessoas.dependente` | `nome` | pessoal | remover | não entra | identifica a pessoa e não serve a indicador nenhum |
| `pessoas.dependente` | `dt_nascimento` | pessoal | ano | `ano_nascimento` | o ano basta para faixa etária |
| `pessoas.afastamento` | `cid_grupo` | sensível | manter | `cid_grupo` | saúde, para indicador agregado de absenteísmo; a gold não o leva com chave de pessoa |
| `folha.folha_item` | `valor` | pessoal | manter | `valor` | remuneração individual é o custo da folha, base da margem; a pessoa já é só um id |
| `sst.aso` | `resultado` | sensível | manter | `resultado` | saúde, para indicador agregado de segurança; a gold não o leva com chave de pessoa |
| `sst.aso` | `medico_crm` | sem etiqueta | remover | não entra | identifica o médico examinador; nenhum indicador usa |
| `sst.acidente` | `tipo` | sensível | manter | `tipo` | saúde, para indicador agregado de segurança |
| `sst.acidente` | `gravidade` | sensível | manter | `gravidade` | saúde, para indicador agregado de segurança |
| `seguranca.usuario` | `nome` | pessoal | remover | não entra | identifica a pessoa e não serve a indicador nenhum |
| `seguranca.usuario` | `email` | pessoal | remover | não entra | contato da pessoa; nenhum indicador usa |
| `seguranca.usuario` | `login` | sem etiqueta | chave | `login_chave` | o login costuma ser o nome; vira chave para a auditoria de acesso agrupar por usuário |
| `seguranca.log_auditoria` | `valor_anterior` | pessoal | remover | não entra | pode carregar o dado pessoal alterado |
| `seguranca.log_auditoria` | `valor_novo` | pessoal | remover | não entra | pode carregar o dado pessoal alterado |

Duas colunas da lista não têm etiqueta na DDL e foram achadas neste trabalho: o CRM do médico e o login. Estão tratadas na silver, e a etiqueta entra na DDL quando o modelo da réplica for revisto.

**A ordem importa.** As marcas de qualidade são calculadas sobre a bronze em claro, **antes** da pseudonimização: o CPF inválido continua marcado (`q_ats_03`), só que a silver não guarda mais o CPF. E a coluna derivada que carregava dado pessoal passa pela chave também: o `grupo_pessoa` da duplicidade, que era o CPF, é a chave do CPF.

**O que a pseudonimização não é.** Não é anonimização: com o segredo, o dado volta a ser pessoal, e a silver continua sob a LGPD. O segredo se guarda como senha; trocá-lo troca toda chave de pessoa, e a silver inteira precisa ser refeita ([Manual de Operação, seção 2](08_manual_de_operacao.md)).

## 4. Como uma tabela é construída, e provada

Cada tabela passa por quatro passos, na ordem em que a literatura chama de auditar, gravar, auditar e publicar:

1. **Montar.** As regras da tabela rodam sobre a bronze, cada uma devolvendo o `id` e as colunas novas. A silver é a bronze pseudonimizada com essas colunas juntadas pelo `id`.
2. **Gravar na área de conferência**, `silver/_em_conferencia/`, nunca direto no endereço que a gold lê.
3. **Conferir o arquivo gravado**, lido de volta do lake, não o que ficou na memória.
4. **Publicar**: só a tabela aprovada é movida para `silver/<modulo>/<tabela>/`. A reprovada fica na área de conferência para quem for investigar, e a versão publicada antes continua como estava.

A conferência são **cinco provas**, e qualquer uma reprova a tabela:

| prova | o que exige | o que pega |
|---|---|---|
| linhas | o mesmo número de linhas da bronze, no total e em cada ano | linha perdida ou duplicada num join |
| valores | toda coluna original com o mesmo valor e o mesmo tipo, na tabela inteira (`EXCEPT ALL` nos dois sentidos, contra a bronze pseudonimizada pela mesma regra) | regra que alterou o que não devia |
| colunas | as da bronze pseudonimizada e depois as novas, na ordem | coluna a mais, a menos ou fora do lugar |
| marcas | marca preenchida só em linha avaliada; `pessoal_descartado` igual ao que a bronze mostra | marca em linha morta, ou vazia em linha viva |
| chaves | coluna de chave só com 64 dígitos hexadecimais | documento em claro que escapasse por engano |

A segunda prova não é amostra: compara a tabela inteira. No caso das marcações de ponto são 4,3 milhões de linhas, e mesmo assim a tabela é montada, gravada e conferida em três segundos.

## 5. A linha que não se avalia

Duas linhas seguem na silver sem passar pelas regras, com todas as marcas nulas:

- **a excluída na origem** (`excluido_em` preenchido): ela não existe mais para o negócio;
- **a descartada por retenção** (`pessoal_descartado` verdadeiro, hoje só no candidato): o dado pessoal dela foi apagado por força de lei.

A segunda merece a explicação, porque o projeto errou aqui antes de acertar. Na primeira versão, o candidato descartado, agora sem CPF, era contado pela regra "candidato sem CPF", e o achado saltou de 295 para 19.266. Estava errado: o CPF que o próprio pipeline apagou não é defeito do cadastro do cliente. Marca nula quer dizer exatamente isso, **não avaliada**, e é diferente de `FALSE`. Com a correção, o achado é 147: os candidatos sem CPF que continuam com o dado.

Quem consulta a silver para medir qualidade filtra as duas: `WHERE excluido_em IS NULL AND NOT pessoal_descartado` (a segunda condição só na tabela que tem a coluna).

## 6. A prestação de contas

O catálogo foi aprovado com números: 457 CPFs inválidos, 263 temporários além do prazo. A silver promete marcar exatamente essas linhas, e a **prestação de contas** cobra a promessa: roda cada uma das 34 regras sobre a bronze, **na data de referência da auditoria** (a regra com prazo depende do dia), conta na unidade em que a auditoria contou (linhas, dias, pessoas, contratos) e compara. Qualquer diferença reprova.

```bash
.venv/bin/python -m rh_fictalent.silver --prestar-contas
```

Na primeira vez que rodou, ela reprovou duas regras, e as duas pelo mesmo defeito de quem escreveu o código: uma função que comparava só a última coluna de uma chave composta marcava 436 postos onde a auditoria tinha achado 8. É para isso que a conta existe.

**A cadeia de custódia.** O descarte de dado pessoal muda a medida. Apagar o CPF de 19.119 candidatos vencidos tira esses cadastros dos grupos de CPF repetido, e a regra passa a dar outro número, por força de lei. Exigir o número da auditoria para sempre obrigaria a escolher entre descumprir a LGPD e desligar a prova.

A saída é registrar. Cada descarte mede, para toda regra que lê a tabela descartada, o número **antes** e **depois** de apagar, e grava os dois em `lgpd.descarte`, no warehouse, sem nenhum dado pessoal. O número esperado de uma regra passa a ser o da auditoria, trocado pelo "depois" de cada descarte, em ordem; e o "antes" de cada descarte tem de ser o esperado até ali, ou o número da auditoria, que é o caso da tabela recopiada da réplica (a recópia traz o dado pessoal de volta, e o descarte seguinte o apaga de novo). Se um elo não fecha (alguém apagou sem registrar, a bronze mudou entre dois descartes), a prestação reprova dizendo onde a cadeia quebrou.

O primeiro descarte, em 01/10/2026, deixou este registro para as regras do candidato:

| regra | na auditoria | depois do descarte |
|---|---:|---:|
| ATS-01, a mesma pessoa cadastrada mais de uma vez | 2.735 | 859 |
| ATS-02, mesmo nome e nascimento, CPFs diferentes | 181 | 66 |
| ATS-03, CPF inválido | 457 | 244 |
| ATS-04, data de nascimento impossível | 94 | 50 |
| ATS-05, nome escrito de vários jeitos | 1.333 | 679 |
| ATS-06, candidato sem CPF | 295 | 147 |
| ATS-08, experiência antes dos 14 anos | 667 | 454 |

As outras 27 regras continuam com o número da auditoria. A prestação fecha em 34 de 34, e o relatório fica no lake, em `silver/_prestacao_de_contas.json`, com a origem de cada número esperado.

Quando a prestação reprova sem descarte e sem mudança nas regras, a causa é a bronze: a réplica andou depois da auditoria. O caminho é refazer a auditoria, revisar o catálogo e aprovar de novo, nunca ajustar a regra para bater. O número aprovado é o contrato.

## 7. No Dagster

| o quê | nome | o que faz |
|---|---|---|
| 76 assets | `silver/<modulo>/<tabela>` | monta, grava, confere e publica a tabela; reprova a si mesmo |
| asset | `lgpd/descarte` | apaga da bronze o dado pessoal eliminado ou vencido, e registra |
| asset | `silver/prestacao_de_contas` | as 34 regras contra o número esperado; grava o relatório |
| job | `construir_silver` | o descarte, as 76 tabelas e a prestação |
| job | `aplicar_descarte` | o caminho curto, à mão: o descarte, as 12 tabelas com dado pessoal e a prestação |
| sensor | `silver_depois_da_carga` | dispara `construir_silver` depois de toda carga incremental que termina bem |

A linhagem diz por que uma tabela muda. `silver/pessoas/alocacao` depende da bronze da alocação e também da bronze do ASO, do certificado e da fatura, porque as marcas dela leem essas tabelas. A silver de tabela com dado pessoal depende do `lgpd/descarte`: ela nunca é montada sobre dado vencido.

A silver inteira é refeita depois de toda carga incremental, porque a carga muda a bronze, e o descarte vai na frente porque a carga pode trazer o dado de volta: ela troca na bronze as linhas que mudaram na réplica, e o candidato vencido cujo cadastro foi alterado volta inteiro, em claro. O backfill não dispara nada: são nove execuções, uma por ano, e disparar a cada uma rodaria nove descartes, vários ao mesmo tempo, sobre os mesmos arquivos. Depois de um backfill, quem fecha o ciclo é a primeira carga incremental, que também cria a marca d'água de onde sai a data de referência.

Três decisões de operação. No máximo **duas tabelas por vez**, porque cada passo é um processo com o Dagster e o DuckDB carregados, e o padrão (um por núcleo) passa do limite de memória do container. **Nova tentativa só para falha de infraestrutura**: reprovação na conferência não se repete, porque é determinística, e tentar de novo só adiaria a mesma resposta. E **a memória é do daemon**: tudo o que entra pela fila (agenda, sensor, interface) é executado no container do daemon, não no da interface. Com o teto de 1 GB que ele tinha, o kernel matava o passo da maior tabela, e o erro que aparece é só `ChildProcessCrashException`; quem conta a causa é o contador `oom_kill` do container. O teto passou a 3 GB e o DuckDB ganhou limite próprio de 512 MB por passo, com o excedente indo para disco. Provado na silver disparada pelo sensor: 78 passos, nenhum processo morto. O uso de memória do container chega ao teto mesmo assim, porque a conta inclui o cache de arquivos, que o sistema devolve quando precisa; o que diz se faltou memória é o contador, não o pico.

## 8. Ler a silver

A silver é parquet no lake, lida com o mesmo DuckDB da bronze. Da raiz do repositório, com a plataforma de pé:

```python
from dotenv import load_dotenv

from rh_fictalent.lake import consulta
from rh_fictalent.orquestracao.recursos import lake_do_ambiente

load_dotenv(".env")
lake = lake_do_ambiente()
con = consulta.abrir(lake)
candidatos = lake.caminho("silver", "ats", "candidato", "ano=*.parquet")
consulta.sql(
    con,
    f"""
    SELECT count(*) AS cadastros,
           count(DISTINCT cpf_chave) AS pessoas_com_documento,
           count(*) FILTER (WHERE q_ats_01) AS em_grupo_repetido
    FROM read_parquet('{candidatos}')
    WHERE excluido_em IS NULL AND NOT pessoal_descartado
""",
)
```

A conexão que `abrir` devolve tem as views da bronze e já sabe falar com o lake; a silver se lê pelo caminho. Views com os nomes das tabelas para a silver chegam com a gold, que é quem vai lê-la todo dia.

## 9. Os tempos, lado a lado

| operação | volume | tempo medido |
|---|---|---|
| prestação de contas | 34 regras sobre a bronze | 1,4 s |
| a silver inteira, pela linha de comando | 76 tabelas, 8,4 milhões de linhas, com as cinco provas | 31 s |
| a maior tabela (`ponto.marcacao`) | 4.300.719 linhas, montar, gravar e conferir | 3 s |
| job `construir_silver`, no container | 78 passos, dois por vez | de 3 a 4 minutos (175 s quando disparado pelo sensor) |
| o primeiro descarte | 19.119 candidatos em 7 arquivos, com conferência | 11 s |
| job `aplicar_descarte`, sem alvo | 14 passos | 41 s |

A diferença entre os 31 segundos da linha de comando e os 185 do job é o custo de cada passo do Dagster ser um processo novo, com registro, linhagem e histórico. É o preço de saber, depois, o que rodou, quando e com que resultado.

## 10. O que ainda não existe

- **Série diária.** As marcas com prazo valem na data de referência. A pergunta "quantas pessoas estavam com ASO vencido em cada dia de 2025" é uma série, e é da gold.
- **Views da silver.** Hoje se lê pelo caminho do arquivo (seção 8).
- **Silver incremental.** Cada tabela é refeita inteira. Com 31 segundos para a camada toda, refazer é mais barato que o código para não refazer; a conta muda se o volume crescer dez vezes.
- **Rotação do segredo.** Trocar o segredo e refazer a silver funciona, mas não há procedimento para trocar mantendo as chaves antigas legíveis por um período.
- **Etiqueta LGPD do CRM e do login.** Tratados na silver, ainda sem etiqueta na DDL da réplica.
- **Fontes públicas e trilha de exclusões.** Não passam pela silver: não são dado do cliente a conformar.

---

[Início](#topo)
