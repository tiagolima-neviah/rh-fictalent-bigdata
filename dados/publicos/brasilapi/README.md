# BrasilAPI · feriados nacionais 2018 a 2026

**Fonte:** BrasilAPI, feriados nacionais v1 (`https://brasilapi.com.br/api/feriados/v1/{ano}`). Dado público.

`feriados_nacionais.csv`: uma linha por feriado e ano (2018 a 2026, a história da Fictalent), com `data`, `nome`, `abrangencia` (sempre `NACIONAL` aqui; a réplica também aceita `ESTADUAL` e `MUNICIPAL`, que o gerador acrescenta para os três municípios do caso) e `ano`. `fonte.json` guarda a fonte, a URL e a data do download.

Regenerar (junto com os municípios):

```bash
.venv/bin/python -m rh_fictalent.fontes.apis
```

O mesmo dado entra no lake pelo asset `fontes/brasilapi/feriados` do Dagster, particionado por ano (job `carregar_feriados`, com backfill de 2018 a 2026 pela interface).
