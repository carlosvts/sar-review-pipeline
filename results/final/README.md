# Etapa 07: tabela final e análise (25/11/2026)

Resultado final da revisão depois da convergência do snowballing na rodada 8. Nada aqui usa LLM: as respostas às QPs são
a marcação humana do artefato de triagem (rodadas 1 a 7) e da planilha verificada do start set (rodada 0); o resto é
contagem em pandas sobre o que já estava salvo.

Regerar tudo, da raiz do repo:

```bash
uv run --extra analysis python scripts/final/dados.py      # tabelas, OpenAlex (cache em dados/openalex_includes.json)
uv run --extra analysis python scripts/final/mineracao.py  # contagem de termos nos textos completos
uv run --extra analysis python scripts/final/figuras.py    # figuras/
uv run --extra analysis python scripts/final/prisma.py     # prisma/
uv run --extra analysis python scripts/final/painel.py     # painel/ (CSVs do painel interativo)
```

## Números finais

| | |
|---|---|
| Registros identificados | 9.930 (start set 16 + snowballing 9.914, rodadas 1–8) |
| Excluídos pelo título | 7.937 (2 sem triagem concluída) |
| Abstracts avaliados / sem abstract | 1.977 / 156 |
| Agrupados por tema / em clusters não mantidos | 1.821 / 1.508 |
| Textos completos buscados / sem texto (EC6) | 329 / 57 |
| Lidos / excluídos / só semente (EC4) | 272 / 107 / 27 |
| **Incluídos** | **138** (13, 27, 33, 28, 20, 13, 3, 1 nas rodadas 0 a 7) |

## O que tem em cada pasta

- `tabela_final.xlsx`: abas `includes` (138), `extracao_QP1-QP4` (uma linha por artigo e QP, com a resposta do revisor
  e os 3 trechos do RAG), `funil_rodadas` e `texto_completo_todos` (329 decisões).
- `prisma/`: `prisma_final` (fluxograma PRISMA 2020), `prisma_por_rodada` (tabela) e `prisma_contagens.json`.
- `figuras/`: 46 figuras em PNG (300 dpi) e SVG; a lista está abaixo e em `figuras/indice.csv`.
- `dados/`: os CSVs de onde saem as figuras.
  - `includes.csv`: metadados, QPs e OpenAlex.
  - `texto_completo_decisoes.csv`.
  - `evidencias_rag.csv`.
  - `extracao_QP1-QP4.csv`.
  - `funil_rodadas.csv`.
  - `autores_instituicoes.csv`, `topicos.csv` e `keywords.csv`.
  - `mencoes_*.csv`: contagem por artigo e categoria.
  - `robo_principal.csv`, `dominante_contexto_populacao.csv` e `amostra_auto.csv`.
- `painel/`: CSVs enxutos do painel interativo (artefato "Síntese SAR em Saúde").

## Como ler as contagens de termos

`mineracao.py` procura padrões (dicionários em expressões regulares) no texto completo extraído, sem a folha de rosto,
as afiliações e as referências.

- Um artigo conta numa categoria quando o padrão aparece 2 vezes ou mais.
- O robô principal é o nome mais citado, com 3 menções ou mais. Sem isso, o artigo fica como "robô citado de
  passagem" (algum nome com 1 ou 2 menções) ou "nenhum robô nomeado". O dicionário inclui os robôs próprios achados
  nos textos (Robin, Flo/Lil'Flo, Edù, Mirrly, URSUS, Pukkabot, MAKI/IVEY, LOVOT, Cocoron etc.); a morfologia de um
  robô próprio só é dada quando o texto a descreve, senão fica "próprio (não classificado)".
- O contexto e a população dominantes são a categoria mais citada, com 3 menções ou mais.
- O N de participantes é o primeiro "N = x" ou "x participants" das seções de método. É aproximado; confira no
  trecho em `amostra_auto.csv`.

Essas contagens medem presença no texto, não a resposta à QP. Servem para descrever o corpus; a síntese das QPs
continua sendo a leitura dos trechos.

## Figuras

| nº | arquivo | título | fonte |
|---|---|---|---|
| 1 | [01_funil_rodadas](figuras/01_funil_rodadas.png) | Funil do snowballing por rodada | funil_rodadas.csv |
| 2 | [02_convergencia](figuras/02_convergencia.png) | Convergência do snowballing | funil_rodadas.csv |
| 3 | [03_taxas_passagem](figuras/03_taxas_passagem.png) | Taxa de passagem entre etapas por rodada | funil_rodadas.csv |
| 4 | [04_exclusoes_por_codigo](figuras/04_exclusoes_por_codigo.png) | Texto completo: não incluídos por critério e rodada | texto_completo_decisoes.csv |
| 5 | [05_obtencao_texto](figuras/05_obtencao_texto.png) | Obtenção do texto completo por rodada | texto_completo_decisoes.csv |
| 6 | [06_includes_rodada_direcao](figuras/06_includes_rodada_direcao.png) | Incluídos por rodada e direção | tabela final (results/final/dados) |
| 7 | [07_includes_por_ano](figuras/07_includes_por_ano.png) | Incluídos por ano de publicação | tabela final (results/final/dados) |
| 8 | [08_tipo_publicacao](figuras/08_tipo_publicacao.png) | Incluídos por tipo de publicação | tabela final (results/final/dados) |
| 9 | [09_top_veiculos](figuras/09_top_veiculos.png) | 15 veículos com mais incluídos | OpenAlex (primary_location) |
| 10 | [10_top_editoras](figuras/10_top_editoras.png) | Editoras com mais incluídos | OpenAlex (host_organization) |
| 11 | [11_paises](figuras/11_paises.png) | Países das instituições dos autores (artigos com ≥1 autor do país) | OpenAlex (authorships.institutions) |
| 12 | [12_instituicoes](figuras/12_instituicoes.png) | 15 instituições com mais incluídos | OpenAlex (authorships.institutions) |
| 13 | [13_colaboracao_internacional](figuras/13_colaboracao_internacional.png) | Colaboração internacional (nº de países por artigo) | OpenAlex |
| 14 | [14_topicos_openalex](figuras/14_topicos_openalex.png) | Tópico principal do OpenAlex (12 mais frequentes) | OpenAlex (primary_topic) |
| 15 | [15_subcampos_openalex](figuras/15_subcampos_openalex.png) | Subcampos do OpenAlex (artigos com o subcampo em algum tópico) | OpenAlex (topics) |
| 16 | [16_citacoes](figuras/16_citacoes.png) | Distribuição de citações | OpenAlex (cited_by_count) |
| 17 | [17_acesso_aberto](figuras/17_acesso_aberto.png) | Status de acesso aberto dos incluídos | OpenAlex (open_access) |
| 18 | [18_n_autores](figuras/18_n_autores.png) | Número de autores por artigo | tabela final (results/final/dados) |
| 19 | [19_artigos_por_qp](figuras/19_artigos_por_qp.png) | Incluídos que respondem a cada QP (marcação do revisor) | artefato de triagem (marcação humana) |
| 20 | [20_upset_qps](figuras/20_upset_qps.png) | Combinações de QPs (UpSet) | artefato de triagem (marcação humana) |
| 21 | [21_n_qps_por_artigo](figuras/21_n_qps_por_artigo.png) | Quantas QPs cada incluído responde | artefato de triagem |
| 22 | [22_qp_por_rodada](figuras/22_qp_por_rodada.png) | Proporção de incluídos que respondem a cada QP, por rodada | artefato de triagem |
| 23 | [23_qp_por_periodo](figuras/23_qp_por_periodo.png) | Proporção que responde a cada QP, por período de publicação | artefato de triagem |
| 24 | [24_coocorrencia_qps](figuras/24_coocorrencia_qps.png) | Coocorrência de QPs (nº de artigos que respondem às duas) | artefato de triagem |
| 25 | [25_rag_cos_vs_revisor](figuras/25_rag_cos_vs_revisor.png) | RAG × revisor (cosseno do melhor trecho) | evidencias_rag.csv |
| 26 | [26_rag_secoes](figuras/26_rag_secoes.png) | Seções de onde veio o melhor trecho do RAG | evidencias_rag.csv (1º trecho de cada QP) |
| 27 | [27_recomendacao_vs_revisor](figuras/27_recomendacao_vs_revisor.png) | Recomendação automática × decisão do revisor (rodadas 3–7, n=147) | texto_completo_decisoes.csv |
| 28 | [28_contexto](figuras/28_contexto.png) | Contexto de aplicação mencionado no texto | contagem de termos no texto completo (≥2 menções por artigo), N=138 includes |
| 29 | [29_populacao](figuras/29_populacao.png) | População mencionada no texto | contagem de termos no texto completo (≥2 menções por artigo), N=138 includes |
| 30 | [30_contexto_dominante](figuras/30_contexto_dominante.png) | Contexto dominante (o mais mencionado no artigo, ≥3 menções) | contagem de termos no texto completo (categoria com mais menções) |
| 31 | [31_populacao_dominante](figuras/31_populacao_dominante.png) | População dominante (a mais mencionada no artigo, ≥3 menções) | contagem de termos no texto completo (categoria com mais menções) |
| 32 | [32_robo_principal](figuras/32_robo_principal.png) | Robô mais citado em cada artigo (≥3 menções) | dicionário de robôs no texto completo |
| 33 | [33_morfologia](figuras/33_morfologia.png) | Morfologia do robô principal | dicionário de robôs (NAO, Pepper = humanoide; PARO, Huggable = zoomórfico...) |
| 34 | [34_robos_mencionados](figuras/34_robos_mencionados.png) | Robôs mencionados (≥2 vezes no artigo) | dicionário de robôs no texto completo |
| 35 | [35_qp1_fisico](figuras/35_qp1_fisico.png) | QP1: características físicas e visuais mencionadas (artigos que respondem à QP1, n=90) | contagem de termos no texto completo (≥2 menções por artigo), N=138 includes |
| 36 | [36_qp2_comunicacao](figuras/36_qp2_comunicacao.png) | QP2: modalidades de comunicação mencionadas (artigos que respondem à QP2, n=129) | contagem de termos no texto completo (≥2 menções por artigo), N=138 includes |
| 37 | [37_qp3_emocao](figuras/37_qp3_emocao.png) | QP3: emoção e personalidade mencionadas (artigos que respondem à QP3, n=88) | contagem de termos no texto completo (≥2 menções por artigo), N=138 includes |
| 38 | [38_qp4_avaliacao](figuras/38_qp4_avaliacao.png) | QP4: métodos e instrumentos de avaliação mencionados (artigos que respondem à QP4, n=121) | contagem de termos no texto completo (≥2 menções por artigo), N=138 includes |
| 39 | [39_desenho_estudo](figuras/39_desenho_estudo.png) | Desenho do estudo mencionado no texto | contagem de termos no texto completo (≥2 menções por artigo), N=138 includes |
| 40 | [40_tamanho_amostral](figuras/40_tamanho_amostral.png) | Tamanho amostral (extração automática) | amostra_auto.csv |
| 41 | [41_contexto_x_qp](figuras/41_contexto_x_qp.png) | Proporção que responde a cada QP, por contexto (contextos com ≥5 artigos) | contagem de termos no texto completo (≥2 menções por artigo), N=138 includes |
| 42 | [42_populacao_x_qp](figuras/42_populacao_x_qp.png) | Proporção que responde a cada QP, por população (≥5 artigos) | contagem de termos no texto completo (≥2 menções por artigo), N=138 includes |
| 43 | [43_morfologia_x_qp](figuras/43_morfologia_x_qp.png) | Proporção que responde a cada QP, por morfologia do robô principal | dicionário de robôs + marcação humana |
| 44 | [44_populacao_x_contexto](figuras/44_populacao_x_contexto.png) | População × contexto (nº de artigos que mencionam os dois) | contagem de termos no texto completo (≥2 menções por artigo), N=138 includes |
| 45 | [45_instrumentos_por_periodo](figuras/45_instrumentos_por_periodo.png) | Instrumentos de avaliação por período de publicação | contagem de termos no texto completo (≥2 menções por artigo), N=138 includes |
| 46 | [46_comunicacao_por_periodo](figuras/46_comunicacao_por_periodo.png) | Modalidades de comunicação por período de publicação | contagem de termos no texto completo (≥2 menções por artigo), N=138 includes |
