#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOTOR VERTTI — Passo 1: A DESTILARIA (Receita Federal -> base local só-MS)

PROBLEMA QUE ESTE SCRIPT RESOLVE
--------------------------------
A base completa do CNPJ tem ~60 GB descompactados. Ler tudo a cada lote
mensal é inviável. A solução é destilar UMA VEZ: uma única passada de
leitura em streaming (direto de dentro dos ZIPs, sem descompactar) que
guarda apenas as linhas de MS num SQLite local (`base_ms.sqlite`,
~100-200 MB). Depois disso, TODOS os filtros — raios geográficos, CNAE,
recência, e-mail — rodam em segundos sobre a base local, sem nunca mais
tocar nos arquivos gigantes.

No mês seguinte, você baixa só os novos Estabelecimentos*.zip e roda de
novo: o script detecta a referência (AAAA-MM) e substitui a base antiga.

ONDE BAIXAR (grátis, mensal)
----------------------------
https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/
  -> Estabelecimentos0.zip ... Estabelecimentos9.zip  (obrigatórios)
  -> Municipios.zip                                    (obrigatório, pequeno)
  -> Empresas0.zip ... Empresas9.zip                   (opcional: razão social/porte)

USO
---
    python 1_destilar_ms.py --pasta ./dados_receita --ref 2026-07
    # com razão social (recomendado; um pouco mais demorado):
    python 1_destilar_ms.py --pasta ./dados_receita --ref 2026-07 --com-empresas
"""
import argparse
import csv
import io
import os
import sqlite3
import sys
import unicodedata
import zipfile

csv.field_size_limit(10_000_000)

# Layout oficial ESTABELECIMENTOS (dicionário de dados da Receita)
E = dict(cnpj_basico=0, cnpj_ordem=1, cnpj_dv=2, matriz_filial=3, nome_fantasia=4,
         situacao=5, data_situacao=6, data_inicio=10, cnae=11, cnae_sec=12,
         tipo_logr=13, logr=14, num=15, compl=16, bairro=17, cep=18, uf=19,
         municipio=20, ddd1=21, tel1=22, email=27)

# Layout oficial EMPRESAS
EMP = dict(cnpj_basico=0, razao_social=1, natureza=2, capital=4, porte=5)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").upper().strip()


def zips_de(pasta, prefixo):
    return sorted(os.path.join(pasta, f) for f in os.listdir(pasta)
                  if f.lower().startswith(prefixo.lower()) and f.lower().endswith(".zip"))


def linhas_do_zip(zpath):
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():
            with z.open(name) as raw:
                txt = io.TextIOWrapper(raw, encoding="latin-1", newline="")
                yield from csv.reader(txt, delimiter=";")


def carregar_municipios(pasta, con):
    """Municipios.zip: código TOM -> nome. Essencial para os raios."""
    zs = zips_de(pasta, "Municipios")
    if not zs:
        sys.exit("Municipios.zip não encontrado — baixe junto com os Estabelecimentos.")
    con.execute("DROP TABLE IF EXISTS municipios")
    con.execute("CREATE TABLE municipios (cod TEXT PRIMARY KEY, nome TEXT)")
    n = 0
    for row in linhas_do_zip(zs[0]):
        if len(row) >= 2:
            con.execute("INSERT OR REPLACE INTO municipios VALUES (?,?)",
                        (row[0], norm(row[1])))
            n += 1
    con.commit()
    print(f"  municípios carregados: {n:,}")


def destilar_estabelecimentos(pasta, con):
    con.execute("DROP TABLE IF EXISTS estab_ms")
    con.execute("""CREATE TABLE estab_ms (
        cnpj TEXT PRIMARY KEY, cnpj_basico TEXT, nome_fantasia TEXT,
        situacao TEXT, data_inicio TEXT, cnae TEXT, cnae_sec TEXT,
        endereco TEXT, bairro TEXT, cep TEXT, municipio_cod TEXT,
        ddd TEXT, telefone TEXT, email TEXT, matriz TEXT)""")
    zs = zips_de(pasta, "Estabelecimentos")
    if not zs:
        sys.exit("Nenhum Estabelecimentos*.zip encontrado na pasta.")
    lidas = gravadas = 0
    for zpath in zs:
        print(f"  destilando {os.path.basename(zpath)} ...")
        lote = []
        for row in linhas_do_zip(zpath):
            lidas += 1
            try:
                if row[E["uf"]] != "MS":
                    continue
                cnpj = row[E["cnpj_basico"]] + row[E["cnpj_ordem"]] + row[E["cnpj_dv"]]
                end = " ".join(x for x in (row[E["tipo_logr"]], row[E["logr"]],
                                            row[E["num"]]) if x).strip()
                lote.append((cnpj, row[E["cnpj_basico"]], row[E["nome_fantasia"]].strip(),
                             row[E["situacao"]], row[E["data_inicio"]], row[E["cnae"]],
                             row[E["cnae_sec"]], end, row[E["bairro"]].strip(),
                             row[E["cep"]], row[E["municipio"]], row[E["ddd1"]],
                             row[E["tel1"]], row[E["email"]].strip().lower(),
                             row[E["matriz_filial"]]))
                if len(lote) >= 5000:
                    con.executemany(
                        "INSERT OR REPLACE INTO estab_ms VALUES "
                        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", lote)
                    gravadas += len(lote)
                    lote = []
            except IndexError:
                continue
        if lote:
            con.executemany("INSERT OR REPLACE INTO estab_ms VALUES "
                            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", lote)
            gravadas += len(lote)
        con.commit()
    print(f"  linhas lidas: {lidas:,} | estabelecimentos MS gravados: {gravadas:,}")


def destilar_empresas(pasta, con):
    """Só as razões sociais dos CNPJs básicos que já estão na base MS."""
    con.execute("DROP TABLE IF EXISTS empresas_ms")
    con.execute("""CREATE TABLE empresas_ms (
        cnpj_basico TEXT PRIMARY KEY, razao_social TEXT, porte TEXT)""")
    basicos = {r[0] for r in con.execute("SELECT DISTINCT cnpj_basico FROM estab_ms")}
    print(f"  buscando razão social de {len(basicos):,} CNPJs básicos ...")
    zs = zips_de(pasta, "Empresas")
    if not zs:
        print("  (Empresas*.zip não encontrados — pulando; razão social ficará vazia)")
        return
    n = 0
    for zpath in zs:
        print(f"  varrendo {os.path.basename(zpath)} ...")
        lote = []
        for row in linhas_do_zip(zpath):
            try:
                if row[EMP["cnpj_basico"]] in basicos:
                    lote.append((row[EMP["cnpj_basico"]],
                                 row[EMP["razao_social"]].strip(),
                                 row[EMP["porte"]]))
                    if len(lote) >= 2000:
                        con.executemany(
                            "INSERT OR REPLACE INTO empresas_ms VALUES (?,?,?)", lote)
                        n += len(lote)
                        lote = []
            except IndexError:
                continue
        if lote:
            con.executemany("INSERT OR REPLACE INTO empresas_ms VALUES (?,?,?)", lote)
            n += len(lote)
        con.commit()
    print(f"  razões sociais gravadas: {n:,}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", required=True)
    ap.add_argument("--ref", required=True, help="referência da base, ex.: 2026-07")
    ap.add_argument("--com-empresas", action="store_true")
    ap.add_argument("--db", default="base_ms.sqlite")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    ref_atual = con.execute("SELECT v FROM meta WHERE k='ref'").fetchone()
    if ref_atual and ref_atual[0] == args.ref:
        print(f"Base {args.ref} já destilada em {args.db}. Nada a fazer.")
        return

    print(f"== Destilaria VERTTI — referência {args.ref} ==")
    carregar_municipios(args.pasta, con)
    destilar_estabelecimentos(args.pasta, con)
    if args.com_empresas:
        destilar_empresas(args.pasta, con)
    con.execute("CREATE INDEX IF NOT EXISTS ix_mun ON estab_ms(municipio_cod)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_ini ON estab_ms(data_inicio)")
    con.execute("INSERT OR REPLACE INTO meta VALUES ('ref', ?)", (args.ref,))
    con.commit()
    con.close()
    tam = os.path.getsize(args.db) / 1e6
    print(f"\nPronto: {args.db} ({tam:.0f} MB). Daqui em diante tudo roda local, "
          "em segundos, sem reler os ZIPs.")


if __name__ == "__main__":
    main()
