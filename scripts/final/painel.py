"""
Etapa 07, parte 5: CSVs enxutos para o painel interativo (artefato "Síntese SAR em Saúde").

  uv run --extra analysis python scripts/final/painel.py

Grava results/final/painel/{includes,funil,decisoes,mencoes,evidencias}.csv a partir de results/final/dados/.
"""
from pathlib import Path

import pandas as pd

DADOS = Path("results/final/dados")
OUT = Path("results/final/painel")
QPS = ["QP1", "QP2", "QP3", "QP4"]
MIN_HITS = 2
GRUPOS = {"contexto": "Contexto", "populacao": "População", "qp1_fisico": "QP1 físico/visual",
          "qp2_comunicacao": "QP2 comunicação", "qp3_emocao": "QP3 emoção/personalidade",
          "qp4_avaliacao": "QP4 avaliação", "desenho_estudo": "Desenho do estudo", "robos": "Robôs"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    inc = pd.read_csv(DADOS / "includes.csv")
    rob = pd.read_csv(DADOS / "robo_principal.csv")
    dom = pd.read_csv(DADOS / "dominante_contexto_populacao.csv").pivot(index="key", columns="grupo",
                                                                        values="dominante")
    am = pd.read_csv(DADOS / "amostra_auto.csv")
    df = (inc.merge(rob[["key", "robo_principal", "morfologia"]], on="key")
          .merge(dom.rename(columns={"contexto": "contexto_dominante", "populacao": "populacao_dominante"}),
                 left_on="key", right_index=True)
          .merge(am[["key", "n_participantes_auto"]], on="key"))
    df["ano"] = df.ano.astype("Int64")
    df["n_participantes_auto"] = df.n_participantes_auto.astype("Int64")
    for q in QPS:
        df[q] = df[q].map({True: "sim", False: "não"})
    cols = ["key", "rodada", "direcao", "ano", "titulo", "doi", "tipo", "veiculo", "paises", "citacoes", *QPS,
            "n_qps", "combinacao_qps", "robo_principal", "morfologia", "contexto_dominante", "populacao_dominante",
            "n_participantes_auto"]
    df[cols].to_csv(OUT / "includes.csv", index=False)

    pd.read_csv(DADOS / "funil_rodadas.csv").to_csv(OUT / "funil.csv", index=False)
    dec = pd.read_csv(DADOS / "texto_completo_decisoes.csv")
    dec[["key", "rodada", "decisao", "codigo", "texto"]].fillna("").to_csv(OUT / "decisoes.csv", index=False)

    rows = []
    for grupo, nome in GRUPOS.items():
        m = pd.read_csv(DADOS / f"mencoes_{grupo}.csv").set_index("key")
        for key, r in m.iterrows():
            for cat, n in r.items():
                if n >= MIN_HITS:
                    rows.append({"key": key, "grupo": nome, "categoria": cat, "mencoes": int(n)})
    pd.DataFrame(rows).to_csv(OUT / "mencoes.csv", index=False)

    ev = pd.read_csv(DADOS / "evidencias_rag.csv")
    ev = ev[ev["rank"] == 1][["key", "QP", "cos", "secao", "paginas", "trecho", "qp_marcada_revisor"]]
    ev["qp_marcada_revisor"] = ev.qp_marcada_revisor.map({True: "sim", False: "não"})
    ev.to_csv(OUT / "evidencias.csv", index=False)
    for f in sorted(OUT.glob("*.csv")):
        print(f, f.stat().st_size // 1024, "KB", sum(1 for _ in open(f)) - 1, "linhas")


if __name__ == "__main__":
    main()
