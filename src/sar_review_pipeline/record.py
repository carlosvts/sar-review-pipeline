"""
    Registro versionado de uma rodada (results/rounds/r<N>/), para o PRISMA e para a auditoria.
    data/ fica fora do git; aqui fica, no git, tudo o que justifica cada decisão da rodada:

      ledger.csv     uma linha por work coletado na rodada: em que etapa saiu e por quê
      summary.json   números do fluxo (PRISMA), o clustering (modelo, K escolhido, inércia e silhouette
                     do K, clusters excluídos com tema e tamanho) e o texto completo
      sweep.csv, elbow.png, silhouette.png, umap_k<K>.png, assignments_k<K>.csv   do clustering
      decisions.csv  a decisão do texto completo (QPs, include/seed_only/exclude, código IC/EC)

    uv run record-round --round N   (pode ser rodado de novo a qualquer momento: reescreve o registro
    com o estado atual; etapas ainda não feitas aparecem como pendentes)
"""
import csv
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

from sar_review_pipeline.rounds import Round, pop_round

RESULTS = Path("results/rounds")

LEDGER_FIELDS = [
    "id", "doi", "title", "publication_year", "round", "direction",
    "stage", "outcome", "reason",
    "title_status", "title_rule", "title_keyword",
    "abstract_status", "abstract_source",
    "cluster", "cluster_theme",
    "text_status", "qp1", "qp2", "qp3", "qp4", "qp5", "fulltext_decision", "fulltext_reason",
]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cluster_record(rnd: Round) -> tuple[dict, dict[str, int]]:
    """Decisão de cluster da rodada (com o K, a inércia e a silhouette do K escolhido) e id -> cluster."""
    from sar_review_pipeline.abstracts.include import DECISIONS

    decision = DECISIONS.get(rnd.n)
    if decision is None:
        return {"decidido": False}, {}
    assignments = {r["id"]: int(r["cluster"]) for r in read_csv(decision.assignments(rnd))}
    sweep = read_csv(decision.assignments(rnd).parent / "sweep.csv")
    chosen = next((r for r in sweep if int(r["k"]) == decision.k), None)
    sizes = Counter(assignments.values())
    return {
        "decidido": True,
        "modelo": decision.model,
        "metrica": decision.metric,
        "k": decision.k,
        "motivo_do_k": decision.k_rationale,
        "inercia_do_k": float(chosen["inertia"]) if chosen else None,
        "silhouette_do_k": float(chosen["silhouette"]) if chosen else None,
        "maior_silhouette_a_partir_de_k4": max(
            ({"k": int(r["k"]), "silhouette": float(r["silhouette"])} for r in sweep if int(r["k"]) >= 4),
            key=lambda r: r["silhouette"], default=None,
        ),
        "assignments": str(decision.assignments(rnd)),
        "clusters": {
            str(c): {"artigos": sizes[c], "decisao": "excluido" if c in decision.excluded else "mantido",
                     "tema": decision.excluded.get(c) or decision.kept.get(c, "")}
            for c in sorted(sizes)
        },
    }, assignments


def build_ledger(rnd: Round, cluster: dict, assignments: dict[str, int]) -> list[dict]:
    works = read_jsonl(rnd.works)
    screening = {r["id"]: r for r in read_jsonl(rnd.title_screening_jsonl)}
    abstracts = {r["id"]: r for r in read_jsonl(rnd.candidates_abstracts)}
    decisions = {r["id"]: r for r in read_csv(rnd.decisions)}
    themes = {int(c): v["tema"] for c, v in cluster.get("clusters", {}).items()}
    excluded_clusters = {int(c) for c, v in cluster.get("clusters", {}).items() if v["decisao"] == "excluido"}
    rows = []
    for w in works:
        i = w["id"]
        s, a, d = screening.get(i, {}), abstracts.get(i, {}), decisions.get(i, {})
        c = assignments.get(i)
        row = {
            "id": i, "doi": w.get("doi") or "", "title": w.get("title") or "", "publication_year": w.get("publication_year") or "",
            "round": w.get("round"), "direction": w.get("direction"),
            "title_status": s.get("status", ""), "title_rule": s.get("matched_rule", ""), "title_keyword": s.get("matched_keyword", ""),
            "abstract_status": a.get("abstract_status", ""), "abstract_source": a.get("abstract_source") or "",
            "cluster": "" if c is None else c, "cluster_theme": themes.get(c, "") if c is not None else "",
            "text_status": d.get("text_status", ""),
            **{f"qp{k}": d.get(f"qp{k}", "") for k in range(1, 6)},
            "fulltext_decision": d.get("decision", ""), "fulltext_reason": d.get("reason", ""),
        }
        if rnd.n == 0:
            stage, outcome, reason = "start_set", "", ""
        elif s.get("status") in ("excluded_by_title", "pending_title", "pending_rules") or not s:
            stage, outcome = "titulo", "excluido"
            reason = {"excluded_by_title": "título sem termo das regras de inclusão",
                      "pending_title": "sem título no registro"}.get(s.get("status"), "sem triagem por título")
        elif not a:
            stage, outcome, reason = "abstract", "pendente", "abstracts ainda não recuperados"
        elif a.get("exclusion_reason"):
            stage, outcome, reason = "abstract", "excluido", f"{a['exclusion_reason']} (needs_context sem abstract válido)"
        elif not cluster.get("decidido"):
            stage, outcome, reason = "cluster", "pendente", "decisão de cluster pendente"
        elif c is None:
            stage, outcome, reason = "cluster", "excluido", "fora das atribuições do clustering"
        elif c in excluded_clusters:
            stage, outcome, reason = "cluster", "excluido", f"cluster {c}: {themes.get(c, '')}"
        else:
            stage, outcome, reason = "texto_completo", "pendente", "decisão do texto completo pendente"
        if stage in ("texto_completo", "start_set") and d.get("decision"):
            stage = "texto_completo"
            outcome = {"include": "incluido", "seed_only": "seed_only", "exclude": "excluido"}[d["decision"]]
            reason = d.get("reason", "")
        row.update(stage=stage, outcome=outcome, reason=reason)
        rows.append(row)
    return rows


def flow(rows: list[dict], rnd: Round) -> dict:
    by = Counter((r["stage"], r["outcome"]) for r in rows)
    seeds_prev = read_jsonl(Round(rnd.n - 1).selected) if rnd.n >= 1 else []
    return {
        "seeds_da_rodada": len(seeds_prev),
        "works_novos_coletados": len(rows),
        "por_direcao": dict(Counter(r["direction"] for r in rows)),
        "excluidos_titulo": by[("titulo", "excluido")],
        "candidatos_titulo": sum(1 for r in rows if r["title_status"] in ("passed_title", "needs_context")),
        "excluidos_sem_abstract": by[("abstract", "excluido")],
        "no_clustering": sum(1 for r in rows if r["cluster"] != ""),
        "excluidos_cluster": by[("cluster", "excluido")],
        "texto_completo_avaliados": sum(1 for r in rows if r["stage"] == "texto_completo"),
        "texto_completo": {
            "incluidos_sintese": by[("texto_completo", "incluido")],
            "seed_only_EC4": by[("texto_completo", "seed_only")],
            "excluidos": by[("texto_completo", "excluido")],
            "excluidos_por_codigo": dict(Counter(
                (re.search(r"\bEC\d+\b", r["fulltext_reason"]) or [""])[0] for r in rows if r["fulltext_decision"] == "exclude")),
            "pendentes": by[("texto_completo", "pendente")],
        },
        "seeds_para_proxima_rodada": len(read_jsonl(rnd.selected)) if rnd.n >= 1 and rnd.selected.exists() else None,
        "pendentes": sum(v for (st, o), v in by.items() if o == "pendente"),
    }


def main():
    rnd, _ = pop_round(sys.argv[1:])
    if not rnd.works.exists():
        sys.exit(f"{rnd.works} não existe: a rodada {rnd.n} ainda não foi coletada")
    out = RESULTS / f"r{rnd.n}"
    out.mkdir(parents=True, exist_ok=True)
    cluster, assignments = cluster_record(rnd) if rnd.n >= 1 else ({"decidido": False, "nota": "start set: sem clustering"}, {})
    rows = build_ledger(rnd, cluster, assignments)
    with open(out / "ledger.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    summary = {"rodada": rnd.n, "fluxo": flow(rows, rnd), "clustering": cluster}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    copies = [rnd.decisions]
    if cluster.get("decidido"):
        cdir = Path(cluster["assignments"]).parent
        copies += [cdir / "sweep.csv", cdir / "elbow.png", cdir / "silhouette.png",
                   cdir / f"umap_k{cluster['k']}.png", Path(cluster["assignments"])]
    elif rnd.n >= 1:
        # antes da decisão, guarda pelo menos as varreduras feitas
        copies += sorted(rnd.cluster_dir.glob("*/*/sweep.csv"))
    for src in copies:
        if not src.exists():
            continue
        # varreduras de antes da decisão levam o modelo no nome (pode haver mais de uma)
        name = f"{src.parent.parent.name}_{src.name}" if not cluster.get("decidido") and src.name == "sweep.csv" else src.name
        shutil.copyfile(src, out / name)

    f = summary["fluxo"]
    print(f"{rnd.name}: {f['works_novos_coletados']} works no ledger | título excluiu {f['excluidos_titulo']}"
          f" | sem abstract {f['excluidos_sem_abstract']} | cluster excluiu {f['excluidos_cluster']}"
          f" | texto completo {f['texto_completo']} | pendentes {f['pendentes']}")
    if cluster.get("decidido"):
        print(f"clustering: {cluster['modelo']} K={cluster['k']} silhouette={cluster['silhouette_do_k']:.4f}"
              f" inércia={cluster['inercia_do_k']:.2f}")
    print(f"Registro: {out.resolve()}")


if __name__ == "__main__":
    main()
