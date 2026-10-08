<a id="topo"></a>

# Backup e restauração · dos bancos e do lake, com a restauração provada

<!-- nav:start -->
[Home](../README.md) | [← API dos indicadores](18_api.md) | [Solução de problemas →](20_solucao_de_problemas.md)
<!-- nav:end -->

> Backup que nunca foi restaurado não é backup; é uma esperança. Este documento explica o que a plataforma guarda e onde (`rh_fictalent.backup`), como se faz um backup, como se **prova** que ele restaura (em alvos descartáveis, sem tocar na plataforma de pé), como se restaura de verdade quando for preciso, o que fazer com a pasta que sai, e os tempos medidos na base completa em 07/10/2026.

## 1. O que se guarda, e por quê

| parte | o que é | ferramenta | por que entra |
|---|---|---|---|
| **réplica** | os 10 databases de negócio mais `meta` (a trilha de exclusões), 76 tabelas, 8,41 milhões de linhas | `mysqldump --single-transaction --databases --add-drop-database`, um `.sql.gz` por database | é o sistema do cliente: a fonte de tudo; a bronze é espelho, mas o espelho não substitui o original |
| **keyring** | a chave de cifra em repouso da réplica | cópia do arquivo do keyring (modo 600 no destino) | sem ela, o **disco** da réplica é irrecuperável; serve à restauração física do volume, não ao dump lógico |
| **warehouse** | `dw_fictalent` inteiro: `dim` e `fato`, as métricas (`observabilidade`), os descartes (`lgpd`), o acesso (`acesso`) | `pg_dump -Fc --no-owner` | `dim` e `fato` se refazem da gold, mas as métricas, a cadeia de custódia dos descartes e os tokens, não |
| **Dagster** | o histórico de execuções (`runs`, `event_logs`, ticks) | `pg_dump -Fc --no-owner` | é a memória de operação; perdê-la não para o pipeline, mas apaga o que rodou |
| **lake** | os arquivos do bucket, camada a camada: `bronze`, `silver`, `gold`, `fontes`, `controle` | arquivo a arquivo pelo s3fs | a bronze guarda a história que a réplica já não tem (a linha excluída na origem fica marcada, não some); silver e gold se refazem, mas custam minutos |

Tudo isso vai para uma pasta datada, `<base>/<AAAAMMDD-HHMMSS>/`, com um `manifesto.json` que guarda, por parte, as contagens de cada tabela (linhas) ou camada (arquivos e bytes) **no momento do backup**, e, por arquivo, o tamanho e o SHA-256. O manifesto é o que torna a prova possível.

## 2. Fazer

```bash
.venv/bin/python -m rh_fictalent.backup --fazer backups
```

Cria `backups/<AAAAMMDD-HHMMSS>/` com `replica/*.sql.gz` e `replica/keyring`, `warehouse/dw_fictalent.dump`, `dagster/dagster.dump`, `lake/<camada>/...` e o manifesto. As senhas vêm do `.env`; nenhuma passa pela linha de comando. Para um recorte, `--parte`:

```bash
.venv/bin/python -m rh_fictalent.backup --fazer backups --parte replica:seguranca,warehouse,lake:gold
```

As partes são `replica` (ou `replica:<database>`), `keyring`, `warehouse`, `dagster` e `lake` (ou `lake:<camada>`).

**Banco vivo.** As contagens são tiradas antes e depois do dump. Num banco parado as duas são iguais e a prova compara exato; num banco vivo (o Dagster registra ticks dos sensores o tempo todo), o restaurado tem de cair no intervalo entre as duas. O manifesto guarda os dois lados.

## 3. Provar

```bash
.venv/bin/python -m rh_fictalent.backup --provar backups/20261007-182435
```

A prova primeiro confere cada arquivo contra o manifesto (tamanho e SHA-256) e depois restaura cada parte num **alvo descartável**, conta de novo, compara e apaga o alvo:

| parte | alvo descartável | o que se compara |
|---|---|---|
| réplica | um MySQL efêmero (`docker run --rm`, imagem igual à da plataforma, keyring próprio numa pasta temporária, senha de root gerada no processo e nunca impressa) | linhas por tabela, nos databases restaurados |
| warehouse | o banco `dw_fictalent_prova`, criado no mesmo Postgres | linhas por tabela em `dim`, `fato`, `observabilidade`, `lgpd`, `acesso` |
| Dagster | o banco `dagster_prova`, no Postgres do Dagster | linhas por tabela do `public` |
| lake | o prefixo `_prova_restauracao/` no bucket | arquivos e bytes por camada |

Os alvos somem ao fim mesmo quando a prova falha (`finally`). Sai com 0 quando tudo confere e 1 quando alguma parte reprovou, dizendo qual tabela e quais contagens. É a prova que faz o backup ser backup, e ela cabe numa rotina: todo backup que importa é seguido de `--provar`.

## 4. Restaurar de verdade

```bash
.venv/bin/python -m rh_fictalent.backup --restaurar backups/20261007-182435 --sim
```

Sem `--sim` o comando só avisa e sai. Com ele, a réplica recebe cada database de volta (o dump tem `DROP DATABASE` e `CREATE DATABASE`, então a réplica fica igual ao backup), o warehouse e o Dagster recebem `pg_restore --clean --if-exists` e o lake recebe os arquivos no lugar; no fim, as mesmas contagens do manifesto são conferidas. Antes de restaurar o Dagster, pare quem escreve nele: `docker compose stop dagster-web dagster-daemon api`, e suba de novo depois.

Três coisas que a restauração lógica **não** faz, de propósito: não troca a chave do keyring (o dump é texto; qualquer keyring serve), não recria os papéis do Postgres que não existirem no destino (`--no-owner`; o DCL e o RLS são refeitos pelo `carregar_warehouse` e pelo `--preparar` da API), e não religa o Dagster, que precisa subir depois de o banco dele estar inteiro.

## 5. A pasta é dado pessoal

O dump da réplica sai **em claro**. A cifra em repouso ([Segurança e LGPD](05_seguranca_e_lgpd.md)) protege o disco do banco, não o arquivo que o `mysqldump` escreve, e esse arquivo tem CPF, nome, endereço e salário de cada pessoa do caso. Mesmo sintética, a disciplina é a mesma que valeria com a base real do cliente: a pasta do backup se guarda cifrada (`age`, `gpg` ou o cofre do provedor), fora da máquina que roda a plataforma, e se apaga quando a retenção acabar. Este módulo só produz e prova a pasta; o resto é rito do operador, e em produção vira política escrita.

A chave do keyring tem o mesmo tratamento, com um agravante: ela e o disco cifrado nunca ficam no mesmo lugar, porque juntos são o dado em claro.

## 6. Os tempos, medidos

Base completa, em 07/10/2026, na máquina de desenvolvimento:

| parte | backup | prova de restauração |
|---|---|---|
| réplica (11 databases, 76 tabelas, 8.410.930 linhas) | 69 s, 123 MB em gzip | 157 s num MySQL efêmero, tudo igual |
| keyring | 0,1 s, 15 KB | tamanho conferido |
| warehouse (31 tabelas, 1.683.369 linhas) | 9 s, 23 MB | 13 s, tudo igual |
| Dagster (22 tabelas, 57 execuções) | 5 s, 2,6 MB | 4 s, dentro do intervalo do banco vivo |
| lake (5 camadas, 1.364 arquivos) | 4 s, 276 MB | 4 s, bytes iguais |
| **total** | **94 s, 423 MB** | **189 s** |

Dois tropeços do caminho ficaram registrados. A primeira prova do Dagster falhou por quatro linhas em `job_ticks` (o banco escreveu entre o dump e a contagem), o que deu origem ao intervalo da seção 2. E o `get` recursivo do s3fs tropeçou numa entrada de pasta que o SeaweedFS lista como objeto vazio, o que fez o download do lake passar a ser arquivo a arquivo.

## 7. O que ainda não existe

- **Agenda.** O backup é um comando; não há job nem cron. A plataforma de laboratório sobe e desce todo dia, e o backup vale ser feito antes de uma mudança grande e ao fechar uma versão.
- **Cifra da pasta pelo módulo.** O operador cifra depois; um `--cifrar` com `age` seria o passo seguinte.
- **Restauração parcial no tempo.** O dump é a foto de um instante; voltar a um ponto no tempo (PITR) pede o binlog da réplica e o WAL dos Postgres, que não são guardados.
- **O destino em nuvem.** O warehouse no Neon não entra no backup: ele é espelho do local, e o Neon tem o próprio histórico de restauração (6 horas no plano gratuito).

---

[Início](#topo)
