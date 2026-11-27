"""
Etapa 07, parte 3: figuras estáticas (PNG 300 dpi + SVG) a partir de results/final/dados/.

  uv run --extra analysis python scripts/final/figuras.py

Grava results/final/figuras/NN_nome.{png,svg} e results/final/figuras/indice.csv (número, arquivo, título, fonte).
"""
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

DADOS = Path("results/final/dados")
FIG = Path("results/final/figuras")
QPS = ["QP1", "QP2", "QP3", "QP4"]
QP_NOMES = {"QP1": "QP1 físico/visual", "QP2": "QP2 comunicação", "QP3": "QP3 emoção/personalidade",
            "QP4": "QP4 avaliação"}
MIN_HITS = 2

# paleta de referência (modo claro), ordem fixa
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BLUE = CAT[0]
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#fcfcfb"
SEQ = LinearSegmentedColormap.from_list("seq", ["#f4f8fd", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "figure.facecolor": "white", "axes.facecolor": "white", "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlecolor": INK, "axes.titlelocation": "left", "legend.frameon": False, "svg.fonttype": "none",
})


class Figuras:
    index: list[dict] = []
    n = 0

    @classmethod
    def save(cls, fig, nome: str, titulo: str, fonte: str, tight: bool = True) -> None:
        cls.n += 1
        stem = f"{cls.n:02d}_{nome}"
        width = int(fig.get_figwidth() * 10.5)
        if tight:
            fig.tight_layout(rect=(0, 0.04, 1, 1))
        for ax in fig.axes:
            title = ax.get_title(loc="left")
            chars = int(ax.get_position().width * fig.get_figwidth() * 7.2)
            if title and len(title) > chars:
                ax.set_title(textwrap.fill(title, max(chars, 30)), loc="left")
        fig.text(0.01, 0.005, textwrap.fill(f"Fonte: {fonte}", int(width * 1.6)), fontsize=7, color=MUTED,
                 ha="left", va="bottom")
        if tight:
            fig.tight_layout(rect=(0, 0.04, 1, 1))
        fig.savefig(FIG / f"{stem}.png", dpi=300)
        fig.savefig(FIG / f"{stem}.svg")
        plt.close(fig)
        cls.index.append({"n": cls.n, "arquivo": stem, "titulo": titulo, "fonte": fonte})

    @classmethod
    def barh(cls, series: pd.Series, nome: str, titulo: str, fonte: str, xlabel: str = "artigos",
             total: int | None = None, color: str = BLUE, muted: tuple = ()) -> None:
        series = series[series > 0].sort_values()
        fig, ax = plt.subplots(figsize=(7, max(2.2, 0.28 * len(series) + 0.9)))
        colors = [MUTED if label in muted else color for label in series.index]
        ax.barh(series.index.astype(str), series.values, color=colors, height=0.68)
        for y, v in enumerate(series.values):
            label = f"{v}" if total is None else f"{v} ({v / total:.0%})"
            ax.text(v + series.max() * 0.01, y, label, va="center", fontsize=8, color=INK2)
        ax.set_xlim(0, series.max() * 1.18)
        ax.set_xlabel(xlabel)
        ax.grid(axis="y", visible=False)
        ax.set_title(titulo)
        cls.save(fig, nome, titulo, fonte)

    @classmethod
    def heatmap(cls, df: pd.DataFrame, nome: str, titulo: str, fonte: str, fmt: str = "{:.0%}",
                annot: pd.DataFrame | None = None, cbar_label: str = "") -> None:
        fig, ax = plt.subplots(figsize=(max(5, 0.9 * df.shape[1] + 3), max(2.5, 0.36 * df.shape[0] + 1.2)))
        im = ax.imshow(df.values.astype(float), cmap=SEQ, aspect="auto", vmin=0)
        ax.set_xticks(range(df.shape[1]), df.columns, rotation=30, ha="right")
        ax.set_yticks(range(df.shape[0]), df.index)
        ax.grid(False)
        vmax = np.nanmax(df.values.astype(float)) or 1
        for i in range(df.shape[0]):
            for j in range(df.shape[1]):
                v = df.values[i, j]
                text = fmt.format(v) if annot is None else annot.values[i, j]
                ax.text(j, i, text, ha="center", va="center", fontsize=7.5,
                        color="white" if v > vmax * 0.55 else INK)
        cb = fig.colorbar(im, ax=ax, shrink=0.8)
        cb.outline.set_visible(False)
        cb.set_label(cbar_label, color=INK2)
        ax.set_title(titulo)
        cls.save(fig, nome, titulo, fonte)

    @classmethod
    def stacked(cls, df: pd.DataFrame, nome: str, titulo: str, fonte: str, xlabel: str = "",
                ylabel: str = "artigos", colors: list[str] | None = None) -> None:
        colors = colors or CAT
        fig, ax = plt.subplots(figsize=(7.5, 3.6))
        bottom = np.zeros(len(df))
        x = np.arange(len(df))
        for i, col in enumerate(df.columns):
            ax.bar(x, df[col].values, bottom=bottom, color=colors[i % len(colors)], label=col, width=0.7,
                   edgecolor="white", linewidth=1)
            bottom += df[col].values
        for xi, tot in zip(x, bottom):
            ax.text(xi, tot + bottom.max() * 0.01, f"{int(tot)}", ha="center", va="bottom", fontsize=8, color=INK2)
        ax.set_xticks(x, df.index.astype(str))
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(axis="x", visible=False)
        ax.legend(ncol=min(4, len(df.columns)), loc="upper right", fontsize=8)
        ax.set_title(titulo)
        cls.save(fig, nome, titulo, fonte)


def presence(path: str, keys: pd.Series) -> pd.DataFrame:
    df = pd.read_csv(DADOS / path).set_index("key").loc[keys]
    return df >= MIN_HITS


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    inc = pd.read_csv(DADOS / "includes.csv")
    dec = pd.read_csv(DADOS / "texto_completo_decisoes.csv")
    funil = pd.read_csv(DADOS / "funil_rodadas.csv")
    ev = pd.read_csv(DADOS / "evidencias_rag.csv")
    aut = pd.read_csv(DADOS / "autores_instituicoes.csv")
    top = pd.read_csv(DADOS / "topicos.csv")
    rob = pd.read_csv(DADOS / "robo_principal.csv").set_index("key").loc[inc.key]
    amostra = pd.read_csv(DADOS / "amostra_auto.csv").set_index("key").loc[inc.key]
    N = len(inc)
    F = "tabela final (results/final/dados)"
    FM = f"contagem de termos no texto completo (≥{MIN_HITS} menções por artigo), N={N} includes"

    # ---- funil e snowballing
    fig, axes = plt.subplots(1, 4, figsize=(11, 3.3), sharey=True)
    etapas = [("coletados", "Coletados"), ("candidatos", "Passaram no título"),
              ("texto_completo_avaliados", "Texto completo"), ("include", "Incluídos")]
    for ax, (col, lab), color in zip(axes, etapas, [CAT[0], CAT[0], CAT[0], CAT[2]]):
        ax.barh(funil.rodada.astype(str), funil[col], color=color, height=0.68)
        for y, v in enumerate(funil[col]):
            ax.text(v + funil[col].max() * 0.02, y, str(v), va="center", fontsize=7.5, color=INK2)
        ax.set_xlim(0, funil[col].max() * 1.3)
        ax.set_title(lab, fontsize=9.5)
        ax.grid(axis="y", visible=False)
        ax.invert_yaxis() if ax is axes[0] else None
    axes[0].set_ylabel("rodada")
    fig.suptitle("Funil do snowballing por rodada", x=0.01, ha="left", fontweight="bold", color=INK)
    Figuras.save(fig, "funil_rodadas", "Funil do snowballing por rodada", "funil_rodadas.csv")

    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    ax.plot(funil.rodada, funil.include, color=CAT[2], lw=2, marker="o", ms=6, label="incluídos")
    ax.plot(funil.rodada, funil.seeds_proxima, color=CAT[0], lw=2, marker="o", ms=6, label="sementes p/ próxima")
    for x, y in zip(funil.rodada, funil.include):
        ax.text(x, y + 1.2, str(y), ha="center", fontsize=8, color=INK2)
    ax.set_xticks(funil.rodada)
    ax.set_xlabel("rodada")
    ax.set_ylabel("artigos")
    ax.legend()
    ax.set_title("Convergência: incluídos e sementes por rodada (Wohlin: para quando não há novos incluídos)")
    Figuras.save(fig, "convergencia", "Convergência do snowballing", "funil_rodadas.csv")

    taxa = funil[funil.rodada >= 1].set_index("rodada")
    taxa = pd.DataFrame({"título → candidatos": taxa.candidatos / taxa.coletados,
                         "candidatos → texto completo": taxa.texto_completo_avaliados / taxa.candidatos,
                         "texto completo → incluído": taxa.include / taxa.texto_completo_avaliados.replace(0, np.nan)})
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    for i, col in enumerate(taxa.columns):
        ax.plot(taxa.index, taxa[col], color=CAT[i], lw=2, marker="o", ms=6, label=col)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1))
    ax.set_xlabel("rodada")
    ax.set_ylabel("proporção que segue")
    ax.legend(fontsize=8)
    ax.set_title("Taxa de passagem entre etapas por rodada")
    Figuras.save(fig, "taxas_passagem", "Taxa de passagem entre etapas por rodada", "funil_rodadas.csv")

    codes = ["EC1", "EC2", "EC3", "EC5", "EC6", "EC7", "IC6"]
    ex = dec[dec.decisao != "include"].copy()
    ex["motivo_cod"] = np.where(ex.decisao == "seed_only", "EC4 (seed_only)", ex.codigo.fillna(""))
    tab = ex.pivot_table(index="rodada", columns="motivo_cod", values="key", aggfunc="count", fill_value=0)
    tab = tab[[c for c in ["EC1", "EC2", "EC3", "EC4 (seed_only)", "EC5", "EC6", "EC7", "IC6"] if c in tab.columns]]
    Figuras.stacked(tab, "exclusoes_por_codigo", "Texto completo: não incluídos por critério e rodada",
                    "texto_completo_decisoes.csv", xlabel="rodada")

    st = dec.copy()
    st["status"] = np.where(st.codigo == "EC6", "sem texto (EC6)",
                            np.where(st.texto == "downloaded", "download automático", "busca manual (CAPES/AA)"))
    tab = st.pivot_table(index="rodada", columns="status", values="key", aggfunc="count", fill_value=0)
    tab = tab[["download automático", "busca manual (CAPES/AA)", "sem texto (EC6)"]]
    Figuras.stacked(tab, "obtencao_texto", "Obtenção do texto completo por rodada", "texto_completo_decisoes.csv",
                    xlabel="rodada", colors=[CAT[0], CAT[2], CAT[7]])

    tab = inc.pivot_table(index="rodada", columns="direcao", values="key", aggfunc="count", fill_value=0)
    tab = tab[[c for c in ["start_set", "backward", "forward", "both"] if c in tab.columns]]
    Figuras.stacked(tab, "includes_rodada_direcao", "Incluídos por rodada e direção", F, xlabel="rodada")

    # ---- bibliometria
    anos = inc.ano.value_counts().sort_index()
    anos = anos.reindex(range(int(anos.index.min()), int(anos.index.max()) + 1), fill_value=0)
    fig, ax = plt.subplots(figsize=(8, 3.3))
    ax.bar(anos.index, anos.values, color=BLUE, width=0.75)
    for x, v in anos.items():
        if v:
            ax.text(x, v + 0.3, str(v), ha="center", fontsize=7, color=INK2)
    ax.set_xlabel("ano de publicação")
    ax.set_ylabel("artigos")
    ax.grid(axis="x", visible=False)
    ax.set_title(f"Incluídos por ano de publicação (N={N})")
    Figuras.save(fig, "includes_por_ano", "Incluídos por ano de publicação", F)

    tipo = inc.tipo.replace({"article": "artigo de periódico", "conference-paper": "artigo de conferência",
                             "book-chapter": "capítulo de livro", "dissertation": "tese/dissertação",
                             "preprint": "preprint"}).value_counts()
    Figuras.barh(tipo, "tipo_publicacao", "Incluídos por tipo de publicação", F, total=N)
    Figuras.barh(inc.veiculo.fillna("(sem veículo)").value_counts().head(15), "top_veiculos",
                 "15 veículos com mais incluídos", "OpenAlex (primary_location)")
    Figuras.barh(inc.editora.fillna("(sem editora)").value_counts().head(12), "top_editoras",
                 "Editoras com mais incluídos", "OpenAlex (host_organization)")

    paises = aut.dropna(subset=["pais"]).drop_duplicates(["key", "pais"]).pais.value_counts().head(20)
    Figuras.barh(paises, "paises", "Países das instituições dos autores (artigos com ≥1 autor do país)",
                 "OpenAlex (authorships.institutions)", total=N)
    inst = aut.dropna(subset=["instituicao"]).drop_duplicates(["key", "instituicao"]).instituicao.value_counts().head(15)
    Figuras.barh(inst, "instituicoes", "15 instituições com mais incluídos", "OpenAlex (authorships.institutions)")
    collab = pd.cut(inc.n_paises, [-1, 0, 1, 2, 100], labels=["sem país", "1 país", "2 países", "3+ países"])
    Figuras.barh(collab.value_counts().reindex(["sem país", "1 país", "2 países", "3+ países"]),
                 "colaboracao_internacional", "Colaboração internacional (nº de países por artigo)",
                 "OpenAlex", total=N)
    Figuras.barh(inc.topico.fillna("(sem tópico)").value_counts().head(12), "topicos_openalex",
                 "Tópico principal do OpenAlex (12 mais frequentes)", "OpenAlex (primary_topic)")
    sub = top.drop_duplicates(["key", "subcampo"]).subcampo.value_counts().head(12)
    Figuras.barh(sub, "subcampos_openalex", "Subcampos do OpenAlex (artigos com o subcampo em algum tópico)",
                 "OpenAlex (topics)", total=N)

    fig, ax = plt.subplots(figsize=(7.5, 3.3))
    bins = [0, 1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000]
    counts = pd.cut(inc.citacoes, bins, right=False).value_counts().sort_index()
    labels = ["0", "1–4", "5–9", "10–24", "25–49", "50–99", "100–249", "250–499", "500–999", "1000+"]
    ax.bar(labels, counts.values, color=BLUE, width=0.75)
    for i, v in enumerate(counts.values):
        ax.text(i, v + 0.3, str(v), ha="center", fontsize=8, color=INK2)
    ax.set_xlabel("citações (OpenAlex, 25/11/2026)")
    ax.set_ylabel("artigos")
    ax.grid(axis="x", visible=False)
    ax.set_title(f"Distribuição de citações dos incluídos (mediana {inc.citacoes.median():.0f})")
    Figuras.save(fig, "citacoes", "Distribuição de citações", "OpenAlex (cited_by_count)")

    oa = inc.oa_status.fillna("desconhecido").value_counts()
    Figuras.barh(oa, "acesso_aberto", "Status de acesso aberto dos incluídos", "OpenAlex (open_access)", total=N)
    Figuras.barh(inc.n_autores.clip(upper=12).value_counts().sort_index().rename(lambda x: "12+" if x == 12 else str(x)),
                 "n_autores", "Número de autores por artigo", F)

    # ---- QPs
    qp = inc[QPS].sum().rename(QP_NOMES)
    Figuras.barh(qp, "artigos_por_qp", "Incluídos que respondem a cada QP (marcação do revisor)",
                 "artefato de triagem (marcação humana)", total=N, color=CAT[0])

    combos = inc.combinacao_qps.value_counts()
    fig = plt.figure(figsize=(8, 4.4))
    gs = fig.add_gridspec(2, 1, height_ratios=[2.2, 1], hspace=0.05)
    ax1, ax2 = fig.add_subplot(gs[0]), fig.add_subplot(gs[1])
    x = np.arange(len(combos))
    ax1.bar(x, combos.values, color=BLUE, width=0.6)
    for xi, v in zip(x, combos.values):
        ax1.text(xi, v + 0.5, str(v), ha="center", fontsize=8, color=INK2)
    ax1.set_xticks([])
    ax1.set_ylabel("artigos")
    ax1.grid(axis="x", visible=False)
    ax1.set_title("Combinações de QPs respondidas (UpSet)")
    for j, q in enumerate(QPS):
        on = [q in c.split("+") for c in combos.index]
        ax2.scatter(x, [j] * len(x), s=40, color=[INK if o else GRID for o in on], zorder=3)
        for xi, o in zip(x, on):
            pass
    for xi, c in zip(x, combos.index):
        ys = [j for j, q in enumerate(QPS) if q in c.split("+")]
        if len(ys) > 1:
            ax2.plot([xi, xi], [min(ys), max(ys)], color=INK, lw=1.5, zorder=2)
    ax2.set_yticks(range(4), [QP_NOMES[q] for q in QPS])
    ax2.set_xticks([])
    ax2.set_xlim(ax1.get_xlim())
    ax2.invert_yaxis()
    ax2.grid(False)
    for s in ax2.spines.values():
        s.set_visible(False)
    fig.subplots_adjust(left=0.27, right=0.98, top=0.92, bottom=0.08)
    Figuras.save(fig, "upset_qps", "Combinações de QPs (UpSet)", "artefato de triagem (marcação humana)", tight=False)

    Figuras.barh(inc.n_qps.value_counts().sort_index().rename(lambda x: f"{x} QP" + ("s" if x != 1 else "")),
                 "n_qps_por_artigo", "Quantas QPs cada incluído responde", "artefato de triagem", total=N)

    by = inc.groupby("rodada")[QPS].mean().rename(columns=QP_NOMES)
    by.index = [f"rodada {i} (n={c})" for i, c in inc.rodada.value_counts().sort_index().items()]
    Figuras.heatmap(by, "qp_por_rodada", "Proporção de incluídos que respondem a cada QP, por rodada",
                    "artefato de triagem", cbar_label="proporção")

    per = pd.cut(inc.ano, [0, 2010, 2015, 2020, 2023, 2100], labels=["até 2010", "2011–2015", "2016–2020",
                                                                      "2021–2023", "2024+"])
    by = inc.groupby(per, observed=True)[QPS].mean().rename(columns=QP_NOMES)
    by.index = [f"{i} (n={c})" for i, c in per.value_counts().sort_index().items() if c]
    Figuras.heatmap(by, "qp_por_periodo", "Proporção que responde a cada QP, por período de publicação",
                    "artefato de triagem", cbar_label="proporção")

    corr = pd.DataFrame(index=[QP_NOMES[q] for q in QPS], columns=[QP_NOMES[q] for q in QPS], dtype=float)
    annot = corr.copy().astype(object)
    for a in QPS:
        for b in QPS:
            both = int((inc[a] & inc[b]).sum())
            corr.loc[QP_NOMES[a], QP_NOMES[b]] = both / N
            annot.loc[QP_NOMES[a], QP_NOMES[b]] = str(both)
    Figuras.heatmap(corr, "coocorrencia_qps", "Coocorrência de QPs (nº de artigos que respondem às duas)",
                    "artefato de triagem", annot=annot, cbar_label="proporção do total")

    # ---- RAG x revisor
    best = ev[ev["rank"] == 1]
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    pos = 0
    ticks, labs = [], []
    for i, q in enumerate(QPS):
        for marked, color in [(True, CAT[0]), (False, MUTED)]:
            vals = best[(best.QP == q) & (best.qp_marcada_revisor == marked)].cos
            if len(vals):
                bp = ax.boxplot(vals, positions=[pos], widths=0.6, patch_artist=True, showfliers=False)
                for b in bp["boxes"]:
                    b.set(facecolor=color, alpha=0.35, edgecolor=color)
                for k in ["medians", "whiskers", "caps"]:
                    for l in bp[k]:
                        l.set(color=color)
                ax.scatter(np.random.default_rng(0).normal(pos, 0.06, len(vals)), vals, s=8, color=color, zorder=3)
            ticks.append(pos)
            labs.append(f"{q}\n{'marcada' if marked else 'não marcada'}\n(n={len(vals)})")
            pos += 1
        pos += 0.6
    ax.set_xticks(ticks, labs, fontsize=7.5)
    ax.set_ylabel("cosseno do 1º trecho")
    ax.grid(axis="x", visible=False)
    ax.set_title("Similaridade do melhor trecho do RAG: QP marcada × não marcada pelo revisor")
    Figuras.save(fig, "rag_cos_vs_revisor", "RAG × revisor (cosseno do melhor trecho)", "evidencias_rag.csv")

    sec = best.copy()
    sec["secao_raiz"] = sec.secao.fillna("").str.split(" > ").str[0].str.replace(r"^[\dIVX.]+\s*", "", regex=True)
    sec["secao_raiz"] = sec.secao_raiz.str.strip().str.lower().replace("", "(sem seção)")
    Figuras.barh(sec.secao_raiz.value_counts().head(15), "rag_secoes", "Seções de onde veio o melhor trecho do RAG",
                 "evidencias_rag.csv (1º trecho de cada QP)")

    rec = dec[(dec.rodada >= 3) & dec.rec_llm_decisao.notna() & (dec.codigo != "EC6")].copy()
    if len(rec):
        rec["humano"] = rec.decisao
        ct = pd.crosstab(rec.rec_llm_decisao, rec.humano)
        Figuras.heatmap(ct, "recomendacao_vs_revisor",
                        f"Recomendação automática × decisão do revisor (rodadas 3–7, n={len(rec)})",
                        "texto_completo_decisoes.csv", fmt="{:.0f}", cbar_label="artigos")

    # ---- contexto, população, robôs
    ctx = presence("mencoes_contexto.csv", inc.key)
    Figuras.barh(ctx.sum(), "contexto", "Contexto de aplicação mencionado no texto", FM, total=N)
    pop = presence("mencoes_populacao.csv", inc.key)
    Figuras.barh(pop.sum(), "populacao", "População mencionada no texto", FM, total=N)
    dom = pd.read_csv(DADOS / "dominante_contexto_populacao.csv")
    for grupo, titulo in [("contexto", "Contexto dominante (o mais mencionado no artigo, ≥3 menções)"),
                          ("populacao", "População dominante (a mais mencionada no artigo, ≥3 menções)")]:
        Figuras.barh(dom[dom.grupo == grupo].dominante.value_counts(), f"{grupo}_dominante", titulo,
                     "contagem de termos no texto completo (categoria com mais menções)", total=N)

    sem = ("nenhum robô nomeado", "robô citado de passagem", "próprio (não classificado)")
    Figuras.barh(rob.robo_principal.value_counts(), "robo_principal",
                 "Robô mais citado em cada artigo (≥3 menções; cinza = sem robô principal)",
                 "dicionário de robôs no texto completo (scripts/final/mineracao.py)", total=N, muted=sem)
    Figuras.barh(rob.morfologia.value_counts(), "morfologia", "Morfologia do robô principal (cinza = sem classificação)",
                 "dicionário de robôs; robôs próprios só têm morfologia quando o texto a descreve", total=N, muted=sem)
    rob_any = presence("mencoes_robos.csv", inc.key).sum()
    Figuras.barh(rob_any.sort_values().tail(20), "robos_mencionados", "Robôs mencionados (≥2 vezes no artigo)",
                 "dicionário de robôs no texto completo", total=N)

    # ---- termos por QP (todos os includes e só os que respondem à QP)
    for grupo, q, titulo in [("qp1_fisico", "QP1", "QP1: características físicas e visuais mencionadas"),
                             ("qp2_comunicacao", "QP2", "QP2: modalidades de comunicação mencionadas"),
                             ("qp3_emocao", "QP3", "QP3: emoção e personalidade mencionadas"),
                             ("qp4_avaliacao", "QP4", "QP4: métodos e instrumentos de avaliação mencionados")]:
        m = presence(f"mencoes_{grupo}.csv", inc.key)
        sel = inc.set_index("key")[q]
        n_q = int(sel.sum())
        Figuras.barh(m[sel.values].sum(), grupo, f"{titulo} (artigos que respondem à {q}, n={n_q})", FM,
                     total=n_q)
    des = presence("mencoes_desenho_estudo.csv", inc.key)
    Figuras.barh(des.sum(), "desenho_estudo", "Desenho do estudo mencionado no texto", FM, total=N)

    n = amostra.n_participantes_auto.dropna()
    n = n[n <= 1000]
    fig, ax = plt.subplots(figsize=(7.5, 3.3))
    bins = [1, 5, 10, 20, 30, 50, 100, 200, 500, 1001]
    counts = pd.cut(n, bins, right=False).value_counts().sort_index()
    labels = ["2–4", "5–9", "10–19", "20–29", "30–49", "50–99", "100–199", "200–499", "500–1000"]
    ax.bar(labels, counts.values, color=BLUE, width=0.75)
    for i, v in enumerate(counts.values):
        ax.text(i, v + 0.3, str(v), ha="center", fontsize=8, color=INK2)
    ax.set_xlabel("participantes (primeiro 'N = x' ou 'x participants' do método)")
    ax.set_ylabel("artigos")
    ax.grid(axis="x", visible=False)
    ax.set_title(f"Tamanho amostral extraído automaticamente (n={len(n)}, mediana {n.median():.0f}) — conferir")
    Figuras.save(fig, "tamanho_amostral", "Tamanho amostral (extração automática)", "amostra_auto.csv")

    # ---- cruzamentos
    def cross(m: pd.DataFrame, nome: str, titulo: str, fonte: str) -> None:
        qps = inc.set_index("key")[QPS]
        rows = {}
        for cat in m.columns:
            idx = m.index[m[cat].values]
            if len(idx) >= 5:
                rows[f"{cat} (n={len(idx)})"] = qps.loc[idx].mean().rename(QP_NOMES)
        Figuras.heatmap(pd.DataFrame(rows).T, nome, titulo, fonte, cbar_label="proporção")

    cross(ctx, "contexto_x_qp", "Proporção que responde a cada QP, por contexto (contextos com ≥5 artigos)", FM)
    cross(pop, "populacao_x_qp", "Proporção que responde a cada QP, por população (≥5 artigos)", FM)
    morf = pd.get_dummies(rob.morfologia).astype(bool)
    cross(morf, "morfologia_x_qp", "Proporção que responde a cada QP, por morfologia do robô principal",
          "dicionário de robôs + marcação humana")

    pc = pd.DataFrame({c: [int((pop[p] & ctx[c]).sum()) for p in pop.columns] for c in ctx.columns},
                      index=pop.columns)
    pc = pc.loc[pc.sum(axis=1) > 0, pc.sum() > 0]
    Figuras.heatmap(pc, "populacao_x_contexto", "População × contexto (nº de artigos que mencionam os dois)", FM,
                    fmt="{:.0f}", cbar_label="artigos")

    q4 = presence("mencoes_qp4_avaliacao.csv", inc.key)
    insts = ["Godspeed", "SUS (usabilidade)", "Almere", "UTAUT", "TAM", "NARS (atitudes negativas)",
             "Entrevista", "Observação / vídeo", "Fisiológico"]
    by = q4[insts].groupby(per.values, observed=True).mean()
    by.index = [f"{i} (n={c})" for i, c in per.value_counts().sort_index().items() if c]
    Figuras.heatmap(by.T, "instrumentos_por_periodo", "Instrumentos de avaliação por período de publicação",
                    FM, cbar_label="proporção dos artigos do período")

    q2 = presence("mencoes_qp2_comunicacao.csv", inc.key)
    by = q2.groupby(per.values, observed=True).mean()
    by.index = [f"{i} (n={c})" for i, c in per.value_counts().sort_index().items() if c]
    Figuras.heatmap(by.T, "comunicacao_por_periodo", "Modalidades de comunicação por período de publicação",
                    FM, cbar_label="proporção dos artigos do período")

    pd.DataFrame(Figuras.index).to_csv(FIG / "indice.csv", index=False)
    print(f"{len(Figuras.index)} figuras em {FIG}")


if __name__ == "__main__":
    main()
