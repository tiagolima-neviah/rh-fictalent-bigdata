# Novo CAGED · tabelas derivadas para calibrar a sazonalidade

**Fonte:** microdados não identificados do Novo CAGED, PDET / Ministério do Trabalho e Emprego, FTP público `ftp://ftp.mtps.gov.br/pdet/microdados/NOVO CAGED/`. Dado público, de uso livre com citação da fonte. O bruto (três arquivos `.7z` por competência, ~50 MB, ~4 milhões de linhas por mês) **não está no repositório**: fica num cache fora do git; aqui entram só as tabelas derivadas, geradas por `python -m rh_fictalent.fontes.caged`.

**O que o projeto tira daqui, e só isso:** o ritmo do ano. O arco da história da Fictalent continua ficção; o CAGED diz em que meses o segmento admite e desliga mais.

## Como foi agregado

- Três arquivos por competência de declaração: `MOV` (no prazo), `FOR` (fora do prazo) e `EXC` (exclusões, que invertem o saldo). Somados `MOV + FOR - EXC`, **pela competência da movimentação** (`competênciamov`), não da declaração.
- Escopos: os três municípios do caso (Atibaia `350410`, Bragança Paulista `350760`, Extrema `312510`; códigos IBGE de 6 dígitos, como no CAGED) e os estados de SP (`35`) e MG (`31`) como reserva de amostra.
- Grupos: `78` (subclasses 78.10 seleção e agenciamento, 78.20 locação de mão de obra temporária, 78.30 fornecimento e gestão de RH), nos municípios e nos estados; e cada **seção CNAE** (uma letra) só nos municípios, para o ritmo da demanda dos clientes (comércio `G`, indústria `C`, transporte `H`, serviços administrativos `N`...).
- Período: competências de declaração de 2023-01 a 2025-12 (36 meses); a tabela mensal é recortada ao mesmo período.

## As tabelas

`movimentacao_mensal.csv`: uma linha por competência, escopo e grupo, com `admissoes`, `desligamentos`, `saldo` e `nome_escopo`.

`indice_sazonal.csv`: uma linha por escopo, grupo e mês do ano (1 a 12), com `indice_admissoes` e `indice_desligamentos` (o mês dividido pela média do ano, na média dos anos completos), `anos` (quantos anos entraram) e `amostra_media` (média mensal de admissões do escopo e grupo, para julgar se a amostra sustenta o índice; abaixo de umas 30 por mês, prefira o estado). A média dos 12 índices de um escopo e grupo é 1 por construção.

`fonte.json`: a fonte, a regra de agregação, as competências e a data do download.

## Regenerar

```bash
.venv/bin/python -m rh_fictalent.fontes.caged --de 2023-01 --ate 2025-12
```

Baixa o que não estiver no cache (`~/refs_privadas/fictalent/caged/`), extrai e agrega mês a mês descartando o texto extraído, e reescreve as três saídas. Um teste (`tests/test_caged.py`) confere a agregação numa amostra e a coerência das tabelas versionadas.
