"""
Etapa 07, parte 1: tabelas finais a partir do que já está salvo (sem LLM).

Fontes:
  - data/artefato/triagem_data.json        artigos de texto completo de todas as rodadas, trechos do RAG por QP
  - data/artefato/decisions/*.json         decisões humanas do artefato (rodadas 1 a 7)
  - results/rounds/r0/decisions.csv        decisões do start set (rodada 0)
  - results/rounds/r1/decisions.csv        código de critério que faltou no artefato (1 caso da rodada 1)
  - data/rounds/r*/, data/rodada*/         contagens do funil (coleta, título, abstract, cluster)
  - OpenAlex (cache em results/final/dados/openalex_includes.json): veículo, autores, países, tópicos, citações

  uv run --extra analysis python scripts/final/dados.py

Grava em results/final/dados/ (CSVs) e results/final/tabela_final.xlsx.
"""
import csv
import glob
import json
import time
from pathlib import Path

import pandas as pd

from sar_review_pipeline.snowball.openalex import OpenAlexClient

OUT = Path("results/final")
DADOS = OUT / "dados"
QPS = ["QP1", "QP2", "QP3", "QP4"]
OA_SELECT = ("id,doi,publication_date,type,primary_location,authorships,primary_topic,topics,keywords,"
             "cited_by_count,open_access,language")


class Decisoes:
    """Decisão final de cada artigo que chegou ao texto completo (rodadas 0 a 7)."""

    @classmethod
    def csv_rounds(cls, path: str) -> dict[str, dict]:
        rows = {}
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows[row["id"].rsplit("/", 1)[-1]] = row
        return rows

    @classmethod
    def code_from_reason(cls, reason: str) -> str:
        head = reason.split(":", 1)[0].strip()
        if head[:2] in ("EC", "IC") and len(head) <= 4:
            return head
        return ""

    @classmethod
    def load(cls) -> pd.DataFrame:
        data = json.load(open("data/artefato/triagem_data.json", encoding="utf-8"))
        db = {}
        for f in glob.glob("data/artefato/decisions/*.json"):
            j = json.load(open(f, encoding="utf-8"))
            db[j["key"]] = j
        r0 = cls.csv_rounds("results/rounds/r0/decisions.csv")
        r1 = cls.csv_rounds("results/rounds/r1/decisions.csv")

        rows = []
        for p in data["papers"]:
            key = p["key"]
            row = {"key": key, "rodada": p["round"], "titulo": p["title"], "doi": p["doi"], "ano": p["year"],
                   "direcao": p["direction"], "tipo": p["type"], "n_autores": p["n_authors"],
                   "autores_3": "; ".join(p["authors"]), "texto": p["text_status"], "abstract": p["abstract"]}
            if p["round"] == 0:
                src = r0[key]
                for qp in QPS:
                    row[qp] = src[qp.lower()] == "sim"
                row["decisao"] = src["decision"]
                row["codigo"] = cls.code_from_reason(src["reason"]) if src["decision"] != "include" else ""
                row["motivo"] = src["reason"]
                row["fonte_decisao"] = "results/rounds/r0/decisions.csv"
            elif key in db:
                j = db[key]
                for qp in QPS:
                    row[qp] = bool(j["qp"].get(qp))
                decision = j["decision"]
                if decision == "" and any(j["qp"].values()):
                    decision = "include"
                row["decisao"] = decision
                row["codigo"] = j["code"]
                if decision == "seed_only" and not row["codigo"]:
                    row["codigo"] = "EC4"
                if decision == "exclude" and not row["codigo"] and key in r1:
                    row["codigo"] = cls.code_from_reason(r1[key]["reason"])
                row["motivo"] = j["reason"]
                row["fonte_decisao"] = "artefato (banco decisions)"
            elif p["locked"]:
                for qp in QPS:
                    row[qp] = False
                row["decisao"] = "exclude"
                row["codigo"] = "EC6"
                row["motivo"] = p["locked_reason"]
                row["fonte_decisao"] = "artefato (travado, EC6)"
            else:
                raise SystemExit(f"sem decisão: {key}")
            row["rec_llm_decisao"] = (p.get("rec") or {}).get("decision", "")
            row["rec_llm_justificativa"] = (p.get("rec") or {}).get("why", "")
            rows.append(row)
        return pd.DataFrame(rows)


class Evidencias:
    """Os 3 trechos do RAG por QP (os mesmos mostrados no artefato)."""

    @classmethod
    def load(cls, keys: set[str]) -> pd.DataFrame:
        data = json.load(open("data/artefato/triagem_data.json", encoding="utf-8"))
        rows = []
        for p in data["papers"]:
            if p["key"] not in keys or not p["evidence"]:
                continue
            for qp in QPS:
                for rank, e in enumerate(p["evidence"].get(qp) or [], 1):
                    rows.append({"key": p["key"], "QP": qp, "rank": rank, "cos": e["cos"], "secao": e["section"],
                                 "paginas": e["pages"], "trecho": e["text"]})
        return pd.DataFrame(rows)


class Funil:
    """Contagens de cada etapa por rodada (identificação → título → abstract/cluster → texto completo)."""

    @classmethod
    def lines(cls, path: str) -> list[dict]:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    @classmethod
    def early(cls, n: int) -> dict:
        if n == 0:
            return {"coletados": 16, "backward": 0, "forward": 0, "both": 0, "excl_titulo": 0, "pend_titulo": 0,
                    "candidatos": 0, "sem_abstract": 0, "no_cluster": 0, "excl_cluster": 0, "k": None,
                    "clusters_mantidos": "start set"}
        if n in (1, 2):
            s = json.load(open(f"results/rounds/r{n}/summary.json", encoding="utf-8"))
            fl, cl = s["fluxo"], s["clustering"]
            kept = [c for c, v in cl["clusters"].items() if v["decisao"] == "mantido"]
            return {"coletados": fl["works_novos_coletados"], "backward": fl["por_direcao"].get("backward", 0),
                    "forward": fl["por_direcao"].get("forward", 0), "both": fl["por_direcao"].get("both", 0),
                    "excl_titulo": fl["excluidos_titulo"], "pend_titulo": 0, "candidatos": fl["candidatos_titulo"],
                    "sem_abstract": fl["excluidos_sem_abstract"], "no_cluster": fl["no_clustering"],
                    "excl_cluster": fl["excluidos_cluster"], "k": cl["k"], "clusters_mantidos": ", ".join(kept)}
        d = Path(f"data/rodada{n}")
        works = cls.lines(d / "works.jsonl")
        status = [r["status"] for r in json.load(open(d / "title_screening.json", encoding="utf-8"))]
        cov = json.load(open(d / "abstracts_coverage_report.json", encoding="utf-8"))
        cd = json.load(open(d / "cluster_decision.json", encoding="utf-8"))
        included = len(cls.lines(d / "included.jsonl"))
        no_cluster = cov["total"] - cov["excluidos_sem_abstract"]
        directions = [w["direction"] for w in works]
        return {"coletados": len(works), "backward": directions.count("backward"),
                "forward": directions.count("forward"), "both": directions.count("both"),
                "excl_titulo": status.count("excluded_by_title"), "pend_titulo": status.count("pending_title"),
                "candidatos": cov["total"], "sem_abstract": cov["excluidos_sem_abstract"], "no_cluster": no_cluster,
                "excl_cluster": no_cluster - included, "k": cd["k"],
                "clusters_mantidos": ", ".join(cd["mantidos"]) or "nenhum"}

    @classmethod
    def build(cls, dec: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for n in range(0, 9):
            row = {"rodada": n, **cls.early(n)}
            sub = dec[dec.rodada == n]
            row["texto_completo_avaliados"] = len(sub)
            row["ec6_sem_texto"] = int((sub.codigo == "EC6").sum())
            row["lidos"] = len(sub) - row["ec6_sem_texto"]
            row["include"] = int((sub.decisao == "include").sum())
            row["seed_only_EC4"] = int((sub.decisao == "seed_only").sum())
            for code in ["EC1", "EC2", "EC3", "EC5", "EC7", "IC6"]:
                row[code] = int(((sub.decisao == "exclude") & (sub.codigo == code)).sum())
            rows.append(row)
        df = pd.DataFrame(rows)
        df["seeds_proxima"] = df.include + df.seed_only_EC4
        return df


class OpenAlexMeta:
    """Metadados do OpenAlex dos includes (cache local; só ids públicos vão para a API)."""

    CACHE = DADOS / "openalex_includes.json"

    @classmethod
    def fetch(cls, keys: list[str]) -> dict[str, dict]:
        cache = json.load(open(cls.CACHE, encoding="utf-8")) if cls.CACHE.exists() else {}
        missing = [k for k in keys if k not in cache]
        client = OpenAlexClient()
        for i in range(0, len(missing), 50):
            chunk = "|".join(missing[i : i + 50])
            for raw in client.get(f"openalex:{chunk}", per_page=50, select=OA_SELECT):
                cache[raw["id"].rsplit("/", 1)[-1]] = raw
            time.sleep(0.2)
        json.dump(cache, open(cls.CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        return cache

    @classmethod
    def tables(cls, meta: dict[str, dict]) -> dict[str, pd.DataFrame]:
        works, authors, topics, keywords = [], [], [], []
        for key, raw in meta.items():
            loc = raw.get("primary_location") or {}
            source = loc.get("source") or {}
            countries = set()
            for pos, a in enumerate(raw.get("authorships") or []):
                for inst in a.get("institutions") or []:
                    authors.append({"key": key, "posicao": pos, "autor": (a.get("author") or {}).get("display_name"),
                                    "instituicao": inst.get("display_name"), "pais": inst.get("country_code"),
                                    "tipo_instituicao": inst.get("type")})
                for c in a.get("countries") or []:
                    countries.add(c)
                if not a.get("institutions"):
                    authors.append({"key": key, "posicao": pos, "autor": (a.get("author") or {}).get("display_name"),
                                    "instituicao": None, "pais": None, "tipo_instituicao": None})
            pt = raw.get("primary_topic") or {}
            works.append({"key": key, "veiculo": source.get("display_name"), "tipo_veiculo": source.get("type"),
                          "editora": source.get("host_organization_name"), "data_publicacao": raw.get("publication_date"),
                          "citacoes": raw.get("cited_by_count"), "acesso_aberto": (raw.get("open_access") or {}).get("is_oa"),
                          "oa_status": (raw.get("open_access") or {}).get("oa_status"), "idioma": raw.get("language"),
                          "paises": "; ".join(sorted(countries)), "n_paises": len(countries),
                          "topico": pt.get("display_name"), "subcampo": (pt.get("subfield") or {}).get("display_name"),
                          "campo": (pt.get("field") or {}).get("display_name"),
                          "dominio": (pt.get("domain") or {}).get("display_name")})
            for t in raw.get("topics") or []:
                topics.append({"key": key, "topico": t.get("display_name"), "score": t.get("score"),
                               "subcampo": (t.get("subfield") or {}).get("display_name"),
                               "campo": (t.get("field") or {}).get("display_name")})
            for kw in raw.get("keywords") or []:
                keywords.append({"key": key, "keyword": kw.get("display_name"), "score": kw.get("score")})
        return {"openalex": pd.DataFrame(works), "autores_instituicoes": pd.DataFrame(authors),
                "topicos": pd.DataFrame(topics), "keywords": pd.DataFrame(keywords)}


def main():
    DADOS.mkdir(parents=True, exist_ok=True)
    dec = Decisoes.load()
    dec.drop(columns=["abstract"]).to_csv(DADOS / "texto_completo_decisoes.csv", index=False)

    inc = dec[dec.decisao == "include"].copy()
    inc["n_qps"] = inc[QPS].sum(axis=1)
    inc["combinacao_qps"] = inc[QPS].apply(lambda r: "+".join(q for q in QPS if r[q]) or "nenhuma", axis=1)

    meta = OpenAlexMeta.fetch(inc.key.tolist())
    oa = OpenAlexMeta.tables({k: meta[k] for k in inc.key if k in meta})
    inc = inc.merge(oa["openalex"], on="key", how="left")
    inc.to_csv(DADOS / "includes.csv", index=False)
    for name, df in oa.items():
        if name != "openalex":
            df.to_csv(DADOS / f"{name}.csv", index=False)

    ev = Evidencias.load(set(inc.key))
    marked = inc.set_index("key")[QPS]
    ev["qp_marcada_revisor"] = [bool(marked.loc[k, q]) for k, q in zip(ev.key, ev.QP)]
    ev.to_csv(DADOS / "evidencias_rag.csv", index=False)

    funil = Funil.build(dec)
    funil.to_csv(DADOS / "funil_rodadas.csv", index=False)

    long = []
    for _, r in inc.iterrows():
        for qp in QPS:
            sub = ev[(ev.key == r.key) & (ev.QP == qp)].sort_values("rank")
            long.append({"Artigo": r.titulo, "key": r.key, "rodada": r.rodada, "ano": r.ano, "QP": qp,
                         "Responde (revisor)": "sim" if r[qp] else "não",
                         "Trecho_1": sub.trecho.iloc[0] if len(sub) > 0 else "",
                         "Secao_1": sub.secao.iloc[0] if len(sub) > 0 else "",
                         "Paginas_1": sub.paginas.iloc[0] if len(sub) > 0 else "",
                         "cos_1": sub.cos.iloc[0] if len(sub) > 0 else None,
                         "Trecho_2": sub.trecho.iloc[1] if len(sub) > 1 else "",
                         "Trecho_3": sub.trecho.iloc[2] if len(sub) > 2 else "",
                         "Fonte": "marcação humana no artefato; trechos do RAG (Qwen3-Embedding)"})
    long = pd.DataFrame(long)
    long.to_csv(DADOS / "extracao_QP1-QP4.csv", index=False)

    with pd.ExcelWriter(OUT / "tabela_final.xlsx") as xw:
        cols = ["key", "rodada", "direcao", "ano", "titulo", "doi", "tipo", "veiculo", "editora", "paises",
                "citacoes", "acesso_aberto", *QPS, "n_qps", "combinacao_qps", "topico", "campo"]
        inc[cols].to_excel(xw, sheet_name="includes", index=False)
        long.to_excel(xw, sheet_name="extracao_QP1-QP4", index=False)
        funil.to_excel(xw, sheet_name="funil_rodadas", index=False)
        dec.drop(columns=["abstract"]).to_excel(xw, sheet_name="texto_completo_todos", index=False)
    print(f"texto completo: {len(dec)}; includes: {len(inc)}; trechos: {len(ev)}; openalex: {len(oa['openalex'])}")
    print(funil[["rodada", "coletados", "candidatos", "texto_completo_avaliados", "include", "seed_only_EC4"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
