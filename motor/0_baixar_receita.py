#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOTOR VERTTI — Passo 0: BAIXAR sozinho a base da Receita Federal

O que este script faz:
  1. Descobre qual é o mês mais recente disponível no portal de dados abertos.
  2. Lista os arquivos daquele mês (Estabelecimentos*.zip, Empresas*.zip, Municipios.zip).
  3. Baixa cada um, com retomada automática (se cair a conexão, continua de onde
     parou — não perde o que já baixou) e nova tentativa em caso de falha.
  4. Confere o tamanho de cada arquivo baixado contra o tamanho informado pelo
     servidor, para garantir que não ficou nada corrompido/incompleto.

IMPORTANTE — sobre bloqueio automático:
  O servidor da Receita pode, em alguns momentos, limitar downloads feitos por
  script (é comum em portais de dados abertos, para não sobrecarregar o
  servidor). Este script já:
    - usa um identificador (User-Agent) educado e transparente;
    - espera alguns segundos entre arquivos;
    - tenta de novo, com espera crescente, se uma conexão falhar.
  Se mesmo assim o servidor recusar (erro 403 ou 429 repetido), o script avisa
  claramente e mostra o link exato para baixar aquele arquivo manualmente pelo
  navegador — nunca fica travado sem explicação.

USO
---
    python 0_baixar_receita.py --pasta ./dados_receita
    python 0_baixar_receita.py --pasta ./dados_receita --mes 2026-06   (forçar um mês específico)
    python 0_baixar_receita.py --pasta ./dados_receita --sem-empresas  (pula Empresas*.zip, mais rápido)
"""
import argparse
import os
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def http_get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout)


def listar_meses_disponiveis():
    """Lê o índice raiz e devolve as pastas AAAA-MM em ordem decrescente (mais novo primeiro)."""
    try:
        with http_get(BASE) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        sys.exit(f"O portal da Receita recusou o acesso: HTTP {exc.code} ({exc.reason}). "
                  f"URL: {BASE}")
    except urllib.error.URLError as exc:
        sys.exit(f"Não consegui conectar ao portal da Receita: {exc.reason}. URL: {BASE}")
    meses = sorted(set(re.findall(r'href="(\d{4}-\d{2})/"', html)), reverse=True)
    if not meses:
        sys.exit("Não consegui ler a lista de meses no portal. O site pode ter mudado "
                 "de layout ou estar bloqueando o acesso agora. Confira manualmente em:\n"
                 + BASE)
    return meses


def listar_arquivos_do_mes(mes):
    url = f"{BASE}{mes}/"
    try:
        with http_get(url) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        sys.exit(f"O portal da Receita recusou o acesso à pasta do mês: HTTP {exc.code} "
                  f"({exc.reason}). URL: {url}")
    except urllib.error.URLError as exc:
        sys.exit(f"Não consegui conectar à pasta do mês: {exc.reason}. URL: {url}")
    arquivos = sorted(set(re.findall(r'href="([^"]+\.zip)"', html)))
    return url, arquivos


def escolher_relevantes(arquivos, com_empresas):
    alvo = []
    for f in arquivos:
        low = f.lower()
        if low.startswith("estabelecimentos") or low.startswith("municipios"):
            alvo.append(f)
        elif com_empresas and low.startswith("empresas"):
            alvo.append(f)
    return alvo


def tamanho_remoto(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers.get("Content-Length", 0))


def baixar_com_retomada(url, destino, tentativas=5):
    tam_remoto = None
    try:
        tam_remoto = tamanho_remoto(url)
    except Exception:
        pass  # alguns servidores não respondem HEAD; segue sem essa checagem prévia

    if os.path.exists(destino) and tam_remoto and os.path.getsize(destino) == tam_remoto:
        print(f"  já baixado por completo, pulando: {os.path.basename(destino)}")
        return True

    for tentativa in range(1, tentativas + 1):
        pos = os.path.getsize(destino) if os.path.exists(destino) else 0
        headers = {"User-Agent": UA}
        if pos:
            headers["Range"] = f"bytes={pos}-"
        req = urllib.request.Request(url, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            # CRÍTICO: só é seguro completar o arquivo (modo append) se o servidor
            # confirmou com HTTP 206 que está mandando só o restante. Se pedimos
            # Range e ele respondeu 200, ele está mandando o arquivo INTEIRO de novo
            # — nesse caso é obrigatório reiniciar do zero, ou o arquivo corrompe.
            retomando_de_verdade = pos > 0 and resp.status == 206
            if pos > 0 and resp.status != 206:
                print(f"\n  aviso: servidor não suporta retomada para este arquivo "
                      f"(respondeu {resp.status} a um pedido de continuação) — "
                      f"reiniciando o download deste arquivo do zero.")
                pos = 0
            modo = "ab" if retomando_de_verdade else "wb"
            with resp, open(destino, modo) as out:
                total = tam_remoto or (int(resp.headers.get("Content-Length", 0)) + pos)
                lidos = pos
                t0 = time.time()
                while True:
                    chunk = resp.read(1 << 20)  # 1 MB por vez
                    if not chunk:
                        break
                    out.write(chunk)
                    lidos += len(chunk)
                    if total:
                        pct = 100 * lidos / total
                        vel = (lidos - pos) / max(0.1, time.time() - t0) / 1e6
                        print(f"\r  {os.path.basename(destino)}: {pct:5.1f}%  "
                              f"({lidos/1e6:7.1f} MB)  {vel:5.1f} MB/s", end="")
            print()
            if tam_remoto and os.path.getsize(destino) != tam_remoto:
                raise IOError(
                    f"tamanho final ({os.path.getsize(destino)}) não bate com o "
                    f"esperado ({tam_remoto})")
            return True
        except (urllib.error.HTTPError, urllib.error.URLError, IOError, TimeoutError) as exc:
            espera = min(60, 5 * tentativa)
            print(f"\n  falha ({exc}) — tentativa {tentativa}/{tentativas}, "
                  f"nova tentativa em {espera}s...")
            time.sleep(espera)
    print(f"  [NÃO BAIXOU] {os.path.basename(destino)} — baixe manualmente pelo navegador:\n  {url}")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", required=True)
    ap.add_argument("--mes", default=None, help="AAAA-MM; padrão: o mais recente disponível")
    ap.add_argument("--sem-empresas", action="store_true",
                    help="pula Empresas*.zip (mais rápido, perde a razão social)")
    ap.add_argument("--pausa", type=float, default=3.0,
                    help="segundos de pausa entre arquivos (padrão: 3s, educado com o servidor)")
    args = ap.parse_args()
    os.makedirs(args.pasta, exist_ok=True)

    print("Consultando meses disponíveis no portal da Receita Federal...")
    meses = listar_meses_disponiveis()
    mes = args.mes or meses[0]
    if mes not in meses:
        sys.exit(f"Mês {mes} não encontrado. Disponíveis: {', '.join(meses[:6])} ...")
    print(f"Mês escolhido: {mes}  (mais recente disponível: {meses[0]})")

    url_mes, arquivos = listar_arquivos_do_mes(mes)
    alvo = escolher_relevantes(arquivos, com_empresas=not args.sem_empresas)
    if not alvo:
        sys.exit("Não encontrei Estabelecimentos*/Empresas*/Municipios* nessa pasta. "
                 "Confira manualmente em: " + url_mes)

    print(f"\n{len(alvo)} arquivo(s) a baixar para {args.pasta}:")
    for f in alvo:
        print(" ", f)
    print()

    ok = falhou = 0
    for i, nome in enumerate(alvo, 1):
        print(f"[{i}/{len(alvo)}] {nome}")
        destino = os.path.join(args.pasta, nome)
        if baixar_com_retomada(url_mes + nome, destino):
            ok += 1
        else:
            falhou += 1
        if i < len(alvo):
            time.sleep(args.pausa)

    print(f"\n=== Concluído: {ok} baixados, {falhou} com falha ===")
    if falhou:
        print("Baixe manualmente os que falharam (links impressos acima) e coloque "
              f"na pasta {args.pasta} — o destilador (1_destilar_ms.py) funciona "
              "igual, não importa como o arquivo chegou lá.")
    else:
        print("Tudo certo. Próximo passo:")
        print(f"  python 1_destilar_ms.py --pasta {args.pasta} --ref {mes}"
              + ("" if args.sem_empresas else " --com-empresas"))


if __name__ == "__main__":
    main()
