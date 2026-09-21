# IBGE · municípios de SP e MG

**Fonte:** API de localidades do IBGE, v1 (`https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios`). Dado público.

`municipios.csv`: uma linha por município das duas UFs do caso (645 em SP, 853 em MG), com `codigo_ibge` (7 dígitos, a chave que a réplica usa em `cadastro.municipio`), `nome`, `uf` e as quatro divisões regionais do IBGE (`microrregiao`, `mesorregiao`, `regiao_imediata`, `regiao_intermediaria`), que o gerador usa para agrupar os municípios em regiões comerciais. `fonte.json` guarda a fonte, a URL e a data do download.

Regenerar (junto com os feriados):

```bash
.venv/bin/python -m rh_fictalent.fontes.apis
```

O mesmo dado entra no lake pelo asset `fontes/ibge/municipios` do Dagster (job `carregar_municipios`).
