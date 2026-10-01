<a id="topo"></a>

# Auditoria de qualidade da bronze · os notebooks

[Home](../../README.md) | [Entendimento dos dados](../../docs/02_entendimento_dados.md) | [Arquitetura](../../docs/03_arquitetura.md)

> Dez notebooks, um por domínio da bronze e um de fechamento, executados de cima a baixo e versionados com as saídas. São a **evidência** da auditoria de qualidade da v0.6.0: cada seção mostra o código, a saída e uma Nota Técnica (Observado, Por que importa, Ação), e cada notebook termina gravando os achados em [`dados/auditoria/`](../../dados/auditoria/), de onde o catálogo de achados parte. Nenhum número da Nota Técnica é inventado: todos vêm da saída executada logo acima.

## A ordem de leitura

A numeração segue o caminho do dado, das tabelas de referência às que dependem delas.

| notebook | domínio | o que responde |
|---|---|---|
| `00_cadastro` | as regras do jogo | geografia, funções, convenções e pisos, feriados, escalas: o que todo o resto referencia |
| `01_comercial` | a carteira | clientes, contratos, postos, preços, SLAs, ocorrências |
| `02_ats` | o funil | candidatos (duplicados, documentos), vagas, candidaturas, etapas, entrevistas |
| `03_pessoas` | o vínculo | colaboradores, contratos de trabalho (prazo do temporário, admissão retroativa), alocações, afastamentos |
| `04_ponto` | o dia a dia | 4,3 milhões de batidas, apontamentos, ocorrências, banco de horas |
| `05_folha` | o custo | itens, provisões, benefícios e o rateio que leva o custo ao contrato |
| `06_financeiro` | a receita | faturas, títulos, impostos e o consolidado da gerência contra a operação |
| `07_treinamento_sst` | os documentos com prazo | cursos e certificados, exames (ASO vencido com pessoa alocada), programas legais, acidentes e CAT |
| `08_seguranca` | quem fez o quê | usuários, perfis, a matriz de permissão e a trilha contra as tabelas que ela nomeia |
| `09_fechamento` | o veredito | os nove registros consolidados, as seis declarações do cliente confrontadas, o catálogo preliminar |

## A regra: auditoria às cegas

Os notebooks procuram os defeitos no dado tendo como únicas referências o esquema (a DDL: chaves, unicidades, domínios declarados, tipos) e o entendimento do negócio ([`docs/02`](../../docs/02_entendimento_dados.md)). **Nenhum deles consulta o gerador da base sintética nem a régua de validação**, e um teste garante isso (`tests/test_auditoria.py`): célula que importe `rh_fictalent.gerador` ou `rh_fictalent.validacao` reprova. O que o cliente declarou sobre a qualidade dos próprios dados entra como hipótese, testada, com veredito no fechamento. É o que faz do catálogo de achados uma prova, e não uma cópia do que foi plantado.

## Como rodar

Com a plataforma de pé (`docker compose up -d`) e o `.env` preenchido, da raiz do projeto:

```bash
.venv/bin/python -m rh_fictalent.auditoria --executar            # todos, na ordem; ~3 minutos
.venv/bin/python -m rh_fictalent.auditoria --executar 04_ponto   # um só
.venv/bin/python -m rh_fictalent.auditoria --verificar           # o padrão, sem executar
```

`--executar` roda cada notebook num kernel novo, de cima a baixo, e o regrava com as saídas: é essa versão que vai para o repositório. `--verificar` confere o que o padrão de entrega exige (célula com `id`, cabeçalho, Nota Técnica em toda seção e de fechamento, toda célula de código executada, nenhum caminho de máquina, nenhuma consulta ao gerador) e é o que a CI roda, sem lake.

Os notebooks leem o lake pelo pacote do projeto (`rh_fictalent.lake.consulta`, uma view por tabela com os nomes da réplica) e a marca d'água no warehouse (`rh_fictalent.ingestao.marca_dagua`): endereço e credencial vêm do `.env`, e nenhum notebook conhece os dois. O que roda mais de uma vez não mora no notebook: as checagens genéricas (perfil, tipos contra a DDL, duplicatas por chave e por conteúdo, órfãos, domínios, ordem temporal, sobreposição de vigências, CPF e CNPJ) estão em `rh_fictalent.auditoria.checagens`, testadas com DuckDB em memória.

Para conferir os números escritos à mão nas Notas Técnicas contra as saídas executadas:

```bash
.venv/bin/python scripts/conferir_numeros_dos_notebooks.py
```

## O que sai daqui

Cada notebook grava `dados/auditoria/<dominio>.json` com os achados (tabela, coluna, linhas atingidas de quantas, severidade, impacto, ação proposta e a declaração do cliente que testa, se houver). O `09_fechamento` consolida os nove e é a entrada do catálogo de achados, aprovado antes de qualquer transformação. A severidade segue o critério da casa: **alta** impede uma análise ou distorce uma decisão; **média** exige tratamento na silver sem impedir a análise; **baixa** incomoda e não muda conclusão; **nenhuma** é hipótese refutada, regra de negócio que parecia defeito, ou ponto forte que vale registrar.

---

[Início](#topo)
