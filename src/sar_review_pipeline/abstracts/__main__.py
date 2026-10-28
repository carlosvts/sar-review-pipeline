import json
import sys

import numpy as np

from sar_review_pipeline.abstracts.stage import AbstractStage

SUMMARY_KEYS = (
    "total",
    "por_status",
    "por_fonte",
    "por_tipo_de_match",
    "por_status_do_titulo",
    "excluidos_sem_abstract",
    "so_titulo",
    "palavras_dos_validos",
    "rejeitados_por_fonte",
    "suspeitos_por_flag",
    "com_erro_de_api",
)


def fetch(sample_size: int | None = None) -> None:
    candidates = AbstractStage.load_candidates()
    if sample_size:
        candidates = AbstractStage.sample(candidates, sample_size)
    print(f"Candidatos: {len(candidates)}\n")

    results = AbstractStage.run(candidates)
    AbstractStage.save(results)
    report = AbstractStage.coverage_report(results)
    AbstractStage.save_report(report)

    print("\n=== Cobertura ===")
    for key in SUMMARY_KEYS:
        print(f"{key}: {json.dumps(report[key], ensure_ascii=False)}")
    print(f"\nSaída: {AbstractStage.OUTPUT_PATH.resolve()}")
    print(f"Relatório (com suspeitos, rejeitados e erros): {AbstractStage.REPORT_PATH.resolve()}")


def embed_candidates(model_key: str):
    # import aqui: o clustering só existe no ambiente do extra do modelo (cluster-specter ou cluster-sentence-transformers)
    from sar_review_pipeline.abstracts.cluster import Clusterer
    from sar_review_pipeline.abstracts.embed import PaperEmbedder

    records = Clusterer.load_records()
    embeddings = PaperEmbedder(model_key).embed_records(records)
    with_abstract, title_only = Clusterer.split_by_abstract(records)
    print(f"Registros: {len(records)}  com abstract (ajuste): {len(with_abstract)}  só título: {len(title_only)}\n")
    return records, embeddings, with_abstract, title_only


def plot_umap_for_k(records, embeddings, kmeans, layout, k: int, model_key: str, metric: str):
    from sar_review_pipeline.abstracts.cluster import Clusterer

    by_title = np.array([r["title_only"] for r in records])
    labels = kmeans.predict(embeddings)
    path = Clusterer.output_dir(model_key, metric) / f"umap_k{k}.png"
    title = f"UMAP (cosseno) dos candidatos · {model_key} · KMeans {metric} · K={k}"
    Clusterer.plot_umap(layout, labels, by_title, title, path)
    return path


def sweep(model_key: str, metric: str | None = None) -> None:
    from sar_review_pipeline.abstracts.cluster import K_MAX, K_MIN, METRIC, UMAP_KS, Clusterer

    metric = metric or METRIC
    records, embeddings, with_abstract, _ = embed_candidates(model_key)
    print(f"Varredura de K={K_MIN} a K={K_MAX} ({model_key}, {metric})")
    rows = Clusterer.sweep(embeddings[with_abstract], metric)

    out = Clusterer.output_dir(model_key, metric)
    out.mkdir(parents=True, exist_ok=True)
    Clusterer.save_sweep_csv(rows, out / "sweep.csv")
    label = f"{model_key}, {metric}"
    Clusterer.plot_metric(rows, "inertia", f"Método do cotovelo: inércia por K ({label})", "Inércia", out / "elbow.png")
    Clusterer.plot_metric(rows, "silhouette", f"Silhouette médio por K ({label})", "Silhouette", out / "silhouette.png")

    layout = Clusterer.umap_layout(embeddings, [r["id"] for r in records], model_key)
    for k in UMAP_KS:
        kmeans = Clusterer.fit(embeddings[with_abstract], k, metric)
        plot_umap_for_k(records, embeddings, kmeans, layout, k, model_key, metric)
    print(f"\nSaída (CSV, cotovelo, silhouette, UMAP de K={UMAP_KS}): {out.resolve()}")


def fit(model_key: str, k: int, metric: str | None = None) -> None:
    from sar_review_pipeline.abstracts.cluster import METRIC, Clusterer

    metric = metric or METRIC
    records, embeddings, with_abstract, title_only = embed_candidates(model_key)
    kmeans = Clusterer.fit(embeddings[with_abstract], k, metric)
    rows = Clusterer.assignments(records, embeddings, kmeans, with_abstract, title_only)
    path = Clusterer.output_dir(model_key, metric) / f"assignments_k{k}.csv"
    Clusterer.save_assignments(rows, path)
    layout = Clusterer.umap_layout(embeddings, [r["id"] for r in records], model_key)
    umap_path = plot_umap_for_k(records, embeddings, kmeans, layout, k, model_key, metric)

    print(f"K={k}  tamanho dos clusters:")
    for cluster, counts in Clusterer.cluster_sizes(rows).items():
        print(f"  {cluster:2d}: {counts['com_abstract']} com abstract + {counts['por_titulo']} por título")
    print(f"\nAtribuições: {path.resolve()}\nUMAP: {umap_path.resolve()}")


USAGE = "uso: step03-abstracts fetch [--sample N] | sweep <modelo> | fit <modelo> K"


def exit_with_usage(valid_models=None) -> None:
    """Imprime o uso (e os modelos válidos, se houver) e termina com código 2, sem rodar nada."""
    print(USAGE)
    if valid_models:
        print(f"modelos válidos: {', '.join(valid_models)}")
    sys.exit(2)


def main():
    # uv run step03-abstracts fetch [--sample N]                    -> etapa 1: abstracts
    # uv run --extra <extra> step03-abstracts sweep <modelo>        -> etapa 2: cotovelo e silhouette
    # uv run --extra <extra> step03-abstracts fit <modelo> K        -> etapa 2: KMeans final com K clusters
    # o modelo é sempre obrigatório e precisa ser uma chave de MODELS (embed.py);
    # a métrica é sempre a METRIC do cluster.py (cosseno), sem argumento na linha de comando
    args = sys.argv[1:]
    if args and args[0] == "fetch":
        sample_size = int(args[args.index("--sample") + 1]) if "--sample" in args else None
        fetch(sample_size)
        return
    if not args or args[0] not in ("sweep", "fit"):
        exit_with_usage()

    # import aqui: embed.py só importa no ambiente de um dos extras de clustering
    from sar_review_pipeline.abstracts.embed import MODELS

    if len(args) < 2 or args[1] not in MODELS:
        exit_with_usage(MODELS)
    model_key = args[1]
    if args[0] == "sweep" and len(args) == 2:
        sweep(model_key)
    elif args[0] == "fit" and len(args) == 3:
        fit(model_key, int(args[2]))
    else:
        exit_with_usage(MODELS)


if __name__ == "__main__":
    main()
