#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOTOR VERTTI — JUCEMS de verdade (não mais só o substituto calculado)

O QUE ESTE SCRIPT RESOLVE
--------------------------
Até aqui, o "sinal JUCEMS" do motor era só um substituto: a própria
contagem de aberturas dentro da base da Receita, servindo de equivalente.
Funciona, mas não é o dado oficial. Este script busca o dado real,
publicado mensalmente pela JUCEMS no Portal de Dados Abertos de MS —
dataset "Empresas de Mato Grosso do Sul" (dados.ms.gov.br/dataset/jucems),
recurso "Empresas Constituídas".

POR QUE VIA API DO CKAN, E NÃO UM LINK FIXO
--------------------------------------------
O nome do arquivo muda todo mês (ex.: .../2026/07/Empresas_Constituidas.csv
vira .../2026/08/... no mês seguinte). Um link fixo quebraria sozinho.
O portal roda em CKAN (confirmado: meta-generator: ckan 2.10.4), que expõe
uma API REST estável e documentada — não é atalho, é a forma oficial de
consumir dados de qualquer portal CKAN (mesma tecnologia usada por
dados.gov.br, data.gov, etc.). A API devolve sempre o link do arquivo
mais recente, não importa como o nome mudou.

MITIGAÇÃO DE ERRO — POR QUE ISSO NÃO PODE QUEBRAR O MOTOR
-----------------------------------------------------------
Portal de governo estadual, mantido por equipe pequena: pode sair do ar,
mudar de formato, atrasar a atualização mensal, ou trocar o nome de uma
coluna sem aviso. Nada disso pode travar o ciclo mensal do motor. Por
isso:
  1. Toda etapa de rede tem try/except — falha aqui nunca derruba o
     restante do pipeline.
  2. O parser de colunas é por NOME (município, quantidade), não por
     posição fixa — tolera reordenação de colunas.
  3. Se qualquer etapa falhar, o script simplesmente não escreve
     jucems_atual.csv, e o motor cai de volta, sozinho, para o sinal
     calculado da própria base (--jucems vira opcional em 2_gerar_lote.py,
     já era assim desde o início).

USO
---
    python jucems_real.py                    # gera jucems_atual.csv
    python jucems_real.py --debug             # imprime as colunas encontradas

Saída: jucems_atual.csv (MUNICIPIO;ABERTURAS), pronto para
       2_gerar_lote.py --jucems jucems_atual.csv
"""
import argparse
import csv
import io
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime

CKAN_API = "https://www.dados.ms.gov.br/api/3/action/package_show?id=jucems"
UA = ("VERTTI-Consultoria-MotorCaptacao/1.0 "
      "(uso de dados publicos JUCEMS para prospeccao B2B)")

# nomes de recurso aceitos (o portal já usou variações de maiúscula/acento)
NOMES_ACEITOS = ("empresas constituidas", "empresas constituídas")

MUNICIPIOS_MS = (
    "CAMPO GRANDE", "DOURADOS", "TRES LAGOAS", "CORUMBA", "PONTA PORA",
    "NAVIRAI", "NOVA ANDRADINA", "AQUIDAUANA", "PARANAIBA", "COXIM",
    "MARACAJU", "CHAPADAO DO SUL", "SAO GABRIEL DO OESTE", "AMAMBAI",
    "TERENOS", "SIDROLANDIA", "JARAGUARI", "ROCHEDO", "CORGUINHO",
    "DOIS IRMAOS DO BURITI", "NOVA ALVORADA DO SUL", "RIBAS DO RIO PARDO",
    "BANDEIRANTES", "BATAGUASSU", "BELA VISTA", "BODOQUENA", "BONITO",
    "CAARAPO", "CAMAPUA", "CASSILANDIA", "GUIA LOPES DA LAGUNA", "IVINHEMA",
    "JARDIM", "MIRANDA", "MUNDO NOVO", "NIOAQUE", "RIO BRILHANTE",
    "SANTA RITA DO PARDO", "SETE QUEDAS", "VICENTINA", "ANASTACIO",
)


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().upper()


def http_get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout)


def achar_recurso_atual():
    """Consulta a API do CKAN e devolve a URL atual do CSV de Empresas Constituídas."""
    with http_get(CKAN_API) as r:
        pacote = json.load(r)
    if not pacote.get("success"):
        raise RuntimeError("API do CKAN respondeu success=false")
    for rec in pacote["result"]["resources"]:
        nome = norm(rec.get("name", ""))
        if any(norm(alvo) in nome for alvo in NOMES_ACEITOS):
            return rec["url"]
    raise RuntimeError("Recurso 'Empresas Constituídas' não encontrado na "
                       "listagem atual do dataset JUCEMS")


def baixar_csv(url):
    with http_get(url) as r:
        bruto = r.read()
    # tenta utf-8 primeiro, cai para latin-1 (padrão em CSV de governo BR)
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return bruto.decode(enc)
        except UnicodeDecodeError:
            continue
    return bruto.decode("latin-1", errors="replace")


def detectar_delimitador(texto):
    primeira_linha = texto.split("\n", 1)[0]
    return ";" if primeira_linha.count(";") >= primeira_linha.count(",") else ","


def parsear_flexivel(texto, debug=False):
    """Encontra a coluna de município e a coluna de quantidade por NOME,
    não por posição — tolera o portal reordenar ou renomear colunas."""
    delim = detectar_delimitador(texto)
    leitor = csv.reader(io.StringIO(texto), delimiter=delim)
    linhas = list(leitor)
    if not linhas:
        raise RuntimeError("CSV vazio")

    cab = [norm(c) for c in linhas[0]]
    if debug:
        print("Colunas encontradas:", linhas[0])

    def achar_col(padroes):
        for i, c in enumerate(cab):
            if any(p in c for p in padroes):
                return i
        return None

    col_mun = achar_col(["MUNICIPIO", "MUNICÍPIO", "CIDADE"])
    col_qtd = achar_col(["QUANTIDADE", "TOTAL", "QTDE", "QTD", "NUMERO", "NÚMERO", "CONSTITUID"])

    if col_mun is None:
        raise RuntimeError(f"Não achei coluna de município entre: {linhas[0]}")
    if col_qtd is None:
        raise RuntimeError(f"Não achei coluna de quantidade entre: {linhas[0]}")

    contagem = {}
    for row in linhas[1:]:
        if len(row) <= max(col_mun, col_qtd):
            continue
        mun_bruto = norm(row[col_mun])
        # o nome do município pode vir com sufixo "-MS" ou similar
        mun = next((m for m in MUNICIPIOS_MS if m in mun_bruto or mun_bruto in m), mun_bruto)
        qtd_txt = re.sub(r"[^\d]", "", row[col_qtd] or "0")
        if not qtd_txt:
            continue
        qtd = int(qtd_txt)
        contagem[mun] = contagem.get(mun, 0) + qtd

    if not contagem:
        raise RuntimeError("Nenhuma linha de dados válida após o parse")
    return contagem


MESES_PT = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]


def parsear_estadual_mensal(texto):
    """Fallback para quando a JUCEMS só publica o total mensal do ESTADO
    inteiro, sem quebra por município (formato Período/Jan.../Dez/Total —
    visto pela primeira vez em jul/2026). Devolve o mês mais recente com
    valor preenchido e o acumulado do ano, na linha do ano corrente."""
    delim = detectar_delimitador(texto)
    linhas = list(csv.reader(io.StringIO(texto), delimiter=delim))
    if not linhas:
        raise RuntimeError("CSV vazio")
    cab = [norm(c) for c in linhas[0]]

    col_periodo = next((i for i, c in enumerate(cab) if "PERIODO" in c), None)
    col_total = next((i for i, c in enumerate(cab) if c == "TOTAL"), None)
    cols_mes = {m: i for i, c in enumerate(cab) for m in MESES_PT if c == m}

    if col_periodo is None or not cols_mes:
        raise RuntimeError(f"Formato estadual mensal não reconhecido entre: {linhas[0]}")

    ano_atual = str(datetime.now().year)
    linha_ano = next((row for row in linhas[1:]
                       if len(row) > col_periodo and ano_atual in row[col_periodo]),
                      linhas[-1] if len(linhas) > 1 else None)
    if linha_ano is None:
        raise RuntimeError("Nenhuma linha de dados após o cabeçalho")

    mes_rotulo, valor_mes = None, None
    for m in reversed(MESES_PT):
        idx = cols_mes.get(m)
        if idx is not None and idx < len(linha_ano):
            txt = re.sub(r"[^\d]", "", linha_ano[idx] or "")
            if txt:
                mes_rotulo, valor_mes = m, int(txt)
                break

    valor_ano = None
    if col_total is not None and col_total < len(linha_ano):
        txt = re.sub(r"[^\d]", "", linha_ano[col_total] or "")
        if txt:
            valor_ano = int(txt)

    if mes_rotulo is None and valor_ano is None:
        raise RuntimeError("Nenhum valor mensal/anual encontrado na linha do ano corrente")

    periodo_txt = linha_ano[col_periodo] if col_periodo < len(linha_ano) else ano_atual
    return {"periodo": periodo_txt, "mes": mes_rotulo, "valor_mes": valor_mes, "valor_ano": valor_ano}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="jucems_atual.csv")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    contagem = None
    estadual = None

    try:
        url = achar_recurso_atual()
        print(f"Recurso atual da JUCEMS: {url}")
        texto = baixar_csv(url)
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"AVISO: falha de rede ao buscar a JUCEMS ({exc}). "
              f"O motor usará o sinal calculado da própria base neste ciclo.")
        sys.exit(2)
    except Exception as exc:
        print(f"AVISO: JUCEMS indisponível ({exc}). "
              f"O motor usará o sinal calculado da própria base neste ciclo.")
        sys.exit(2)

    try:
        contagem = parsear_flexivel(texto, debug=args.debug)
    except Exception as exc_mun:
        print(f"Sem quebra por município neste ciclo ({exc_mun}) — tentando o total estadual...")
        try:
            estadual = parsear_estadual_mensal(texto)
        except Exception as exc_uf:
            print(f"AVISO: JUCEMS indisponível ou mudou de formato por completo ({exc_uf}). "
                  f"O motor usará o sinal calculado da própria base neste ciclo.")
            sys.exit(2)

    if contagem:
        with open(args.saida, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            for mun, qtd in sorted(contagem.items(), key=lambda x: -x[1]):
                w.writerow([mun, qtd])
        print(f"\nJUCEMS real (POR MUNICÍPIO): {len(contagem)} municípios, "
              f"{sum(contagem.values()):,} constituições no total.")
        print(f"Salvo em {args.saida} — use com:")
        print(f"  python 2_gerar_lote.py --jucems {args.saida} ...")
    else:
        # Sem quebra por cidade neste ciclo — grava o número estadual mesmo
        # assim (marcador que nenhum município real jamais vai bater, então
        # 2_gerar_lote.py o ignora com segurança na pontuação por cidade),
        # para o dado real não se perder e ficar visível no status.
        valor_exibir = estadual["valor_mes"] if estadual["valor_mes"] is not None else estadual["valor_ano"]
        with open(args.saida, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["MS_ESTADUAL_SEM_QUEBRA_POR_MUNICIPIO", valor_exibir])
        print(f"\nJUCEMS real (SOMENTE ESTADUAL — a JUCEMS parou de publicar por "
              f"cidade neste recurso): período {estadual['periodo']}, "
              f"mês {estadual['mes'] or '?'}: {estadual['valor_mes']} constituições; "
              f"acumulado no ano: {estadual['valor_ano']}.")
        print(f"Salvo em {args.saida} com o total estadual — não é usado na pontuação "
              f"por cidade (nenhum município bate com esse marcador), mas fica "
              f"registrado no status para acompanhamento.")


if __name__ == "__main__":
    main()
