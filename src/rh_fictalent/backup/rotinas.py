# ruff: noqa: E501
"""As rotinas: fazer, provar e restaurar, parte a parte, com o manifesto de contagens no meio."""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import json
import os
import secrets
import shutil
import subprocess  # nosec B404: os comandos são listas fixas, sem shell
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rh_fictalent.orquestracao.recursos import Lake
from rh_fictalent.staging.gatilhos import MODULOS_DE_NEGOCIO

RAIZ = Path(__file__).resolve().parents[3]
CONTAINER_MYSQL = "fictalent_mysql_staging"
CONTAINER_DW = "fictalent_pg_dw"
CONTAINER_DAGSTER = "fictalent_pg_dagster"
CONTAINER_PROVA = "fictalent_prova_mysql"
IMAGEM_MYSQL = "mysql:8.4.11"
DATABASES = (*MODULOS_DE_NEGOCIO, "meta")
ESQUEMAS_DO_WAREHOUSE = ("dim", "fato", "observabilidade", "lgpd", "acesso")
PARTES = ("replica", "keyring", "warehouse", "dagster", "lake")
PREFIXO_DE_PROVA = "_prova_restauracao"
MANIFESTO = "manifesto.json"


@dataclass(frozen=True)
class Ambiente:
    """O que as rotinas precisam do `.env`; as senhas nunca saem daqui para a linha de comando."""

    senha_root_mysql: str
    usuario_dw: str
    senha_dw: str
    banco_dw: str
    usuario_dagster: str
    senha_dagster: str
    banco_dagster: str
    lake: Lake

    @classmethod
    def do_ambiente(cls) -> Ambiente:
        return cls(
            senha_root_mysql=os.environ["STAGING_ROOT_PASSWORD"],
            usuario_dw=os.environ.get("DW_ADMIN_USER", "fictalent_admin"),
            senha_dw=os.environ["DW_ADMIN_PASSWORD"],
            banco_dw=os.environ.get("DW_DB", "dw_fictalent"),
            usuario_dagster=os.environ.get("DAGSTER_PG_USER", "dagster"),
            senha_dagster=os.environ["DAGSTER_PG_PASSWORD"],
            banco_dagster=os.environ.get("DAGSTER_PG_DB", "dagster"),
            lake=Lake(
                endpoint=os.environ.get("S3_ENDPOINT", "http://127.0.0.1:8333"),
                chave=os.environ["S3_ACCESS_KEY"],
                segredo=os.environ["S3_SECRET_KEY"],
                bucket=os.environ.get("S3_BUCKET", "fictalent-lake"),
            ),
        )


@dataclass
class Resultado:
    parte: str
    ok: bool
    detalhe: str
    segundos: float = 0.0


@dataclass
class Partes:
    """O que fazer: `replica` inteira ou `replica:cadastro`; `lake` inteiro ou `lake:gold`."""

    replica: list[str] = field(default_factory=lambda: list(DATABASES))
    keyring: bool = True
    warehouse: bool = True
    dagster: bool = True
    lake: list[str] | None = None  # None = o bucket inteiro; senão, as camadas (prefixos)

    @classmethod
    def de_texto(cls, texto: str | None) -> Partes:
        """`replica:seguranca,warehouse,lake:controle` → só isso; vazio → tudo."""
        if not texto:
            return cls()
        p = cls(replica=[], keyring=False, warehouse=False, dagster=False, lake=[])
        for item in texto.split(","):
            nome, _, recorte = item.strip().partition(":")
            if nome not in PARTES:
                raise ValueError(f"parte desconhecida: {nome!r} (as partes: {', '.join(PARTES)})")
            if nome == "replica":
                if recorte and recorte not in DATABASES:
                    raise ValueError(f"database desconhecido: {recorte!r}")
                p.replica += [recorte] if recorte else list(DATABASES)
            elif nome == "lake":
                p.lake = None if not recorte else [*(p.lake or []), recorte]
            else:
                setattr(p, nome, True)
        if p.lake == []:
            p.lake = ["\0"]  # nenhum prefixo: o lake não entra
        return p

    @property
    def quer_lake(self) -> bool:
        return self.lake is None or self.lake != ["\0"]


# ----------------------------------------------------------------- utilidades


def _rodar(
    argv: list[str], entrada: bytes | None = None, ambiente: dict[str, str] | None = None
) -> str:
    saida = subprocess.run(  # nosec B603: argv é lista fixa montada aqui, sem shell
        argv, input=entrada, capture_output=True, check=True, env={**os.environ, **(ambiente or {})}
    )
    return saida.stdout.decode("utf-8", errors="replace")


def _mysql(container: str, senha: str, sql: str, database: str | None = None) -> list[list[str]]:
    argv = [
        "docker",
        "exec",
        "-e",
        f"MYSQL_PWD={senha}",
        container,
        "mysql",
        "-uroot",
        "-N",
        "--default-character-set=utf8mb4",
        "-e",
        sql,
    ]
    if database:
        argv.insert(-2, database)
    texto = _rodar(argv)
    return [linha.split("\t") for linha in texto.splitlines() if linha]


def _psql(container: str, usuario: str, senha: str, banco: str, sql: str) -> list[list[str]]:
    argv = [
        "docker",
        "exec",
        "-e",
        f"PGPASSWORD={senha}",
        container,
        "psql",
        "-U",
        usuario,
        "-d",
        banco,
        "-tAF",
        "\t",
        "-c",
        sql,
    ]
    return [linha.split("\t") for linha in _rodar(argv).splitlines() if linha]


def _canal(argv: list[str], **opcoes: Any) -> subprocess.Popen[bytes]:
    """Um processo com os canais abertos; argv é lista fixa montada aqui, sem shell."""
    return subprocess.Popen(argv, **opcoes)  # nosec B603


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def nome_da_pasta(agora: datetime | None = None) -> str:
    return (agora or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")


# ----------------------------------------------------------------- contagens


def contar_replica(
    amb: Ambiente,
    databases: Iterable[str],
    container: str = CONTAINER_MYSQL,
    senha: str | None = None,
) -> dict[str, int]:
    """Linhas por tabela, exatas (`COUNT(*)`), em `database.tabela`."""
    contagens: dict[str, int] = {}
    for db in databases:
        lista = f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{db}' AND table_type = 'BASE TABLE' ORDER BY 1"  # noqa: S608 # nosec B608
        tabelas = [t for (t,) in _mysql(container, senha or amb.senha_root_mysql, lista)]
        if not tabelas:
            continue
        uniao = " UNION ALL ".join(f"SELECT '{t}', COUNT(*) FROM `{db}`.`{t}`" for t in tabelas)  # noqa: S608 # nosec B608
        for tabela, n in _mysql(container, senha or amb.senha_root_mysql, uniao):
            contagens[f"{db}.{tabela}"] = int(n)
    return contagens


def contar_postgres(
    container: str, usuario: str, senha: str, banco: str, esquemas: Iterable[str] | None
) -> dict[str, int]:
    """Linhas por tabela (as particionadas pela mãe), em `schema.tabela`; sem schemas, as do `public`."""
    filtro = (
        f"n.nspname IN ({', '.join(repr(e) for e in esquemas)})"
        if esquemas
        else "n.nspname = 'public'"
    )
    sql = f"SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind IN ('r', 'p') AND NOT c.relispartition AND {filtro} ORDER BY 1, 2"  # noqa: S608 # nosec B608
    contagens: dict[str, int] = {}
    for esquema, tabela in _psql(container, usuario, senha, banco, sql):
        contagem = f'SELECT count(*) FROM "{esquema}"."{tabela}"'  # noqa: S608 # nosec B608
        (n,) = _psql(container, usuario, senha, banco, contagem)[0]
        contagens[f"{esquema}.{tabela}"] = int(n)
    return contagens


def contar_lake(
    lake: Lake, prefixo: str = "", camadas: Iterable[str] | None = None
) -> dict[str, dict[str, int]]:
    """Arquivos e bytes por camada (o primeiro nível do bucket)."""
    fs = lake.sistema()
    raiz = f"{lake.bucket}/{prefixo}".rstrip("/")
    por_camada: dict[str, dict[str, int]] = {}
    for caminho, info in fs.find(raiz, detail=True).items():
        if info.get("type") == "directory" or int(info.get("size") or 0) == 0:
            continue  # pasta, ou a entrada vazia que o SeaweedFS lista como objeto
        relativo = caminho[len(raiz) + 1 :]
        if not relativo:
            continue  # a entrada do próprio prefixo, que o SeaweedFS lista como objeto
        camada = relativo.split("/", 1)[0]
        if camadas is not None and camada not in camadas:
            continue
        atual = por_camada.setdefault(camada, {"arquivos": 0, "bytes": 0})
        atual["arquivos"] += 1
        atual["bytes"] += int(info.get("size") or 0)
    return por_camada


# ----------------------------------------------------------------- fazer


def _dump_mysql(amb: Ambiente, db: str, destino: Path) -> None:
    argv = [
        "docker",
        "exec",
        "-e",
        f"MYSQL_PWD={amb.senha_root_mysql}",
        CONTAINER_MYSQL,
        "mysqldump",
        "-uroot",
        "--single-transaction",
        "--routines",
        "--triggers",
        "--events",
        "--set-gtid-purged=OFF",
        "--default-character-set=utf8mb4",
        "--add-drop-database",
        "--databases",
        db,
    ]
    with (
        _canal(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc,
        gzip.open(destino, "wb") as saida,
    ):
        if proc.stdout is None:
            raise RuntimeError("mysqldump sem canal de saída")
        shutil.copyfileobj(proc.stdout, saida)
        erro = proc.stderr.read().decode() if proc.stderr else ""
    if proc.returncode != 0:
        raise RuntimeError(f"mysqldump {db} falhou: {erro.strip()}")


def _dump_postgres(container: str, usuario: str, senha: str, banco: str, destino: Path) -> None:
    argv = [
        "docker",
        "exec",
        "-e",
        f"PGPASSWORD={senha}",
        container,
        "pg_dump",
        "-U",
        usuario,
        "-Fc",
        "--no-owner",
        banco,
    ]
    with (
        _canal(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc,
        destino.open("wb") as saida,
    ):
        if proc.stdout is None:
            raise RuntimeError("pg_dump sem canal de saída")
        shutil.copyfileobj(proc.stdout, saida)
        erro = proc.stderr.read().decode() if proc.stderr else ""
    if proc.returncode != 0:
        raise RuntimeError(f"pg_dump {banco} falhou: {erro.strip()}")


def _baixar_camada(fs: Any, bucket: str, camada: str, destino: Path) -> None:
    """Arquivo a arquivo: o `get` recursivo do s3fs tropeça na entrada de pasta que o SeaweedFS
    lista como objeto vazio e que não existe como chave."""
    for caminho, info in fs.find(f"{bucket}/{camada}", detail=True).items():
        if info.get("type") != "file" or int(info.get("size") or 0) == 0:
            continue
        local = destino / caminho[len(bucket) + 1 :]
        local.parent.mkdir(parents=True, exist_ok=True)
        fs.get_file(caminho, str(local))


def fazer(amb: Ambiente, pasta: Path, partes: Partes | None = None) -> list[Resultado]:
    """O backup na pasta: os dumps, a chave, o lake e o manifesto com as contagens."""
    p = partes or Partes()
    pasta.mkdir(parents=True, exist_ok=False)
    manifesto: dict[str, Any] = {
        "feito_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "partes": {},
        "arquivos": {},
    }
    resultados: list[Resultado] = []

    def registra(parte: str, inicio: float, detalhe: str, **contagens: Any) -> None:
        manifesto["partes"][parte] = contagens
        resultados.append(Resultado(parte, True, detalhe, round(time.monotonic() - inicio, 1)))

    if p.replica:
        inicio = time.monotonic()
        (pasta / "replica").mkdir()
        antes = contar_replica(amb, p.replica)
        for db in p.replica:
            _dump_mysql(amb, db, pasta / "replica" / f"{db}.sql.gz")
        contagens = contar_replica(amb, p.replica)
        registra(
            "replica",
            inicio,
            f"{len(p.replica)} databases, {len(contagens)} tabelas, {sum(contagens.values())} linhas",
            databases=p.replica,
            linhas=contagens,
            linhas_antes=antes,
        )
    if p.keyring:
        inicio = time.monotonic()
        (pasta / "replica").mkdir(exist_ok=True)
        chave = subprocess.run(
            ["docker", "exec", CONTAINER_MYSQL, "cat", "/var/lib/mysql-keyring/keyring"],
            capture_output=True,
            check=True,
        ).stdout  # nosec B603 B607
        (pasta / "replica" / "keyring").write_bytes(chave)
        os.chmod(pasta / "replica" / "keyring", 0o600)
        registra("keyring", inicio, f"{len(chave)} bytes", bytes=len(chave))
    if p.warehouse:
        inicio = time.monotonic()
        (pasta / "warehouse").mkdir()
        antes = contar_postgres(
            CONTAINER_DW, amb.usuario_dw, amb.senha_dw, amb.banco_dw, ESQUEMAS_DO_WAREHOUSE
        )
        _dump_postgres(
            CONTAINER_DW,
            amb.usuario_dw,
            amb.senha_dw,
            amb.banco_dw,
            pasta / "warehouse" / f"{amb.banco_dw}.dump",
        )
        contagens = contar_postgres(
            CONTAINER_DW, amb.usuario_dw, amb.senha_dw, amb.banco_dw, ESQUEMAS_DO_WAREHOUSE
        )
        registra(
            "warehouse",
            inicio,
            f"{len(contagens)} tabelas, {sum(contagens.values())} linhas",
            banco=amb.banco_dw,
            linhas=contagens,
            linhas_antes=antes,
        )
    if p.dagster:
        inicio = time.monotonic()
        (pasta / "dagster").mkdir()
        antes = contar_postgres(
            CONTAINER_DAGSTER, amb.usuario_dagster, amb.senha_dagster, amb.banco_dagster, None
        )
        _dump_postgres(
            CONTAINER_DAGSTER,
            amb.usuario_dagster,
            amb.senha_dagster,
            amb.banco_dagster,
            pasta / "dagster" / f"{amb.banco_dagster}.dump",
        )
        contagens = contar_postgres(
            CONTAINER_DAGSTER, amb.usuario_dagster, amb.senha_dagster, amb.banco_dagster, None
        )
        registra(
            "dagster",
            inicio,
            f"{len(contagens)} tabelas, {contagens.get('public.runs', 0)} execuções",
            banco=amb.banco_dagster,
            linhas=contagens,
            linhas_antes=antes,
        )
    if p.quer_lake:
        inicio = time.monotonic()
        fs = amb.lake.sistema()
        camadas = p.lake
        destino = pasta / "lake"
        destino.mkdir()
        for camada in camadas or [
            c.rsplit("/", 1)[-1] for c in fs.ls(amb.lake.bucket, detail=False)
        ]:
            if camada.startswith("_") or not fs.isdir(f"{amb.lake.bucket}/{camada}"):
                continue  # prefixos de prova e o que não é camada ficam de fora
            _baixar_camada(fs, amb.lake.bucket, camada, destino)
        contagens_lake = contar_lake(amb.lake, camadas=camadas)
        registra(
            "lake",
            inicio,
            f"{len(contagens_lake)} camadas, {sum(c['arquivos'] for c in contagens_lake.values())} arquivos, {sum(c['bytes'] for c in contagens_lake.values()) / 1e6:.1f} MB",
            camadas=contagens_lake,
        )

    for arquivo in sorted(x for x in pasta.rglob("*") if x.is_file()):
        manifesto["arquivos"][str(arquivo.relative_to(pasta))] = {
            "bytes": arquivo.stat().st_size,
            "sha256": _sha256(arquivo),
        }
    (pasta / MANIFESTO).write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return resultados


# ----------------------------------------------------------------- provar e restaurar


def ler_manifesto(pasta: Path) -> dict[str, Any]:
    manifesto: dict[str, Any] = json.loads((pasta / MANIFESTO).read_text(encoding="utf-8"))
    return manifesto


def conferir_arquivos(pasta: Path) -> list[str]:
    """Os arquivos da pasta contra o manifesto: tamanho e sha256; devolve os problemas."""
    problemas = []
    for relativo, esperado in ler_manifesto(pasta)["arquivos"].items():
        arquivo = pasta / relativo
        if not arquivo.exists():
            problemas.append(f"{relativo}: ausente")
        elif arquivo.stat().st_size != esperado["bytes"] or _sha256(arquivo) != esperado["sha256"]:
            problemas.append(f"{relativo}: diferente do manifesto")
    return problemas


def _comparar(
    esperado: dict[str, int], obtido: dict[str, int], antes: dict[str, int] | None = None
) -> list[str]:
    """O restaurado contra o manifesto. Num banco vivo, a contagem antes do dump e a de depois
    podem diferir (o Dagster registra ticks o tempo todo): o restaurado tem de cair no
    intervalo entre as duas; num banco parado, o intervalo é um ponto e a comparação é exata."""
    problemas = []
    for k, depois in esperado.items():
        piso, teto = sorted((antes.get(k, depois) if antes else depois, depois))
        valor = obtido.get(k)
        if valor is None or not piso <= valor <= teto:
            faixa = str(depois) if piso == teto else f"entre {piso} e {teto}"
            problemas.append(
                f"{k}: esperado {faixa}, obtido {'ausente' if valor is None else valor}"
            )
    return problemas


def _esperar_mysql(container: str, senha: str, tempo: int = 180) -> None:
    inicio = time.monotonic()
    while time.monotonic() - inicio < tempo:
        try:
            _mysql(container, senha, "SELECT 1")
            return
        except subprocess.CalledProcessError:
            time.sleep(3)
    raise TimeoutError(f"{container} não respondeu em {tempo} s")


def _restaurar_mysql(container: str, senha: str, dump: Path) -> None:
    with gzip.open(dump, "rb") as entrada:
        argv = [
            "docker",
            "exec",
            "-i",
            "-e",
            f"MYSQL_PWD={senha}",
            container,
            "mysql",
            "-uroot",
            "--default-character-set=utf8mb4",
        ]
        with _canal(argv, stdin=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
            if proc.stdin is None:
                raise RuntimeError("mysql sem canal de entrada")
            shutil.copyfileobj(entrada, proc.stdin)
            proc.stdin.close()
            erro = proc.stderr.read().decode() if proc.stderr else ""
    if proc.returncode != 0:
        raise RuntimeError(f"restauração de {dump.name} falhou: {erro.strip()[:400]}")


def _restaurar_postgres(
    container: str, usuario: str, senha: str, banco: str, dump: Path, limpar: bool
) -> None:
    argv = [
        "docker",
        "exec",
        "-i",
        "-e",
        f"PGPASSWORD={senha}",
        container,
        "pg_restore",
        "-U",
        usuario,
        "-d",
        banco,
        "--no-owner",
        "--exit-on-error",
    ]
    if limpar:
        argv += ["--clean", "--if-exists"]
    with dump.open("rb") as entrada:
        subprocess.run(argv, stdin=entrada, capture_output=True, check=True)  # nosec B603


def _apagar_prefixo(fs: Any, prefixo: str) -> None:
    """Apaga os arquivos do prefixo e a pasta vazia que o SeaweedFS mantém depois deles."""
    if fs.exists(prefixo):
        fs.rm(prefixo, recursive=True)
    for apagar in (fs.rm, fs.rmdir):  # o SeaweedFS pode manter a entrada da pasta vazia
        with contextlib.suppress(FileNotFoundError, OSError):
            apagar(prefixo)
    fs.invalidate_cache()


def provar(amb: Ambiente, pasta: Path, partes: Partes | None = None) -> list[Resultado]:
    """Restaura em alvos descartáveis, compara com o manifesto e apaga os alvos."""
    p = partes or Partes()
    manifesto = ler_manifesto(pasta)
    feitas = manifesto["partes"]
    resultados: list[Resultado] = []
    problemas = conferir_arquivos(pasta)
    resultados.append(
        Resultado(
            "arquivos",
            not problemas,
            "; ".join(problemas)
            or f"{len(manifesto['arquivos'])} arquivos conferem com o manifesto",
        )
    )

    if p.replica and "replica" in feitas:
        inicio = time.monotonic()
        databases = [db for db in p.replica if db in feitas["replica"]["databases"]]
        senha = secrets.token_hex(16)  # só este processo a conhece; o container morre ao fim
        with tempfile.TemporaryDirectory(prefix="prova-keyring-") as keyring:
            os.chmod(keyring, 0o777)  # nosec B103: pasta efêmera que o mysql (uid 999) do container precisa escrever
            subprocess.run(
                ["docker", "rm", "-f", CONTAINER_PROVA], capture_output=True, check=False
            )  # nosec B603 B607
            subprocess.run(  # nosec B603 B607
                [
                    "docker",
                    "run",
                    "-d",
                    "--rm",
                    "--name",
                    CONTAINER_PROVA,
                    "--user",
                    "999:999",
                    "-e",
                    f"MYSQL_ROOT_PASSWORD={senha}",
                    "-e",
                    "LANG=C.UTF-8",
                    "-v",
                    f"{keyring}:/var/lib/mysql-keyring",
                    "-v",
                    f"{RAIZ / 'infra/mysql/mysqld.my'}:/usr/sbin/mysqld.my:ro",
                    "-v",
                    f"{RAIZ / 'infra/mysql/component_keyring_file.cnf'}:/usr/lib64/mysql/plugin/component_keyring_file.cnf:ro",
                    IMAGEM_MYSQL,
                    "--default-table-encryption=ON",
                    "--character-set-server=utf8mb4",
                    "--collation-server=utf8mb4_0900_ai_ci",
                ],
                capture_output=True,
                check=True,
            )
            try:
                _esperar_mysql(CONTAINER_PROVA, senha)
                for db in databases:
                    _restaurar_mysql(CONTAINER_PROVA, senha, pasta / "replica" / f"{db}.sql.gz")
                obtido = contar_replica(amb, databases, CONTAINER_PROVA, senha)
                esperado = {
                    k: v
                    for k, v in feitas["replica"]["linhas"].items()
                    if k.split(".")[0] in databases
                }
                diferencas = _comparar(esperado, obtido, feitas["replica"].get("linhas_antes"))
                resultados.append(
                    Resultado(
                        "replica",
                        not diferencas,
                        "; ".join(diferencas[:5])
                        or f"{len(databases)} databases restaurados num MySQL efêmero: {len(esperado)} tabelas, {sum(esperado.values())} linhas, tudo confere",
                        round(time.monotonic() - inicio, 1),
                    )
                )
            finally:
                subprocess.run(
                    ["docker", "rm", "-f", CONTAINER_PROVA], capture_output=True, check=False
                )  # nosec B603 B607
    if p.keyring and "keyring" in feitas:
        chave = (pasta / "replica" / "keyring").read_bytes()
        resultados.append(
            Resultado(
                "keyring",
                len(chave) == feitas["keyring"]["bytes"] and len(chave) > 0,
                f"{len(chave)} bytes guardados",
            )
        )
    for parte, container, usuario, senha_pg, esquemas in (
        ("warehouse", CONTAINER_DW, amb.usuario_dw, amb.senha_dw, ESQUEMAS_DO_WAREHOUSE),
        ("dagster", CONTAINER_DAGSTER, amb.usuario_dagster, amb.senha_dagster, None),
    ):
        if not getattr(p, parte) or parte not in feitas:
            continue
        inicio = time.monotonic()
        banco_original = feitas[parte]["banco"]
        banco_prova = f"{banco_original}_prova"
        _psql(
            container, usuario, senha_pg, banco_original, f'DROP DATABASE IF EXISTS "{banco_prova}"'
        )
        _psql(container, usuario, senha_pg, banco_original, f'CREATE DATABASE "{banco_prova}"')
        try:
            _restaurar_postgres(
                container,
                usuario,
                senha_pg,
                banco_prova,
                pasta / parte / f"{banco_original}.dump",
                limpar=False,
            )
            obtido = contar_postgres(container, usuario, senha_pg, banco_prova, esquemas)
            diferencas = _comparar(
                feitas[parte]["linhas"], obtido, feitas[parte].get("linhas_antes")
            )
            resultados.append(
                Resultado(
                    parte,
                    not diferencas,
                    "; ".join(diferencas[:5])
                    or f"restaurado em {banco_prova}: {len(obtido)} tabelas, {sum(obtido.values())} linhas, tudo confere",
                    round(time.monotonic() - inicio, 1),
                )
            )
        finally:
            _psql(
                container,
                usuario,
                senha_pg,
                banco_original,
                f'DROP DATABASE IF EXISTS "{banco_prova}"',
            )
    if p.quer_lake and "lake" in feitas:
        inicio = time.monotonic()
        fs = amb.lake.sistema()
        prefixo = f"{amb.lake.bucket}/{PREFIXO_DE_PROVA}"
        _apagar_prefixo(fs, prefixo)
        try:
            camadas = (
                list(feitas["lake"]["camadas"])
                if p.lake is None
                else [c for c in p.lake if c in feitas["lake"]["camadas"]]
            )
            for camada in camadas:
                fs.put(str(pasta / "lake" / camada), f"{prefixo}/{camada}", recursive=True)
            fs.invalidate_cache()
            do_lake = contar_lake(amb.lake, PREFIXO_DE_PROVA, camadas)
            esperado = {c: feitas["lake"]["camadas"][c] for c in camadas}
            diferencas = [
                f"{c}: esperado {esperado[c]}, obtido {do_lake.get(c)}"
                for c in esperado
                if do_lake.get(c) != esperado[c]
            ]
            resultados.append(
                Resultado(
                    "lake",
                    not diferencas,
                    "; ".join(diferencas)
                    or f"{len(camadas)} camadas restauradas em {PREFIXO_DE_PROVA}/: {sum(e['arquivos'] for e in esperado.values())} arquivos, bytes iguais",
                    round(time.monotonic() - inicio, 1),
                )
            )
        finally:
            _apagar_prefixo(fs, prefixo)
    return resultados


def restaurar(amb: Ambiente, pasta: Path, partes: Partes | None = None) -> list[Resultado]:
    """A restauração de verdade, nos alvos reais: destrutiva, só com `--sim`."""
    p = partes or Partes()
    feitas = ler_manifesto(pasta)["partes"]
    resultados: list[Resultado] = []
    problemas = conferir_arquivos(pasta)
    if problemas:
        raise RuntimeError("a pasta não confere com o manifesto: " + "; ".join(problemas))
    if p.replica and "replica" in feitas:
        inicio = time.monotonic()
        databases = [db for db in p.replica if db in feitas["replica"]["databases"]]
        for db in databases:
            _restaurar_mysql(
                CONTAINER_MYSQL, amb.senha_root_mysql, pasta / "replica" / f"{db}.sql.gz"
            )
        obtido = contar_replica(amb, databases)
        esperado = {
            k: v for k, v in feitas["replica"]["linhas"].items() if k.split(".")[0] in databases
        }
        diferencas = _comparar(esperado, obtido, feitas["replica"].get("linhas_antes"))
        resultados.append(
            Resultado(
                "replica",
                not diferencas,
                "; ".join(diferencas[:5]) or f"{len(databases)} databases restaurados na réplica",
                round(time.monotonic() - inicio, 1),
            )
        )
    for parte, container, usuario, senha_pg, esquemas in (
        ("warehouse", CONTAINER_DW, amb.usuario_dw, amb.senha_dw, ESQUEMAS_DO_WAREHOUSE),
        ("dagster", CONTAINER_DAGSTER, amb.usuario_dagster, amb.senha_dagster, None),
    ):
        if not getattr(p, parte) or parte not in feitas:
            continue
        inicio = time.monotonic()
        banco = feitas[parte]["banco"]
        _restaurar_postgres(
            container, usuario, senha_pg, banco, pasta / parte / f"{banco}.dump", limpar=True
        )
        obtido = contar_postgres(container, usuario, senha_pg, banco, esquemas)
        diferencas = _comparar(feitas[parte]["linhas"], obtido, feitas[parte].get("linhas_antes"))
        resultados.append(
            Resultado(
                parte,
                not diferencas,
                "; ".join(diferencas[:5]) or f"{banco} restaurado",
                round(time.monotonic() - inicio, 1),
            )
        )
    if p.quer_lake and "lake" in feitas:
        inicio = time.monotonic()
        fs = amb.lake.sistema()
        camadas = (
            list(feitas["lake"]["camadas"])
            if p.lake is None
            else [c for c in p.lake if c in feitas["lake"]["camadas"]]
        )
        for camada in camadas:
            fs.put(str(pasta / "lake" / camada), f"{amb.lake.bucket}/{camada}", recursive=True)
        fs.invalidate_cache()
        do_lake = contar_lake(amb.lake, camadas=camadas)
        esperado = {c: feitas["lake"]["camadas"][c] for c in camadas}
        diferencas = [
            f"{c}: esperado {esperado[c]}, obtido {do_lake.get(c)}"
            for c in esperado
            if do_lake.get(c) != esperado[c]
        ]
        resultados.append(
            Resultado(
                "lake",
                not diferencas,
                "; ".join(diferencas) or f"{len(camadas)} camadas restauradas no bucket",
                round(time.monotonic() - inicio, 1),
            )
        )
    return resultados


def texto(resultados: list[Resultado]) -> str:
    linhas = [
        f"  {'✓' if r.ok else '✗'} {r.parte:10} {r.detalhe}"
        + (f" ({r.segundos} s)" if r.segundos else "")
        for r in resultados
    ]
    return "\n".join(linhas)
