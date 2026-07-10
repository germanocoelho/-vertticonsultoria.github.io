# MOTOR VERTTI — Manual de Operação Mensal

## Automação real, 100% na nuvem — nada instalado em máquina nenhuma

Os workflows rodam em runners do próprio GitHub (`ubuntu-latest`), na nuvem.
Não há nenhum runner self-hosted, nenhum serviço, nenhum instalador — porque
você não tem como instalar nada na máquina da empresa, e não existe uma
segunda máquina disponível. Essa restrição é definitiva e a arquitetura
inteira respeita ela: zero dependência de qualquer computador seu ligado,
zero passo manual recorrente.

O ponto de atenção real é outro: o portal de dados abertos da Receita
Federal é historicamente instável (cai com frequência, é lento, às vezes
falha o download inteiro) — isso afeta qualquer cliente automatizado,
não é algo específico da nuvem. Como o ciclo mensal só tem uma janela por
mês, uma falha nesse dia poderia, em teoria, custar o mês inteiro. Por isso
existe uma rede de segurança automática:

- **`motor_mensal.yml`** dispara todo dia 20 às 12:00 UTC e tenta o ciclo
  completo (download → destilaria → lote → INPI → Brevo).
- **`motor_retry_diario.yml`** roda sozinho todo dia, do dia 20 ao 28,
  verificando se o ciclo deste mês já terminou com sucesso
  (`motor_status.json` → `ref` bate com o mês atual e `etapas.download.status
  == "ok"`). Se não bateu, ele **redispara o `motor_mensal.yml` sozinho**,
  sem qualquer ação sua. Isso se repete diariamente até dar certo ou até o
  dia 28, quando então vira um alerta que exige olhar o
  `diagnostico_ultima_execucao.txt`.
- Os dois workflows compartilham um `concurrency group`, então mesmo que o
  retry dispare enquanto outra execução ainda está rodando, eles nunca
  rodam em paralelo — um espera o outro.

Os agendamentos atuais:
- **Semanal** (RPI/INPI): toda quarta-feira, 13:00 UTC (~10:00 Campo Grande/MS)
- **Mensal** (ciclo completo): todo dia 20, 12:00 UTC (~09:00 Campo Grande/MS)
- **Retry diário** (só do ciclo mensal): todo dia 20–28, 23:00 UTC

Todos também têm o botão **"Rodar agora"** (`workflow_dispatch`) no ADM,
para disparar manualmente quando quiser, sem esperar o cron.

## A arquitetura em uma frase
Um script baixa a base sozinho (com retomada se cair a conexão); uma passada
pesada **única** destila os 60 GB numa base local só-MS (SQLite); depois
disso, tudo — raios geográficos, prioridade JUCEMS, filtro INPI, exportação
Brevo — roda **em segundos, offline e de graça**.

```
0_baixar_receita.py ──1x/mês──►  ./dados_receita/*.zip (baixado sozinho)
                                          │
Receita (ZIPs)  ──────────────►  1_destilar_ms.py  ──►  base_ms.sqlite (local, pequena)
                                                          │
RPI do INPI (XML) ──semanal──► 3 --baixar-rpi ──► marcas_ms.sqlite (acumulativa)
                                                          │
                              2_gerar_lote.py  ◄──────────┘
                              (raios 1→4 + sinal JUCEMS)
                                     │
                              3 --lote lote_bruto.csv
                                     │
                       prospectos_brevo.csv  ──►  Brevo (sequência dia 0/4/11)
```

## Rotina mensal (ordem exata)

**1. Baixar a base do mês — automático:**
```
python 0_baixar_receita.py --pasta ./dados_receita
```
O script descobre sozinho o mês mais recente, baixa `Estabelecimentos0-9.zip`,
`Municipios.zip` e `Empresas0-9.zip`, com retomada automática se a conexão
cair no meio (não perde o que já baixou) e nova tentativa em caso de falha.
Se o servidor recusar algum arquivo (acontece às vezes, portais públicos
limitam acesso automatizado), ele avisa exatamente qual e te dá o link para
baixar manualmente pelo navegador — nunca trava sem explicação.
Ou use `rodar_motor.sh`/`.bat`, que já pergunta e faz isso por você.

**2. Destilar** (a única etapa demorada; ~20–40 min conforme a máquina):
```
python 1_destilar_ms.py --pasta ./dados_receita --ref 2026-08 --com-empresas
```
Se rodar de novo com a mesma `--ref`, ele detecta e não refaz nada.

**3. Acumular a RPI da semana** (30 segundos; ideal: toda terça):
```
python 3_cruzar_inpi_exportar.py --baixar-rpi 2880 2884
```
O número da RPI vigente está em revistas.inpi.gov.br. O script pula as já
lidas — pode passar intervalos largos sem medo.

**4. Gerar o lote do mês** (instantâneo):
```
python 2_gerar_lote.py --meses 3 --lote 100
```
- `--raios 1,2` limita a Campo Grande + entorno (recomendado nos 2 primeiros meses)
- `--jucems arquivo.csv` usa os números oficiais (formato: `MUNICIPIO;ABERTURAS`),
  baixados do Mapa de Empresas (gov.br → Empresas & Negócios → Mapa de Empresas).
  Sem o arquivo, o motor calcula o mesmo sinal da própria base — funciona igual.

**5. Cruzar com o INPI e exportar**:
```
python 3_cruzar_inpi_exportar.py --lote lote_bruto.csv
```
Gera `prospectos_brevo.csv` (importar no Brevo) e `conferencia_inpi.csv`
(checagem manual de 10 segundos por empresa, recomendada no lote piloto).

**6. Subir no Brevo e disparar** a sequência do Bloco 2 (pasta `emails/`).

## Decisões de engenharia (por que assim, e não de outro jeito)

| Risco | Mitigação implementada |
|---|---|
| Base da Receita gigantesca | Destilaria: 1 passada única → SQLite local; nunca mais relê os ZIPs |
| API paga do INPI | Base própria acumulada da RPI (XML público, de graça, toda semana) |
| RPI não traz CNPJ do titular | Cruzamento por razão social normalizada + UF; alvo são empresas recém-abertas (chance de já ter marca ≈ zero); links de conferência manual no piloto |
| E-mail do contador na base | Filtro de padrões (`contab`, `escritorio`) + dedupe por e-mail |
| Reputação do domínio | Lote inicial de 100, aquecimento gradual, descadastro em 1 clique, DKIM/SPF no Brevo antes do 1º disparo |
| Lote frio demais | Raios: esgota Campo Grande antes de avançar; dentro do raio, prioriza municípios com mais aberturas (sinal JUCEMS) |


## A fila persistente (corrige o "e depois?")

Pergunta que todo sistema de raios precisa responder: **quando Campo Grande
(Raio 1) não tiver mais empresas novas suficientes num mês, o que acontece?**

Resposta antiga (falha silenciosa): nada — o lote simplesmente encolhia,
mês a mês, sem avisar ninguém, e pior: uma empresa que aparecia como
candidata mas não coubesse no lote de um mês podia **desaparecer para
sempre** assim que a janela de `--meses` avançasse, sem nunca ter sido
contatada.

Resposta atual: toda empresa elegível entra numa **fila persistente**
(tabela `fila_candidatos`, dentro do próprio `base_ms.sqlite`) na primeira
vez que aparece, e só sai dela quando for de fato selecionada num lote —
nunca por causa do calendário. Quem não coube este mês é o primeiro da
fila no mês seguinte (FIFO por raio, depois por momento da cidade, depois
por quem está esperando há mais tempo). Só expira depois de
`--expirar-meses` (padrão: 15 meses) sem ser chamado.

Quando o Raio 1 (e o 2, se ativo) esgotarem o estoque de candidatos
qualificados num mês — sinal disso: o lote vem menor que a metade da meta
— duas coisas podem acontecer, conforme `motor_config.json`:

- `"raios_auto_expandir": false` (padrão) — o motor **avisa** no painel
  (aba Motor Auto) que o estoque está baixo e sugere expandir, mas não
  muda nada sozinho. Decisão deliberada: Raio 3/4 (Dourados, Corumbá,
  Três Lagoas...) ficam a centenas de km de Campo Grande, onde reunião
  presencial não é mais um diferencial de fechamento — expandir aí muda
  o perfil comercial do lead, e isso deveria ser uma escolha sua, não
  automática.
- `"raios_auto_expandir": true` — o motor expande sozinho para o próximo
  raio (1 → 1,2 → 1,2,3 → 1,2,3,4) e atualiza `motor_config.json`,
  registrando o porquê no alerta.



## JUCEMS real (não é mais só o substituto)

O motor agora busca o dado oficial da JUCEMS antes de gerar o lote:
`jucems_real.py` consulta a API do CKAN do Portal de Dados Abertos de MS
(`dados.ms.gov.br/dataset/jucems`) e baixa o CSV mais recente de "Empresas
Constituídas" — sem depender de adivinhar o nome do arquivo, que muda todo
mês (ex.: `.../2026/07/Empresas_Constituidas.csv`).

Como toda peça que depende de um site de terceiro (um portal estadual,
mantido por equipe pequena), isso tem mitigação em camadas:
1. **Coluna por nome, não por posição** — o parser procura "MUNICIPIO",
   "QUANTIDADE"/"TOTAL" etc. entre os cabeçalhos, tolerando o portal
   reordenar ou renomear colunas.
2. **Qualquer falha é não-fatal** — rede fora do ar, formato mudou,
   recurso renomeado: o motor registra um aviso (não um erro) e usa
   sozinho, no mesmo ciclo, o sinal calculado da própria base — a
   cobertura de raios e o disparo ao Brevo continuam normalmente.
3. **Testado com 5 variações plausíveis de formato** (delimitador `;` ou
   `,`, nomes de coluna diferentes, linhas repetidas por mês que devem
   somar, e o caso de a coluna simplesmente não existir) antes de ir
   para produção.

Para usar manualmente: `python jucems_real.py` gera `jucems_atual.csv`,
que pode ser passado direto para `2_gerar_lote.py --jucems jucems_atual.csv`.
No ciclo automático mensal, isso já acontece sozinho, sem nenhuma ação sua.

## Requisitos
Python 3.10+ apenas (só biblioteca padrão — sem pip install de nada).
