"""Backup e restauração da plataforma, com a restauração provada: backup não provado não é backup.

Quatro partes, cada uma com a sua ferramenta e o seu manifesto de contagens: a **réplica**
(os 10 databases, por `mysqldump` lógico, mais a chave de cifra do keyring), o **warehouse**
(`pg_dump` do `dw_fictalent`: o modelo dimensional, as métricas, os descartes, o acesso), o
**Dagster** (`pg_dump` do histórico de execuções) e o **lake** (os arquivos do bucket, camada
a camada). O manifesto guarda, no momento do backup, quantas linhas cada tabela tinha e quantos
arquivos e bytes cada camada tinha; a prova de restauração (`--provar`) restaura tudo em alvos
descartáveis (um MySQL efêmero, bancos `*_prova` no mesmo Postgres, um prefixo `_prova` no
bucket), conta de novo, compara com o manifesto e apaga os alvos. A restauração de verdade
(`--restaurar --sim`) faz o mesmo nos alvos reais.

O dump lógico da réplica sai em claro: a cifra em repouso protege o disco do banco, não o
arquivo do backup. A pasta do backup é dado pessoal e deve ser guardada cifrada e fora da
máquina (`docs/19`); este módulo só a produz e a prova.
"""
