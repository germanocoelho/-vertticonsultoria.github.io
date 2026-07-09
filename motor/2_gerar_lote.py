#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOTOR VERTTI — Passo 2: RAIOS GEOGRÁFICOS + PRIORIDADE JUCEMS -> lote do mês

Roda em segundos sobre a base local (`base_ms.sqlite`) criada no Passo 1.

A LÓGICA DOS RAIOS
------------------
O mercado é atacado em anéis a partir da sua sede, do mais quente ao
mais frio. O lote de cada mês esgota primeiro o Raio 1; sobrando cota,
avança para o Raio 2, e assim por diante:

  RAIO 1 — Campo Grande (sua praça: reunião presencial fecha contrato)
  RAIO 2 — Entorno imediato (até ~100 km: Terenos, Sidrolândia, Jaraguari,
           Rochedo, Corguinho, Dois Irmãos do Buriti, Nova Alvorada do Sul,
           Ribas do Rio Pardo, Bandeirantes)
  RAIO 3 — Polos regionais (Dourados, Três Lagoas, Corumbá, Ponta Porã,
           Naviraí, Nova Andradina, Aquidauana, Paranaíba, Coxim, Maracaju,
           Chapadão do Sul, São Gabriel do Oeste, Amambai)
  RAIO 4 — Demais municípios de MS

O SINAL JUCEMS
--------------
Dentro de cada raio, os municípios são ordenados pelo momento de abertura
de empresas — o mesmo sinal do Mapa de Empresas/JUCEMS. Duas fontes:

  (a) AUTOMÁTICA (padrão): o próprio motor conta as aberturas do período
      na base destilada, município a município. É exatamente a estatística
      que a JUCEMS publica, calculada aqui de graça e sem depender de
      formato de planilha alheia.
  (b) OFICIAL (opcional): se você baixar a planilha mensal da JUCEMS /
      Mapa de Empresas (gov.br/empresas-e-negocios -> Mapa de Empresas),
      salve como CSV com colunas MUNICIPIO;ABERTURAS e passe em
      --jucems arquivo.csv — os números oficiais substituem a contagem.

USO
---
    python 2_gerar_lote.py --meses 3 --lote 100
    python 2_gerar_lote.py --meses 3 --lote 100 --jucems jucems_2026_07.csv
    python 2_gerar_lote.py --meses 3 --lote 100 --raios 1,2   # só CG + entorno

Saída: lote_bruto.csv (segue para o Passo 3, que cruza com o INPI)
"""
import argparse
import csv
import re
import sqlite3
import sys
import unicodedata

# ----------------------------------------------------------------------
RAIOS = {
    1: ["CAMPO GRANDE"],
    2: ["TERENOS", "SIDROLANDIA", "JARAGUARI", "ROCHEDO", "CORGUINHO",
        "DOIS IRMAOS DO BURITI", "NOVA ALVORADA DO SUL", "RIBAS DO RIO PARDO",
        "BANDEIRANTES"],
    3: ["DOURADOS", "TRES LAGOAS", "CORUMBA", "PONTA PORA", "NAVIRAI",
        "NOVA ANDRADINA", "AQUIDAUANA", "PARANAIBA", "COXIM", "MARACAJU",
        "CHAPADAO DO SUL", "SAO GABRIEL DO OESTE", "AMAMBAI"],
    # Raio 4 = qualquer outro município de MS (calculado por exclusão)
}

CNAES_PRIORITARIOS = (
    "10", "11", "14", "15", "20", "21", "3101", "3102", "47", "55", "56",
    "58", "59", "60", "62", "63", "70", "71", "72", "73", "74", "85", "86",
    "90", "93", "9602",
)

EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")
EMAILS_DESCARTAR = ("contab", "escritorio", "@cont.")


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").upper().strip()


def raio_do(nome_mun):
    for r, lista in RAIOS.items():
        if nome_mun in lista:
            return r
    return 4


def email_ok(e):
    return bool(EMAIL_RE.match(e)) and not any(m in e for m in EMAILS_DESCARTAR)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="base_ms.sqlite")
    ap.add_argument("--meses", type=int, default=3)
    ap.add_argument("--lote", type=int, default=100)
    ap.add_argument("--raios", default="1,2,3,4")
    ap.add_argument("--jucems", default=None,
                    help="CSV opcional MUNICIPIO;ABERTURAS (dados oficiais)")
    ap.add_argument("--saida", default="lote_bruto.csv")
    args = ap.parse_args()

    raios_ativos = [int(x) for x in args.raios.split(",")]
    con = sqlite3.connect(args.db)
    mun = {cod: nome for cod, nome in con.execute("SELECT cod, nome FROM municipios")}

    from datetime import date, timedelta
    corte = (date.today() - timedelta(days=args.meses * 31)).strftime("%Y%m%d")

    tem_empresas = con.execute(
        "SELECT name FROM sqlite_master WHERE name='empresas_ms'").fetchone()

    # ---- sinal de prioridade por município -------------------------------
    momento = {}
    if args.jucems:
        with open(args.jucems, encoding="utf-8") as f:
            for row in csv.reader(f, delimiter=";"):
                if len(row) >= 2 and row[1].strip().isdigit():
                    momento[norm(row[0])] = int(row[1])
        print(f"Sinal JUCEMS oficial carregado: {len(momento)} municípios.")
    else:
        for cod, n in con.execute(
                "SELECT municipio_cod, COUNT(*) FROM estab_ms "
                "WHERE data_inicio >= ? AND situacao='02' GROUP BY municipio_cod",
                (corte,)):
            momento[mun.get(cod, cod)] = n
        print("Sinal de momento calculado da própria base (equivalente JUCEMS).")

    # ---- seleção ---------------------------------------------------------
    q = """SELECT e.cnpj, e.cnpj_basico, e.nome_fantasia, e.cnae, e.data_inicio,
                  e.municipio_cod, e.bairro, e.ddd, e.telefone, e.email
           FROM estab_ms e
           WHERE e.situacao='02' AND e.matriz='1' AND e.data_inicio >= ?
                 AND e.email <> ''"""
    candidatos = []
    for row in con.execute(q, (corte,)):
        cnpj, basico, fantasia, cnae, ini, mcod, bairro, ddd, tel, email = row
        if not any(cnae.startswith(p) for p in CNAES_PRIORITARIOS):
            continue
        if not email_ok(email):
            continue
        nome_mun = mun.get(mcod, "?")
        r = raio_do(nome_mun)
        if r not in raios_ativos:
            continue
        candidatos.append((r, -momento.get(nome_mun, 0), nome_mun, cnpj, basico,
                           fantasia, cnae, ini, bairro, ddd, tel, email))

    # ordena: raio crescente -> momento decrescente -> abertura mais recente
    candidatos.sort(key=lambda c: (c[0], c[1], c[7]), reverse=False)
    lote = candidatos[: args.lote]

    razoes = {}
    if tem_empresas:
        razoes = dict(con.execute(
            "SELECT cnpj_basico, razao_social FROM empresas_ms"))

    with open(args.saida, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["RAIO", "MUNICIPIO", "CNPJ", "RAZAO_SOCIAL", "NOME_FANTASIA",
                    "CNAE", "DATA_ABERTURA", "BAIRRO", "DDD", "TELEFONE", "EMAIL"])
        for c in lote:
            r, _neg, nome_mun, cnpj, basico, fantasia, cnae, ini, bairro, ddd, tel, email = c
            w.writerow([r, nome_mun, cnpj, razoes.get(basico, ""), fantasia,
                        cnae, ini, bairro, ddd, tel, email])

    print(f"\nCandidatos qualificados: {len(candidatos):,}")
    print(f"Lote gerado ({len(lote)} contatos, raios {raios_ativos}): {args.saida}")
    resumo = {}
    for c in lote:
        resumo[c[0]] = resumo.get(c[0], 0) + 1
    for r in sorted(resumo):
        print(f"  Raio {r}: {resumo[r]} contatos")
    print("\nPróximo passo: python 3_cruzar_inpi_exportar.py --lote " + args.saida)


if __name__ == "__main__":
    main()
