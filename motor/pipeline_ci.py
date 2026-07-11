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
FUNIL = os.path.join(REPO_RAIZ, "funil_historico.json")      # série histórica agregada, sem PII
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
        "proximas": {"semanal": "toda quarta-feira, 13:00 UTC (~10:00 Campo Grande/MS)",
                      "mensal": "todo dia 20, 12:00 UTC (~09:00 Campo Grande/MS)"},
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
    if r.stderr:
        print("STDERR:", r.stderr[-1000:])
    if r.returncode != 0 or "com falha" in r.stdout and ", 0 com falha" not in r.stdout:
        linhas_err = [l for l in r.stderr.strip().splitlines() if l.strip()]
        linhas_out = [l for l in r.stdout.strip().splitlines() if l.strip()]
        # sys.exit(mensagem) e tracebacks vão para o stderr — prioriza ali quando há falha real
        detalhe_real = (linhas_err[-1] if linhas_err
                        else (linhas_out[-1] if linhas_out else "sem saída do script"))
        etapa(st, "download", "erro", detalhe_real, "ver diagnostico_ultima_execucao.txt")
        alerta(st, "erro",
               f"Download automático falhou: {detalhe_real}. "
               "Isso roda 100% na nuvem do GitHub — não depende de nenhuma "
               "máquina sua. Se for uma instabilidade temporária do portal da "
               "Receita, o motor_retry_diario.yml tenta de novo sozinho, uma "
               "vez por dia, até o dia 28 ou até dar certo. Nenhuma ação sua "
               "é necessária a não ser que o alerta persista por vários dias.")
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


def et_jucems_real(st, cfg):
    """Tenta buscar o dado oficial da JUCEMS via API do CKAN. Se falhar por
    qualquer motivo (rede, formato do portal mudou, recurso renomeado), cai
    de volta sozinho para o sinal calculado da própria base — nunca derruba
    o ciclo mensal."""
    caminho_jucems = os.path.join(RAIZ, "jucems_atual.csv")
    r = rodar([sys.executable, "jucems_real.py", "--saida", caminho_jucems])
    print(r.stdout[-800:])
    if r.returncode == 0 and os.path.exists(os.path.join(RAIZ, "jucems_atual.csv")):
        if "SOMENTE ESTADUAL" in r.stdout:
            linha = next((l for l in r.stdout.splitlines() if l.startswith("JUCEMS real (SOMENTE ESTADUAL")), "")
            etapa(st, "jucems", "ok",
                  f"dado oficial da JUCEMS obtido, mas só em nível estadual (a JUCEMS parou "
                  f"de publicar por município neste recurso): {linha[len('JUCEMS real (SOMENTE ESTADUAL — a JUCEMS parou de publicar por cidade neste recurso): '):].strip() or linha}",
                  "não usado na pontuação por cidade (sem granularidade), mas registrado para acompanhamento")
        else:
            etapa(st, "jucems", "ok",
                  "dado oficial da JUCEMS obtido via API do CKAN (dados.ms.gov.br), por município",
                  "coluna localizada por nome, não por posição — tolera mudança de layout")
        return caminho_jucems
    else:
        # jucems_real.py imprime "AVISO: <motivo real>" em vez de lançar
        # exceção crua — capturamos essa linha para o status ficar
        # autoexplicado, em vez de repetir sempre a mesma frase genérica.
        linhas_aviso = [l for l in r.stdout.strip().splitlines() if l.startswith("AVISO:")]
        motivo = linhas_aviso[-1][len("AVISO: "):] if linhas_aviso else "motivo não capturado (ver stdout do passo no log do Actions)"
        etapa(st, "jucems", "aviso",
              f"JUCEMS oficial indisponível neste ciclo: {motivo}",
              "mitigação automática (sinal calculado da própria base) — não impede o ciclo de continuar")
        return None


def et_lote(st, cfg, caminho_jucems=None):
    raios = str(cfg.get("raios", "1,2"))
    cmd = [sys.executable, "2_gerar_lote.py", "--db", BASE_DB,
           "--meses", str(cfg.get("meses", 3)),
           "--lote", str(cfg.get("lote", 0)),   # 0 = só atualiza a fila; o envio real agora é diário (4_disparo_diario.py)
           "--raios", raios,
           "--saida", os.path.join(RAIZ, "lote_bruto.csv")]
    if caminho_jucems:
        cmd += ["--jucems", caminho_jucems]
    r = rodar(cmd)
    print(r.stdout[-1500:])
    if r.returncode != 0:
        etapa(st, "lote", "erro", "falha ao gerar lote", r.stderr[-300:])
        return False

    # MITIGAÇÃO — raios configurados podem, com o tempo, esgotar o estoque de
    # candidatos qualificados (empresas novas no CNAE certo). Sem isso, o
    # lote mensal simplesmente encolheria mês a mês, silenciosamente, sem
    # ninguém perceber. Dois comportamentos possíveis, ambos vindos da config:
    gerados = re.search(r"Lote gerado \((\d+) contatos", r.stdout)
    n_gerado = int(gerados.group(1)) if gerados else 0
    alvo = int(cfg.get("lote", 100))
    if n_gerado < 0.5 * alvo:
        raios_atuais = [int(x) for x in raios.split(",")]
        proximo = min(max(raios_atuais) + 1, 4)
        if cfg.get("raios_auto_expandir", False) and proximo not in raios_atuais and proximo <= 4:
            novos_raios = raios + f",{proximo}"
            alerta(st, "aviso",
                   f"Lote veio com só {n_gerado}/{alvo} contatos (raios {raios} "
                   f"esgotando). Auto-expansão LIGADA: incluindo Raio {proximo} "
                   f"a partir do próximo ciclo (motor_config.json atualizado).")
            cfg["raios"] = novos_raios
            gravar(CONFIG, cfg)
        else:
            texto_raio4 = " (você já está no Raio 4, cobertura máxima de MS)" if max(raios_atuais) >= 4 else ""
            alerta(st, "aviso",
                   f"Lote veio com só {n_gerado}/{alvo} contatos nos raios {raios} — "
                   f"estoque de empresas novas qualificadas está diminuindo nesta "
                   f"região{texto_raio4}. Ligue 'raios_auto_expandir' na configuração, "
                   f"ou amplie os raios manualmente, se quiser manter o volume.")

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
    fila_txt = re.search(r"Fila de espera após este lote: (\d+)", r.stdout)
    fila_restante = int(fila_txt.group(1)) if fila_txt else None
    etapa(st, "lote", "ok", f"{len(linhas)} contatos válidos (raios {raios})",
          f"dedupe ok; {invalidos} e-mails inválidos descartados; "
          f"fila persistente: {fila_restante if fila_restante is not None else '?'} aguardando o próximo ciclo")
    st["_lote"] = linhas
    st["_fila_restante"] = fila_restante
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

    # Alerta preventivo do teto de automação da Brevo (~2.000 contatos no
    # Gratuito e no Starter — só o Standard remove esse teto). Avisa em
    # dois patamares, sem travar o ciclo, para dar tempo de decidir com
    # calma em vez de descobrir na hora que a automação para de rodar.
    total = len(hist)
    if total >= 2000:
        alerta(st, "erro",
               f"🚨 {total} contatos em automação na Brevo — o teto de ~2.000 do "
               f"Gratuito/Starter provavelmente já foi ultrapassado. A automação pode "
               f"ter parado de disparar para contatos novos. É hora de migrar para o "
               f"plano Standard (a partir de ~US$18/mês) para remover esse teto.")
    elif total >= 1700:
        alerta(st, "aviso",
               f"📊 {total}/2.000 contatos em automação na Brevo (~{round(total/2000*100)}%). "
               f"Perto do teto do plano Gratuito/Starter — planeje a migração para o "
               f"Standard antes de bater o limite, para a automação não parar sozinha.")

    if falhas and not ok:
        etapa(st, "brevo", "erro", f"0 enviados, {falhas} falhas",
              "verifique a chave BREVO_API_KEY")
        return False
    etapa(st, "brevo", "ok", f"{ok} contatos na lista Captação ativo (#{lista_id})"
          + (f"; {falhas} falhas pontuais" if falhas else ""),
          "a automação do Brevo dispara a sequência sozinha a partir daqui")
    return True


def et_funil(st, fila_restante=None):
    """Registra uma linha no histórico agregado do funil, sem nenhum dado
    pessoal (só contagens) -- serve para acompanhar a evolução mês a mês
    sem depender de endpoints da Brevo que exigiriam e-mail/ID de contato
    (o que o motor não guarda, por design, para respeitar a LGPD) ou de
    campos que a própria Brevo já avisou que estão sendo depreciados."""
    historico = carregar(FUNIL, [])
    historico.append({
        "data": agora(),
        "tipo": st.get("tipo_ultima_execucao", ""),
        "ref_dados": st.get("ref", ""),
        "enviados_neste_ciclo": st.get("metricas", {}).get("ultimo_lote", 0),
        "enviados_total_historico": st.get("metricas", {}).get("enviados_total", 0),
        "fila_restante": fila_restante,
    })
    gravar(FUNIL, historico)
    etapa(st, "funil", "ok",
          f"{len(historico)} ciclo(s) no histórico — abertura/clique real fica em "
          "Brevo: Automations > Workflows > Activity (não duplicado aqui para não "
          "arriscar guardar dado pessoal nem depender de campo em depreciação)")


# ======================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["semanal", "mensal"])
    ap.add_argument("--sem-download", action="store_true")
    args = ap.parse_args()
    cfg = carregar(CONFIG, {})
    st = status_novo(args.modo)

    if args.modo == "semanal":
        et_rpi(st, cfg)
        gravar(STATUS, st)
        return

    # mensal — cada etapa só roda se a anterior passou (mitigação em cascata)
    if not args.sem_download:
        if not et_download(st, cfg):
            gravar(STATUS, st); sys.exit(1)
    else:
        etapa(st, "download", "pulado", "usando ./dados_receita local")
        st.setdefault("ref", datetime.now().strftime("%Y-%m"))
    if not et_integridade_zips(st):
        gravar(STATUS, st); sys.exit(1)
    if not et_destilaria(st, cfg):
        gravar(STATUS, st); sys.exit(1)
    et_rpi(st, cfg)
    caminho_jucems = et_jucems_real(st, cfg)
    if not et_lote(st, cfg, caminho_jucems):
        gravar(STATUS, st); sys.exit(1)
    etapa(st, "brevo", "ok",
          "envio direto desligado neste ciclo mensal — a fila foi atualizada "
          "(novos candidatos entraram, antigos expiraram) e o envio de verdade "
          "acontece todo dia, com aquecimento gradual, pelo motor_retry/"
          "4_disparo_diario.py",
          "ver etapa 'disparo_diario' no status de cada dia para o volume real enviado")
    et_funil(st, fila_restante=st.get("_fila_restante"))
    st.pop("_lote", None)
    st.pop("_fila_restante", None)
    gravar(STATUS, st)
    print("\n=== Pipeline mensal concluído — status gravado ===")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        import traceback
        erro_txt = traceback.format_exc()
        print("ERRO NÃO TRATADO:\n" + erro_txt, file=sys.stderr)
        try:
            st_emergencia = carregar(STATUS, status_novo("mensal"))
            st_emergencia.setdefault("alertas", []).append({
                "nivel": "erro", "quando": agora(),
                "msg": f"Falha não tratada no pipeline: {exc}\n{erro_txt[-1500:]}"})
            gravar(STATUS, st_emergencia)
        except Exception:
            pass  # mesmo o registro de emergência não pode travar a saída de erro
        sys.exit(1)
