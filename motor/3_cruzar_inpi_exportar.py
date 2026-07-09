#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOTOR VERTTI — Passo 3: FILTRO INPI (grátis, via RPI) + EXPORTAÇÃO BREVO

O PROBLEMA DA API PAGA — E A SOLUÇÃO GRATUITA
---------------------------------------------
Consultar marca por CNPJ em API paga custa por consulta. A alternativa
gratuita e definitiva: a própria Revista da Propriedade Industrial (RPI),
publicada toda terça-feira em XML aberto em
    https://revistas.inpi.gov.br/txt/RM{numero}.zip
Este script acumula, semana a semana, os TITULARES DE MS que aparecem na
RPI numa base local (`marcas_ms.sqlite`). Com o tempo, você constrói de
graça o que a API cobra para responder.

LIMITAÇÃO HONESTA (e por que ela quase não importa aqui)
--------------------------------------------------------
O XML da RPI identifica o titular por RAZÃO SOCIAL + UF, não por CNPJ.
O cruzamento é feito por nome normalizado + UF=MS — heurística com
pequena chance de falso-negativo. Só que o alvo do motor são empresas
ABERTAS HÁ POUCOS MESES: a probabilidade de já terem marca é mínima.
O filtro serve para não constranger a exceção, e a checagem manual dos
links gerados cobre o resto no lote piloto.

USO
---
    # (semanal ou mensal) acumular RPIs na base local — informe o intervalo:
    python 3_cruzar_inpi_exportar.py --baixar-rpi 2870 2885

    # (mensal) cruzar o lote e exportar para o Brevo:
    python 3_cruzar_inpi_exportar.py --lote lote_bruto.csv

Saídas:
    prospectos_brevo.csv  -> importar direto no Brevo
    conferencia_inpi.csv  -> links de checagem manual por empresa
"""
import argparse
import csv
import io
import re
import sqlite3
import sys
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

DB = "marcas_ms.sqlite"  # sobrescrito por --db-marcas
RPI_URL = "https://revistas.inpi.gov.br/txt/RM{n}.zip"

SUFIXOS = (" LTDA", " ME", " EPP", " EIRELI", " SA", " S A", " S/A",
           " SOCIEDADE ANONIMA", " LIMITADA", " - ", ".")


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").upper()
    for suf in SUFIXOS:
        s = s.replace(suf, " ")
    return re.sub(r"[^A-Z0-9 ]", " ", s).strip()


def abrir_db():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS titulares_ms (
        razao_norm TEXT PRIMARY KEY, razao_original TEXT, primeira_rpi INTEGER)""")
    con.execute("""CREATE TABLE IF NOT EXISTS rpis_lidas (
        numero INTEGER PRIMARY KEY)""")
    return con


def baixar_rpis(inicio, fim):
    con = abrir_db()
    ja = {r[0] for r in con.execute("SELECT numero FROM rpis_lidas")}
    for n in range(inicio, fim + 1):
        if n in ja:
            print(f"RPI {n}: já processada, pulando.")
            continue
        url = RPI_URL.format(n=n)
        print(f"RPI {n}: baixando {url} ...")
        try:
            dados = urllib.request.urlopen(url, timeout=120).read()
        except Exception as exc:
            print(f"  falhou ({exc}) — siga para a próxima; re-rode depois.")
            continue
        novos = 0
        try:
            with zipfile.ZipFile(io.BytesIO(dados)) as z:
                for name in z.namelist():
                    if not name.lower().endswith(".xml"):
                        continue
                    tree = ET.parse(z.open(name))
                    for tit in tree.iter("titular"):
                        uf = (tit.get("uf") or "").upper()
                        nome = tit.get("nome-razao-social") or ""
                        if uf == "MS" and nome:
                            rn = norm(nome)
                            if rn:
                                cur = con.execute(
                                    "INSERT OR IGNORE INTO titulares_ms VALUES (?,?,?)",
                                    (rn, nome.strip(), n))
                                novos += cur.rowcount
        except zipfile.BadZipFile:
            print("  arquivo inválido — número de RPI pode não existir ainda.")
            continue
        con.execute("INSERT OR IGNORE INTO rpis_lidas VALUES (?)", (n,))
        con.commit()
        print(f"  titulares MS novos nesta RPI: {novos}")
    total = con.execute("SELECT COUNT(*) FROM titulares_ms").fetchone()[0]
    print(f"\nBase local INPI/MS: {total:,} titulares acumulados.")


def link_busca_inpi(nome):
    # Link da busca pública do INPI (marcas) pré-preenchível não é estável;
    # geramos a URL da busca e o termo para colar — checagem em 10 segundos.
    return ("https://busca.inpi.gov.br/pePI/jsp/marcas/Pesquisa_num_processo.jsp"
            "  [buscar por titular: " + nome + "]")


def cruzar(lote_csv):
    con = abrir_db()
    titulares = {r[0] for r in con.execute("SELECT razao_norm FROM titulares_ms")}
    print(f"Base INPI local: {len(titulares):,} titulares de MS.")

    mantidos, removidos = [], []
    with open(lote_csv, encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for row in rd:
            chave = norm(row.get("RAZAO_SOCIAL") or row.get("NOME_FANTASIA") or "")
            if chave and chave in titulares:
                removidos.append(row)
            else:
                mantidos.append(row)

    # dedupe por e-mail (mesmo contador cadastrando várias empresas etc.)
    vistos, finais = set(), []
    for row in mantidos:
        e = row["EMAIL"].strip().lower()
        if e in vistos:
            continue
        vistos.add(e)
        finais.append(row)

    with open("prospectos_brevo.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        # Cabeçalho no padrão de atributos do Brevo
        w.writerow(["EMAIL", "NOME_EMPRESA", "MUNICIPIO", "CNPJ",
                    "CNAE", "DATA_ABERTURA", "TELEFONE"])
        for r in finais:
            nome_exib = (r.get("NOME_FANTASIA") or r.get("RAZAO_SOCIAL") or "").title()
            tel = (r.get("DDD", "") + r.get("TELEFONE", "")).strip()
            w.writerow([r["EMAIL"], nome_exib, r["MUNICIPIO"].title(), r["CNPJ"],
                        r["CNAE"], r["DATA_ABERTURA"], tel])

    with open("conferencia_inpi.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["NOME_EMPRESA", "STATUS", "CHECAGEM_MANUAL"])
        for r in finais:
            nome = r.get("RAZAO_SOCIAL") or r.get("NOME_FANTASIA") or ""
            w.writerow([nome, "sem marca localizada (heurística)",
                        link_busca_inpi(nome)])
        for r in removidos:
            nome = r.get("RAZAO_SOCIAL") or r.get("NOME_FANTASIA") or ""
            w.writerow([nome, "REMOVIDO: possível marca existente",
                        link_busca_inpi(nome)])

    print(f"Lote de entrada: {len(mantidos) + len(removidos)}")
    print(f"Removidos (possível marca já registrada): {len(removidos)}")
    print(f"Prospectos finais (dedupe por e-mail): {len(finais)}")
    print("\nArquivos gerados: prospectos_brevo.csv | conferencia_inpi.csv")
    print("Suba prospectos_brevo.csv no Brevo e dispare a sequência do Bloco 2.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--baixar-rpi", nargs=2, type=int, metavar=("INICIO", "FIM"))
    ap.add_argument("--lote", default=None)
    ap.add_argument("--db-marcas", default=None,
                    help="caminho do marcas_ms.sqlite (padrão: pasta atual)")
    args = ap.parse_args()
    if args.db_marcas:
        globals()["DB"] = args.db_marcas
    if args.baixar_rpi:
        baixar_rpis(args.baixar_rpi[0], args.baixar_rpi[1])
    elif args.lote:
        cruzar(args.lote)
    else:
        sys.exit("Use --baixar-rpi INICIO FIM ou --lote lote_bruto.csv")
