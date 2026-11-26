"""
Etapa 07, parte 4: fluxograma PRISMA 2020 final (start set + snowballing, rodadas 0 a 8) e tabela por rodada.

  uv run --extra analysis python scripts/final/prisma.py

Lê results/final/dados/funil_rodadas.csv e grava results/final/prisma/prisma_final.{png,svg},
prisma_por_rodada.{png,svg} e prisma_contagens.json.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch

DADOS = Path("results/final/dados")
OUT = Path("results/final/prisma")
INK, INK2, EDGE = "#0b0b0b", "#52514e", "#8a8984"
BLUE_BG, GREY_BG, GREEN_BG = "#e8f1fc", "#f4f3f0", "#e3f5ec"
CODES = {"EC1": "robô sem componente social/assistivo", "EC2": "puramente técnico", "EC3": "sem característica para as QPs",
         "EC5": "resumo/pôster/conteúdo insuficiente", "EC7": "duplicata", "IC6": "não revisado por pares"}


class Contagens:
    @classmethod
    def build(cls, f: pd.DataFrame) -> dict:
        snow = f[f.rodada >= 1]
        c = {
            "start_set": int(f.loc[f.rodada == 0, "coletados"].iloc[0]),
            "rodadas": int(f.rodada.max()),
            "snow_coletados": int(snow.coletados.sum()),
            "snow_backward": int(snow.backward.sum()), "snow_forward": int(snow.forward.sum()),
            "snow_both": int(snow.both.sum()),
            "excl_titulo": int(snow.excl_titulo.sum()), "pend_titulo": int(snow.pend_titulo.sum()),
            "candidatos": int(snow.candidatos.sum()), "sem_abstract": int(snow.sem_abstract.sum()),
            "no_cluster": int(snow.no_cluster.sum()), "excl_cluster": int(snow.excl_cluster.sum()),
            "texto_buscado": int(f.texto_completo_avaliados.sum()), "ec6": int(f.ec6_sem_texto.sum()),
            "lidos": int(f.lidos.sum()), "seed_only": int(f.seed_only_EC4.sum()), "include": int(f.include.sum()),
            "por_codigo": {code: int(f[code].sum()) for code in CODES},
        }
        c["excl_texto"] = sum(c["por_codigo"].values())
        assert c["lidos"] == c["include"] + c["seed_only"] + c["excl_texto"], "funil não fecha no texto completo"
        assert c["snow_coletados"] == c["excl_titulo"] + c["pend_titulo"] + c["candidatos"]
        assert c["texto_buscado"] - c["start_set"] == c["no_cluster"] - c["excl_cluster"]
        return c


class Fluxo:
    W, H = 10.0, 12.6

    def __init__(self):
        self.fig, self.ax = plt.subplots(figsize=(self.W, self.H))
        self.ax.set_xlim(0, self.W)
        self.ax.set_ylim(0, self.H)
        self.ax.axis("off")

    def box(self, x, y, w, h, text, bg=GREY_BG, bold=False, size=8.5):
        self.ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                         fc=bg, ec=EDGE, lw=0.9))
        self.ax.text(x + 0.15, y + h / 2, text, ha="left", va="center", fontsize=size, color=INK,
                     fontweight="bold" if bold else "normal", linespacing=1.35)

    def arrow(self, x1, y1, x2, y2):
        self.ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                         arrowprops=dict(arrowstyle="-|>", color=INK2, lw=1, shrinkA=0, shrinkB=0))

    def band(self, y, h, label):
        self.ax.add_patch(FancyBboxPatch((0.05, y), 0.35, h, boxstyle="round,pad=0.01,rounding_size=0.08",
                                         fc="#2a78d6", ec="none"))
        self.ax.text(0.225, y + h / 2, label, rotation=90, ha="center", va="center", color="white",
                     fontsize=9, fontweight="bold")

    def draw(self, c: dict) -> None:
        L, R, LW, RW = 0.6, 6.0, 5.0, 3.9
        self.ax.text(0.05, self.H - 0.25, "PRISMA 2020 — busca por snowballing (Wohlin), rodadas 0 a "
                     f"{c['rodadas']}", fontsize=12, fontweight="bold", color=INK, va="top")

        y = 10.3
        self.band(y - 0.15, 1.65, "Identificação")
        self.box(L, y + 0.75, 2.35, 0.7, f"Start set\n(n = {c['start_set']})", BLUE_BG, size=8.5)
        self.box(L + 2.5, y + 0.75, 2.5, 0.7, f"Snowballing (rodadas 1–{c['rodadas']})\n"
                 f"registros novos (n = {c['snow_coletados']})", BLUE_BG, size=8.5)
        self.box(R, y, RW, 1.45,
                 f"Por direção (rodadas 1–{c['rodadas']}):\n  backward (referências): {c['snow_backward']}\n"
                 f"  forward (citações): {c['snow_forward']}\n  ambas: {c['snow_both']}\n"
                 "Duplicatas e já vistos removidos na coleta\n(EC7/EC8, por ID OpenAlex e DOI)", size=7.8)
        self.arrow(L + 3.75, y + 0.75, L + 3.75, 9.0)

        y = 8.15
        self.band(y - 1.95, 2.95, "Triagem")
        self.box(L + 2.5, y, 2.5, 0.85, f"Títulos triados\n(n = {c['snow_coletados']})")
        self.box(R, y, RW, 0.85, f"Excluídos pelo título (n = {c['excl_titulo'] + c['pend_titulo']})"
                 + (f"\n  inclui {c['pend_titulo']} sem triagem concluída" if c["pend_titulo"] else ""), size=8)
        self.arrow(L + 5.0, y + 0.42, R, y + 0.42)
        self.arrow(L + 3.75, y, L + 3.75, y - 0.55)

        y = 6.75
        self.box(L + 2.5, y, 2.5, 0.85, f"Abstracts avaliados\n(n = {c['candidatos']})")
        self.box(R, y, RW, 0.85, f"Sem abstract (n = {c['sem_abstract']})", size=8)
        self.arrow(L + 5.0, y + 0.42, R, y + 0.42)
        self.arrow(L + 3.75, y, L + 3.75, y - 0.55)

        y = 5.35
        self.box(L + 2.5, y, 2.5, 0.85, f"Agrupados por tema\n(mpnet + KMeans, n = {c['no_cluster']})")
        self.box(R, y, RW, 0.85, f"Em clusters não mantidos\npelo revisor (n = {c['excl_cluster']})", size=8)
        self.arrow(L + 5.0, y + 0.42, R, y + 0.42)
        self.arrow(L + 3.75, y, L + 3.75, 4.6)
        self.arrow(L + 1.175, 10.3 + 0.75, L + 1.175, 4.6)

        y = 3.8
        self.band(1.55, 3.25, "Elegibilidade")
        self.box(L, y, 5.0, 0.8, f"Textos completos buscados (n = {c['texto_buscado']})\n"
                 f"start set {c['start_set']} + snowballing {c['texto_buscado'] - c['start_set']}")
        self.box(R, y, RW, 0.8, f"Não recuperados — EC6 (n = {c['ec6']})\n(download automático + busca\n"
                 "manual UFLA/Portal CAPES)", size=7.8)
        self.arrow(L + 5.0, y + 0.4, R, y + 0.4)
        self.arrow(L + 2.5, y, L + 2.5, y - 0.6)

        y = 1.55
        excl = "\n".join(f"  {code} {CODES[code]}: {n}" for code, n in c["por_codigo"].items() if n)
        self.box(L, y + 0.85, 5.0, 0.8, f"Textos completos lidos\n(n = {c['lidos']})")
        self.box(R, y - 0.45, RW, 2.1, f"Excluídos (n = {c['excl_texto']}):\n{excl}\n"
                 f"Revisões/estudos secundários — EC4\n  (só sementes) (n = {c['seed_only']})", size=7.6)
        self.arrow(L + 5.0, y + 1.25, R, y + 1.25)
        self.arrow(L + 2.5, y + 0.85, L + 2.5, 0.95)

        self.band(0.15, 0.95, "Incluídos")
        self.box(L, 0.2, 5.0, 0.75, f"Estudos incluídos na síntese (n = {c['include']})", GREEN_BG, bold=True,
                 size=9.5)

    def save(self, stem: Path) -> None:
        self.fig.savefig(stem.with_suffix(".png"), dpi=300, bbox_inches="tight")
        self.fig.savefig(stem.with_suffix(".svg"), bbox_inches="tight")
        plt.close(self.fig)


class TabelaRodadas:
    COLS = [("coletados", "Coletados"), ("excl_titulo", "Excl.\ntítulo"), ("candidatos", "Abstracts"),
            ("sem_abstract", "Sem\nabstract"), ("no_cluster", "Clustering"), ("k", "K"),
            ("clusters_mantidos", "Clusters\nmantidos"), ("excl_cluster", "Excl.\ncluster"),
            ("texto_completo_avaliados", "Texto\nbuscado"), ("ec6_sem_texto", "EC6"), ("lidos", "Lidos"),
            ("excl_texto", "Excl.\ntexto"), ("seed_only_EC4", "EC4\n(semente)"), ("include", "Incluídos")]

    @classmethod
    def draw(cls, f: pd.DataFrame, stem: Path) -> None:
        f = f.copy()
        f["excl_texto"] = f[list(CODES)].sum(axis=1)
        f["k"] = f.k.apply(lambda v: "" if pd.isna(v) else str(int(v)))
        total = {col: (str(int(f[col].sum())) if col not in ("k", "clusters_mantidos") else "") for col, _ in cls.COLS}
        rows = [[str(r[col]) for col, _ in cls.COLS] for _, r in f.iterrows()]
        rows.append([total[col] for col, _ in cls.COLS])
        labels = [f"Rodada {n}" for n in f.rodada] + ["Total"]
        fig, ax = plt.subplots(figsize=(13, 0.36 * len(rows) + 1.2))
        ax.axis("off")
        t = ax.table(cellText=rows, rowLabels=labels, colLabels=[lab for _, lab in cls.COLS], loc="center",
                     cellLoc="center")
        t.auto_set_font_size(False)
        t.set_fontsize(8)
        t.scale(1, 1.35)
        for (i, j), cell in t.get_celld().items():
            cell.set_edgecolor("#e4e3df")
            if i == 0:
                cell.set_height(cell.get_height() * 1.8)
                cell.set_facecolor(BLUE_BG)
                cell.set_text_props(fontweight="bold")
            if i == len(rows):
                cell.set_text_props(fontweight="bold")
            if j == len(cls.COLS) - 1 and i > 0:
                cell.set_facecolor(GREEN_BG)
        ax.set_title("Snowballing por rodada (rodada 0 = start set; rodada 8 sem clusters mantidos → convergiu)",
                     loc="left", fontsize=10, fontweight="bold", color=INK)
        fig.savefig(stem.with_suffix(".png"), dpi=300, bbox_inches="tight")
        fig.savefig(stem.with_suffix(".svg"), bbox_inches="tight")
        plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    f = pd.read_csv(DADOS / "funil_rodadas.csv")
    c = Contagens.build(f)
    json.dump(c, open(OUT / "prisma_contagens.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    fluxo = Fluxo()
    fluxo.draw(c)
    fluxo.save(OUT / "prisma_final")
    TabelaRodadas.draw(f, OUT / "prisma_por_rodada")
    print(json.dumps(c, ensure_ascii=False))


if __name__ == "__main__":
    main()
