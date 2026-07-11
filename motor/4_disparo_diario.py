#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DISPARO DIÁRIO — aquecimento de domínio, multi-remetente
Em vez de um lote único mensal, calcula quanto cada remetente ATIVO pode
enviar hoje (curva de aquecimento própria, contada a partir do dia em que
ele entrou em operação), gera esse pedaço puxando da fila persistente
(reaproveita 2_gerar_lote.py, só muda o tamanho do lote) e manda pro
Brevo, cada remetente na sua própria lista.

Por que isso existe: mandar milhares de e-mails de um domínio com pouco
ou nenhum histórico de envio é o padrão mais vigiado por Gmail/Outlook
para sinalizar comportamento de spam. Aquecimento gradual (crescer devagar
a partir de poucos e-mails por dia) é a prática padrão do mercado para
evitar isso -- ver comentário em motor/README_MOTOR.md.
"""
import csv
import json
import math
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone

RAIZ = os.path.dirname(os.path.abspath(__file__))
REPO_RAIZ = os.path.dirname(RAIZ)
CONFIG = os.path.join(REPO_RAIZ, "motor_config.json")
STATUS = os.path.join(REPO_RAIZ, "motor_status.json")
ENVIADOS = os.path.join(REPO_RAIZ, "motor_enviados.json")
BREVO_API = "https://api.brevo.com/v3/contacts"


def agora():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def carregar(path, padrao):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return padrao


def gravar(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def volume_do_dia(ativo_desde_str, cfg_aquecimento):
    """Curva de aquecimento: começa em 'inicio_diario', cresce
    'crescimento_diario_pct' % por dia, até o teto do remetente."""
    inicio = cfg_aquecimento.get("inicio_diario", 8)
    cresc = cfg_aquecimento.get("crescimento_diario_pct", 20) / 100.0
    teto = cfg_aquecimento.get("teto_diario_por_remetente", 100)
    ativo_desde = datetime.strptime(ativo_desde_str, "%Y-%m-%d").date()
    dias_ativo = max(0, (date.today() - ativo_desde).days)
    volume = inicio * ((1 + cresc) ** dias_ativo)
    return min(teto, math.floor(volume))


def enviar_para_brevo(chave, lista_id, linhas_csv):
    ok = falhas = 0
    hist = set(carregar(ENVIADOS, []))
    novos_hashes = []
    for row in linhas_csv:
        email = row["EMAIL"].strip().lower()
        import hashlib
        h = hashlib.sha256(email.encode()).hexdigest()
        if h in hist:
            continue  # já contatado antes (por qualquer remetente) — nunca duplica
        corpo = json.dumps({
            "email": email,
            "attributes": {"NOME_EMPRESA": row.get("NOME_FANTASIA", ""),
                            "MUNICIPIO": row.get("MUNICIPIO", "")},
            "listIds": [lista_id], "updateEnabled": True,
        }).encode()
        req = urllib.request.Request(BREVO_API, data=corpo, method="POST",
                                     headers={"api-key": chave, "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=30).read()
            ok += 1
            hist.add(h)
            novos_hashes.append(h)
        except urllib.error.HTTPError as e:
            if e.code == 400 and b"duplicate" in (e.read() or b"").lower():
                ok += 1; hist.add(h); novos_hashes.append(h)
            else:
                falhas += 1
        except Exception:
            falhas += 1
    gravar(ENVIADOS, sorted(hist))
    return ok, falhas


def main():
    cfg = carregar(CONFIG, {})
    st = carregar(STATUS, {"etapas": {}, "alertas": []})
    st.setdefault("etapas", {})
    st.setdefault("alertas", [])
    chave = os.environ.get("BREVO_API_KEY", "").strip()

    remetentes = [r for r in cfg.get("remetentes", []) if r.get("ativo", True)]
    aquecimento = cfg.get("aquecimento", {})
    if not remetentes:
        print("Nenhum remetente ativo em motor_config.json — nada a fazer hoje.")
        sys.exit(0)
    if not chave:
        print("AVISO: BREVO_API_KEY não configurada — não é possível disparar hoje.")
        sys.exit(0)

    resultado_dia = []
    for rem in remetentes:
        n_hoje = volume_do_dia(rem["ativo_desde"], aquecimento)
        if n_hoje <= 0:
            continue
        saida_csv = os.path.join(RAIZ, f"lote_diario_{rem['nome']}.csv")
        cmd = [sys.executable, os.path.join(RAIZ, "2_gerar_lote.py"),
               "--lote", str(n_hoje), "--raios", cfg.get("raios", "1,2"),
               "--meses", str(cfg.get("meses", 3)), "--saida", saida_csv]
        r = subprocess.run(cmd, cwd=REPO_RAIZ, capture_output=True, text=True)
        print(f"--- remetente '{rem['nome']}' (dia {n_hoje} do aquecimento, alvo {n_hoje} contatos) ---")
        print(r.stdout[-1500:])
        if r.returncode != 0:
            print(f"AVISO: geração do lote falhou para '{rem['nome']}': {r.stderr[-500:]}")
            continue
        if not os.path.exists(saida_csv):
            continue
        with open(saida_csv, encoding="utf-8") as f:
            linhas = list(csv.DictReader(f))
        if not linhas:
            print(f"Remetente '{rem['nome']}': fila vazia para os raios ativos, nada para enviar hoje.")
            continue
        ok, falhas = enviar_para_brevo(chave, rem["brevo_lista_id"], linhas)
        resultado_dia.append({"remetente": rem["nome"], "alvo": n_hoje,
                               "enviados": ok, "falhas": falhas})
        print(f"Remetente '{rem['nome']}': {ok} enviados, {falhas} falhas.")

    total_enviado = sum(r["enviados"] for r in resultado_dia)
    total_falhas = sum(r["falhas"] for r in resultado_dia)
    st["etapas"]["disparo_diario"] = {
        "status": "ok" if total_enviado or not remetentes else "aviso",
        "quando": agora(),
        "detalhe": f"{total_enviado} contatos enviados hoje, distribuídos entre "
                   f"{len(resultado_dia)} remetente(s) ativo(s): " +
                   ", ".join(f"{r['remetente']}={r['enviados']}" for r in resultado_dia),
        "integridade": f"{total_falhas} falhas pontuais" if total_falhas else "sem falhas"}
    st["metricas"] = st.get("metricas", {})
    st["metricas"]["enviados_total"] = len(carregar(ENVIADOS, []))
    st["metricas"]["ultimo_disparo_diario"] = total_enviado
    gravar(STATUS, st)
    print(f"\n=== Disparo diário concluído: {total_enviado} enviados no total ===")


if __name__ == "__main__":
    main()
    sys.exit(0)
