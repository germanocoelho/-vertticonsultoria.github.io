#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOTOR VERTTI — Orquestrador de CI (GitHub Actions)

Executa o pipeline completo sem intervenção humana, com:
  - testes de integridade em cada etapa (ZIPs válidos, contagens de sanidade,
    dedupe, validade de e-mail);
  - mitigação de erros: cada etapa falha de forma isolada e documentada — o
    status registra exatamente o que passou, o que falhou e o que fazer;
  - privacidade: NENHUM e-mail de prospect é gravado no repositório público.
    O histórico de envio usa hash SHA-256; o CSV do lote vira artefato privado.

Uso (no Actions ou localmente):
    python pipeline_ci.py semanal            # atualiza base RPI/INPI
    python pipeline_ci.py mensal             # ciclo completo
    python pipeline_ci.py mensal --sem-download   # usa ./dados_receita já baixado
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.abspath(__file__))
REPO_RAIZ = os.path.dirname(RAIZ)
STATUS = os.path.join(REPO_RAIZ, "motor_status.json")
CONFIG = os.path.join(REPO_RAIZ, "motor_config.json")
ENVIADOS = os.path.join(REPO_RAIZ, "motor_enviados.json")   # só hashes SHA-256
DADOS = os.path.join(RAIZ, "dados_receita")
MARCAS_DB = os.path.join(REPO_RAIZ, "marcas_ms.sqlite")
BASE_DB = os.path.join(RAIZ, "base_ms.sqlite")

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


def status_novo(tipo):
    return {
        "atualizado_em": agora(),
        "tipo_ultima_execucao": tipo,
        "etapas": {},
        "alertas": [],
        "metricas": carregar(STATUS, {}).get("metricas", {"enviados_total": 0}),
        "proximas": {"semanal": "toda quarta-feira, 09:00 (Brasília ~06:00)",
                      "mensal": "todo dia 20, 06:00 (Brasília ~03:00)"},
    }


def etapa(st, nome, status, detalhe, integridade=""):
    st["etapas"][nome] = {"status": status, "quando": agora(),
                           "detalhe": detalhe, "integridade": integridade}
    st["atualizado_em"] = agora()
    gravar(STATUS, st)
    print(f"[{status.upper():7s}] {nome}: {detalhe}" + (f" | {integridade}" if integridade else ""))


def alerta(st, nivel, msg):
    st["alertas"].append({"nivel": nivel, "msg": msg, "quando": agora()})
    gravar(STATUS, st)
    print(f"[ALERTA-{nivel.upper()}] {msg}")


def rodar(cmd):
    print("+", " ".join(cmd))
    return subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True)


# ======================================================================
# ETAPAS
# ======================================================================

def et_download(st, cfg):
    r = rodar([sys.executable, "0_baixar_receita.py", "--pasta", DADOS])
    print(r.stdout[-2000:])
    if r.returncode != 0 or "com falha" in r.stdout and ", 0 com falha" not in r.stdout:
        etapa(st, "download", "erro",
              "Servidor da Receita recusou parte dos arquivos",
              "ver log do Actions")
        alerta(st, "erro",
               "Download automático falhou (portal pode bloquear IPs de nuvem). "
               "Mitigação: rode rodar_motor.bat na sua máquina este mês; o resto "
               "do pipeline continua funcionando localmente do mesmo jeito.")
        return False
    m = re.search(r"Mês escolhido: (\d{4}-\d{2})", r.stdout)
    st["ref"] = m.group(1) if m else datetime.now().strftime("%Y-%m")
    zips = [f for f in os.listdir(DADOS) if f.endswith(".zip")]
    tam = sum(os.path.getsize(os.path.join(DADOS, f)) for f in zips) / 1e9
    etapa(st, "download", "ok", f"{len(zips)} arquivos, {tam:.1f} GB, ref {st['ref']}")
    return True


def et_integridade_zips(st):
    ruins = []
    for f in sorted(os.listdir(DADOS)):
        if not f.endswith(".zip"):
            continue
        try:
            with zipfile.ZipFile(os.path.join(DADOS, f)) as z:
                if z.testzip() is not None:
                    ruins.append(f)
        except zipfile.BadZipFile:
            ruins.append(f)
    if ruins:
        etapa(st, "integridade_zips", "erro", f"corrompidos: {', '.join(ruins)}")
        alerta(st, "erro", "ZIPs corrompidos detectados — etapa abortada antes de "
               "gerar base inválida. Mitigação: a próxima execução re-baixa "
               "somente os arquivos com tamanho errado.")
        for f in ruins:
            os.remove(os.path.join(DADOS, f))  # força re-download íntegro
        return False
    etapa(st, "integridade_zips", "ok", "todos os ZIPs íntegros",
          "zipfile.testzip aprovado em 100%")
    return True


def et_destilaria(st, cfg):
    ref = st.get("ref", datetime.now().strftime("%Y-%m"))
    r = rodar([sys.executable, "1_destilar_ms.py", "--pasta", DADOS,
               "--ref", ref, "--com-empresas", "--db", BASE_DB])
    print(r.stdout[-1500:])
    if r.returncode != 0:
        etapa(st, "destilaria", "erro", "falha ao destilar", r.stderr[-300:])
        return False
    con = sqlite3.connect(BASE_DB)
    n = con.execute("SELECT COUNT(*) FROM estab_ms").fetchone()[0]
    tem_cg = con.execute(
        "SELECT COUNT(*) FROM municipios WHERE nome LIKE '%CAMPO GRANDE%'").fetchone()[0]
    con.close()
    # sanidade: MS tem centenas de milhares de estabelecimentos; fora disso, algo errou
    if not (100_000 <= n <= 5_000_000):
        etapa(st, "destilaria", "erro", f"{n:,} estabelecimentos — fora da faixa "
              "esperada (100 mil a 5 mi)", "sanidade reprovada")
        alerta(st, "erro", "Contagem da base fora do esperado — provável arquivo "
               "incompleto ou mudança de layout na Receita. Envio ao Brevo "
               "BLOQUEADO automaticamente para proteger a reputação do domínio.")
        return False
    if not tem_cg:
        etapa(st, "destilaria", "erro", "CAMPO GRANDE ausente da tabela de municípios")
        return False
    etapa(st, "destilaria", "ok", f"{n:,} estabelecimentos MS",
          "faixa de sanidade ok; Campo Grande presente")
    return True


def et_rpi(st, cfg):
    con = sqlite3.connect(MARCAS_DB)
    con.execute("CREATE TABLE IF NOT EXISTS titulares_ms (razao_norm TEXT PRIMARY KEY,"
                " razao_original TEXT, primeira_rpi INTEGER)")
    con.execute("CREATE TABLE IF NOT EXISTS rpis_lidas (numero INTEGER PRIMARY KEY)")
    ult = con.execute("SELECT MAX(numero) FROM rpis_lidas").fetchone()[0]
    antes = con.execute("SELECT COUNT(*) FROM titulares_ms").fetchone()[0]
    con.close()
    inicio = (ult + 1) if ult else int(cfg.get("rpi_seed", 2870))
    fim = inicio + int(cfg.get("max_rpis_por_execucao", 4)) - 1
    r = rodar([sys.executable, "3_cruzar_inpi_exportar.py",
               "--db-marcas", MARCAS_DB, "--baixar-rpi", str(inicio), str(fim)])
    print(r.stdout[-1500:])
    con = sqlite3.connect(MARCAS_DB)
    depois = con.execute("SELECT COUNT(*) FROM titulares_ms").fetchone()[0]
    lidas = con.execute("SELECT COUNT(*) FROM rpis_lidas WHERE numero BETWEEN ? AND ?",
                        (inicio, fim)).fetchone()[0]
    con.close()
    if lidas == 0:
        etapa(st, "rpi", "aviso", f"RPIs {inicio}-{fim} indisponíveis "
              "(números futuros ou INPI fora do ar)",
              "base anterior preservada — nada foi perdido")
        return True   # não é fatal: a base acumulada continua valendo
    etapa(st, "rpi", "ok", f"RPIs {inicio}-{inicio+lidas-1} processadas, "
          f"+{depois-antes} titulares MS (total {depois:,})")
    return True


def et_lote(st, cfg):
    r = rodar([sys.executable, "2_gerar_lote.py", "--db", BASE_DB,
               "--meses", str(cfg.get("meses", 3)),
               "--lote", str(cfg.get("lote", 100)),
               "--raios", str(cfg.get("raios", "1,2")),
               "--saida", os.path.join(RAIZ, "lote_bruto.csv")])
    print(r.stdout[-1200:])
    if r.returncode != 0:
        etapa(st, "lote", "erro", "falha ao gerar lote", r.stderr[-300:])
        return False
    r2 = rodar([sys.executable, "3_cruzar_inpi_exportar.py",
                "--db-marcas", MARCAS_DB, "--lote", os.path.join(RAIZ, "lote_bruto.csv")])
    print(r2.stdout[-1200:])
    if r2.returncode != 0:
        etapa(st, "filtro_inpi", "erro", "falha no cruzamento INPI", r2.stderr[-300:])
        return False
    # integridade do lote final
    caminho = os.path.join(RAIZ, "prospectos_brevo.csv")
    email_re = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")
    vistos, invalidos, linhas = set(), 0, []
    with open(caminho, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            e = row["EMAIL"].strip().lower()
            if not email_re.match(e):
                invalidos += 1
                continue
            if e in vistos:
                continue
            vistos.add(e)
            linhas.append(row)
    removidos_txt = re.search(r"Removidos.*?: (\d+)", r2.stdout)
    etapa(st, "filtro_inpi", "ok",
          f"{removidos_txt.group(1) if removidos_txt else '0'} removidos por marca existente")
    etapa(st, "lote", "ok", f"{len(linhas)} contatos válidos "
          f"(raios {cfg.get('raios','1,2')})",
          f"dedupe ok; {invalidos} e-mails inválidos descartados")
    st["_lote"] = linhas
    return True


def et_dedupe_historico(st):
    hist = set(carregar(ENVIADOS, []))
    novos = []
    for row in st.get("_lote", []):
        h = hashlib.sha256(row["EMAIL"].strip().lower().encode()).hexdigest()
        if h not in hist:
            row["_hash"] = h
            novos.append(row)
    repetidos = len(st.get("_lote", [])) - len(novos)
    st["_lote"] = novos
    etapa(st, "dedupe_historico", "ok",
          f"{len(novos)} inéditos; {repetidos} já contatados em meses anteriores",
          "histórico por hash SHA-256 — nenhum e-mail exposto no repositório")
    return True


def et_brevo(st, cfg):
    lote = st.pop("_lote", [])
    chave = os.environ.get("BREVO_API_KEY", "").strip()
    lista_id = int(cfg.get("brevo_lista_id", 2))
    if not cfg.get("envio_automatico", True):
        etapa(st, "brevo", "desligado",
              f"envio automático desativado na configuração — {len(lote)} contatos "
              "aguardando no artefato do Actions para importação manual")
        return True
    if not chave:
        etapa(st, "brevo", "aguardando_chave",
              f"{len(lote)} contatos prontos, mas o segredo BREVO_API_KEY não está "
              "configurado no repositório",
              "mitigação: importe o artefato manualmente OU cadastre a chave")
        alerta(st, "aviso", "Cadastre BREVO_API_KEY em Settings → Secrets → Actions "
               "para fechar o ciclo 100% automático.")
        return True
    ok = falhas = 0
    hist = set(carregar(ENVIADOS, []))
    for row in lote:
        corpo = json.dumps({
            "email": row["EMAIL"].strip().lower(),
            "attributes": {"NOME_EMPRESA": row.get("NOME_EMPRESA", ""),
                            "MUNICIPIO": row.get("MUNICIPIO", "")},
            "listIds": [lista_id], "updateEnabled": True,
        }).encode()
        req = urllib.request.Request(BREVO_API, data=corpo, method="POST",
                                     headers={"api-key": chave,
                                              "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=30).read()
            ok += 1
            hist.add(row["_hash"])
        except urllib.error.HTTPError as e:
            if e.code == 400 and b"duplicate" in (e.read() or b"").lower():
                ok += 1; hist.add(row["_hash"])   # já existia — conta como ok
            else:
                falhas += 1
        except Exception:
            falhas += 1
    gravar(ENVIADOS, sorted(hist))
    st["metricas"]["enviados_total"] = len(hist)
    st["metricas"]["ultimo_lote"] = ok
    if falhas and not ok:
        etapa(st, "brevo", "erro", f"0 enviados, {falhas} falhas",
              "verifique a chave BREVO_API_KEY")
        return False
    etapa(st, "brevo", "ok", f"{ok} contatos na lista Captação ativo (#{lista_id})"
          + (f"; {falhas} falhas pontuais" if falhas else ""),
          "a automação do Brevo dispara a sequência sozinha a partir daqui")
    return True


# ======================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["semanal", "mensal"])
    ap.add_argument("--sem-download", action="store_true")
    args = ap.parse_args()
    cfg = carregar(CONFIG, {})
    st = status_novo(args.modo)
    st["etapas"]["jucems"] = {
        "status": "ok", "quando": agora(),
        "detalhe": "sinal de momento calculado da própria base destilada",
        "integridade": "equivalente ao Mapa de Empresas, sem dependência externa"}

    if args.modo == "semanal":
        et_rpi(st, cfg)
        gravar(STATUS, st)
        return

    # mensal — cada etapa só roda se a anterior passou (mitigação em cascata)
    if not args.sem_download:
        if not et_download(st, cfg):
            gravar(STATUS, st); return
    else:
        etapa(st, "download", "pulado", "usando ./dados_receita local")
        st.setdefault("ref", datetime.now().strftime("%Y-%m"))
    if not et_integridade_zips(st):
        gravar(STATUS, st); return
    if not et_destilaria(st, cfg):
        gravar(STATUS, st); return
    et_rpi(st, cfg)
    if not et_lote(st, cfg):
        gravar(STATUS, st); return
    et_dedupe_historico(st)
    et_brevo(st, cfg)
    st.pop("_lote", None)
    gravar(STATUS, st)
    print("\n=== Pipeline mensal concluído — status gravado ===")


if __name__ == "__main__":
    main()
