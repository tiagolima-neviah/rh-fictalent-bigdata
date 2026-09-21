# Consolidado gerencial · a planilha da gerente-geral

**Dado sintético.** Estas nove pastas de trabalho (uma por ano, de 2018 a 2026) fazem o papel das planilhas que a gerente-geral da Fictalent monta à mão todo mês, juntando o que cada setor exporta. São a **fonte de arquivo** do pipeline: a ingestão de Excel (v0.5.0) lê daqui, contra um esquema declarado.

Cada arquivo tem uma aba `Consolidado`: título na primeira linha, cabeçalho na terceira, uma linha por competência e filial (`Competência`, `Filial`, `Headcount`, `Vagas abertas`, `Faturamento (R$)`, `Custo (R$)`, `Lançado em`) e uma linha `TOTAL` no fim. Quem lê precisa pular o título e descartar o total: é de propósito, planilha de gente é assim.

**O que há para achar aqui.** Até 2021 a planilha bate com a operação. A partir de 2022 ela diverge, e a divergência cresce com o volume (de 0,5% em 2022 a 9% em 2026): é a frase da gerente, "depois de 2022 os relatórios pararam de bater", virando dado. O mesmo conteúdo está na réplica, em `financeiro.consolidado_gerencial`, como a planilha carregada no sistema. Decidir qual número é a verdade é do dono do processo, não do analista.

Regenerar (junto com o financeiro inteiro):

```bash
.venv/bin/python -m rh_fictalent.gerador --etapa 5 --gravar
```
