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
    ap.add_argument("--expirar-meses", type=int, default=15,
                    help="desiste de um candidato se ficou este tempo na fila sem "
                         "ser selecionado (padrão: 15 meses)")
    ap.add_argument("--saida", default="lote_bruto.csv")
    ap.add_argument("--fila-leve", default="motor_fila_leve.csv",
                    help="arquivo leve (poucas linhas) com a fila pendente, "
                         "o unico pedaco da fila persistente pequeno o bastante "
                         "para ser commitado no git a cada execucao -- o banco "
                         "completo (base_ms.sqlite, centenas de MB com todas as "
                         "974 mil empresas de MS) nunca vai para o repositorio")
    args = ap.parse_args()

    raios_ativos = [int(x) for x in args.raios.split(",")]
    con = sqlite3.connect(args.db)
    tem_municipios = con.execute(
        "SELECT name FROM sqlite_master WHERE name='municipios'").fetchone()
    mun = {}
    if tem_municipios:
        mun = {cod: nome for cod, nome in con.execute("SELECT cod, nome FROM municipios")}

    from datetime import date, timedelta
    hoje = date.today()
    corte = (hoje - timedelta(days=args.meses * 31)).strftime("%Y%m%d")
    corte_expira = (hoje - timedelta(days=args.expirar_meses * 31)).strftime("%Y-%m-%d")

    tem_empresas = con.execute(
        "SELECT name FROM sqlite_master WHERE name='empresas_ms'").fetchone()

    # ------------------------------------------------------------------
    # FILA PERSISTENTE — corrige o risco de "envelhecimento silencioso":
    # sem isso, uma empresa que aparece como candidata mas não cabe no
    # lote de um mês (corte da janela rolante de --meses) podia desaparecer
    # para sempre, sem nunca ter sido contatada, assim que a janela avançasse.
    # Agora, toda empresa elegível entra na fila UMA VEZ e só sai dela quando
    # for de fato selecionada num lote, ou quando expirar (--expirar-meses).
    # ------------------------------------------------------------------
    con.execute("""CREATE TABLE IF NOT EXISTS fila_candidatos (
        cnpj TEXT PRIMARY KEY, cnpj_basico TEXT, nome_fantasia TEXT, cnae TEXT,
        municipio_cod TEXT, bairro TEXT, ddd TEXT, telefone TEXT, email TEXT,
        raio INTEGER, data_inicio TEXT, primeiro_visto TEXT, selecionado TEXT)""")

    # ---- importa a fila leve persistida (motor_fila_leve.csv), se existir --
    # é o unico jeito da fila sobreviver de uma execucao do GitHub Actions
    # para a proxima: o banco base_ms.sqlite inteiro (250+ MB) nunca é
    # commitado (nem caberia -- GitHub recusa arquivo acima de 100 MB), entao
    # cada execucao começa com um banco novo e vazio. Sem este import, a fila
    # "persistente" reiniciava do zero todo santo dia.
    import os as _os
    importados = 0
    if _os.path.exists(args.fila_leve):
        with open(args.fila_leve, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                cur = con.execute(
                    """INSERT OR IGNORE INTO fila_candidatos
                       (cnpj, cnpj_basico, nome_fantasia, cnae, municipio_cod, bairro,
                        ddd, telefone, email, raio, data_inicio, primeiro_visto, selecionado)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                    (row["cnpj"], row["cnpj_basico"], row["nome_fantasia"], row["cnae"],
                     row["municipio_cod"], row["bairro"], row["ddd"], row["telefone"],
                     row["email"], int(row["raio"]), row["data_inicio"], row["primeiro_visto"]))
                importados += cur.rowcount
        con.commit()
        print(f"Fila leve importada de '{args.fila_leve}': {importados} candidatos pendentes recuperados.")
    else:
        print(f"Nenhuma fila leve encontrada em '{args.fila_leve}' (primeira execução, ou arquivo ainda não commitado).")

    tem_estab = con.execute(
        "SELECT name FROM sqlite_master WHERE name='estab_ms'").fetchone()

    # ---- sinal de prioridade por município -------------------------------
    momento = {}
    if args.jucems:
        with open(args.jucems, encoding="utf-8") as f:
            for row in csv.reader(f, delimiter=";"):
                if len(row) >= 2 and row[1].strip().isdigit():
                    momento[norm(row[0])] = int(row[1])
        print(f"Sinal JUCEMS oficial carregado: {len(momento)} municípios.")
    elif tem_estab:
        for cod, n in con.execute(
                "SELECT municipio_cod, COUNT(*) FROM estab_ms "
                "WHERE data_inicio >= ? AND situacao='02' GROUP BY municipio_cod",
                (corte,)):
            momento[mun.get(cod, cod)] = n
        print("Sinal de momento calculado da própria base (equivalente JUCEMS).")
    else:
        print("Execução sem base completa (modo diário): sem sinal de momento novo, "
              "usando apenas a ordem de chegada dentro da fila já persistida.")

    # ---- passo 1: todo mundo elegível na janela recente ENTRA na fila -----
    # só roda quando a base completa (estab_ms) está presente -- ou seja, só
    # no ciclo mensal, logo após 0_baixar_receita.py + 1_destilar_ms.py. Na
    # execução diária isso não existe (só 250 MB de download já inviabiliza
    # rodar isso todo dia), então o disparo diário trabalha exclusivamente
    # com quem já está na fila leve persistida.
    novos = 0
    if tem_estab:
        q = """SELECT e.cnpj, e.cnpj_basico, e.nome_fantasia, e.cnae, e.data_inicio,
                      e.municipio_cod, e.bairro, e.ddd, e.telefone, e.email
               FROM estab_ms e
               WHERE e.situacao='02' AND e.matriz='1' AND e.data_inicio >= ?
                     AND e.email <> ''"""
        for row in con.execute(q, (corte,)):
            cnpj, basico, fantasia, cnae, ini, mcod, bairro, ddd, tel, email = row
            if not any(cnae.startswith(p) for p in CNAES_PRIORITARIOS):
                continue
            if not email_ok(email):
                continue
            nome_mun = mun.get(mcod, "?")
            r = raio_do(nome_mun)
            cur = con.execute(
                """INSERT OR IGNORE INTO fila_candidatos
                   (cnpj, cnpj_basico, nome_fantasia, cnae, municipio_cod, bairro,
                    ddd, telefone, email, raio, data_inicio, primeiro_visto, selecionado)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                (cnpj, basico, fantasia, cnae, mcod, bairro, ddd, tel, email, r, ini,
                 hoje.isoformat()))
            novos += cur.rowcount
        con.commit()
    print(f"Fila persistente: {novos} candidatos novos entraram nesta execução.")

    # ---- passo 2: expira quem ficou tempo demais na fila sem ser chamado --
    expirados = con.execute(
        "SELECT COUNT(*) FROM fila_candidatos WHERE selecionado IS NULL "
        "AND primeiro_visto < ?", (corte_expira,)).fetchone()[0]
    if expirados:
        con.execute("DELETE FROM fila_candidatos WHERE selecionado IS NULL "
                    "AND primeiro_visto < ?", (corte_expira,))
        con.commit()
        print(f"Fila persistente: {expirados} candidatos expiraram "
              f"(mais de {args.expirar_meses} meses na fila sem ser contatados).")

    # ---- passo 3: seleção do lote vem da FILA, não da janela do mês -------
    # (assim, quem entrou há 2 meses e não coube no lote de então continua
    # na frente da fila agora, em vez de ter sumido silenciosamente)
    placeholders = ",".join("?" * len(raios_ativos))
    pendentes = con.execute(
        f"""SELECT cnpj, cnpj_basico, nome_fantasia, cnae, municipio_cod, bairro,
                   ddd, telefone, email, raio, data_inicio, primeiro_visto
            FROM fila_candidatos
            WHERE selecionado IS NULL AND raio IN ({placeholders})""",
        raios_ativos).fetchall()

    candidatos = []
    for (cnpj, basico, fantasia, cnae, mcod, bairro, ddd, tel, email, r,
         ini, primeiro_visto) in pendentes:
        nome_mun = mun.get(mcod, "?")
        candidatos.append((r, -momento.get(nome_mun, 0), primeiro_visto, nome_mun,
                           cnpj, basico, fantasia, cnae, ini, bairro, ddd, tel, email))

    # ordena: raio crescente -> cidade mais quente primeiro -> quem está na
    # fila há mais tempo primeiro (evita novo envelhecimento dentro da própria fila)
    candidatos.sort(key=lambda c: (c[0], c[1], c[2]))
    lote = candidatos[: args.lote]

    if lote:
        con.executemany(
            "UPDATE fila_candidatos SET selecionado = ? WHERE cnpj = ?",
            [(hoje.isoformat(), c[4]) for c in lote])
        con.commit()

    fila_restante = len(candidatos) - len(lote)
    print(f"Fila de espera após este lote: {fila_restante} candidatos pendentes "
          f"(entram no próximo lote automaticamente, sem precisar reaparecer na "
          f"janela de {args.meses} meses).")

    # ---- exporta a fila leve (só pendentes) de volta para o arquivo que o
    # workflow vai commitar -- isso é o que faz a fila sobreviver até a
    # próxima execução, em vez de reiniciar do zero todo dia.
    pendentes_export = con.execute(
        """SELECT cnpj, cnpj_basico, nome_fantasia, cnae, municipio_cod, bairro,
                  ddd, telefone, email, raio, data_inicio, primeiro_visto
           FROM fila_candidatos WHERE selecionado IS NULL""").fetchall()
    with open(args.fila_leve, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cnpj", "cnpj_basico", "nome_fantasia", "cnae", "municipio_cod",
                    "bairro", "ddd", "telefone", "email", "raio", "data_inicio", "primeiro_visto"])
        w.writerows(pendentes_export)
    print(f"Fila leve exportada para '{args.fila_leve}': {len(pendentes_export)} candidatos pendentes salvos para a próxima execução.")

    razoes = {}
    if tem_empresas:
        razoes = dict(con.execute(
            "SELECT cnpj_basico, razao_social FROM empresas_ms"))

    with open(args.saida, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["RAIO", "MUNICIPIO", "CNPJ", "RAZAO_SOCIAL", "NOME_FANTASIA",
                    "CNAE", "DATA_ABERTURA", "BAIRRO", "DDD", "TELEFONE", "EMAIL"])
        for c in lote:
            r, _neg, _visto, nome_mun, cnpj, basico, fantasia, cnae, ini, bairro, ddd, tel, email = c
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
