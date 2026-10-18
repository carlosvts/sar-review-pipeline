"""
    Etapa 2 da triagem por abstract: KMeans sobre os embeddings.
    O ajuste e a varredura de K usam só os registros com abstract válido.
    O K não é escolhido aqui: a varredura gera cotovelo, silhouette e UMAPs para decisão manual.

    METRIC escolhe a geometria:
      - "euclidean": KMeans do sklearn e silhouette euclidiana
      - "cosine": KMeans esférico (centroides normalizados, atribuição por cosseno) e silhouette por cosseno
    Saída em data/cluster/<modelo>/<métrica>/; embeddings e layout do UMAP ficam em data/cluster/<modelo>/.
"""
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.cluster import KMeans, kmeans_plusplus
from sklearn.metrics import silhouette_score
from umap import UMAP

METRIC = "cosine"
SEED = 42
N_INIT = 10
MAX_ITER = 300
K_MIN = 2
K_MAX = 30
UMAP_KS = (9, 10)  # K candidatos para a grade de UMAP da varredura
UMAP_NEIGHBORS = 15
UMAP_MIN_DIST = 0.1

CLUSTER_DIR = Path("data/cluster")

# gráficos: série única sem legenda; nos UMAPs, 8 cores fixas + forma do marcador para K > 8
LINE_COLOR = "#2a78d6"
CATEGORICAL = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
MARKERS = ("o", "^", "s", "D")
SURFACE = "#fcfcfb"
TEXT = "#52514e"
GRID = "#e4e3df"


class SphericalKMeans:
    """
    KMeans com similaridade de cosseno: os pontos (já normalizados) vão para o
    centroide de maior cosseno, e cada centroide é a média normalizada dos seus pontos.
    inertia_ = soma de (1 - cosseno) de cada ponto ao seu centroide.
    """

    def __init__(self, n_clusters: int, n_init: int = N_INIT, random_state: int = SEED):
        self.n_clusters = n_clusters
        self.n_init = n_init
        self.random_state = random_state

    @staticmethod
    def normalize(matrix: np.ndarray) -> np.ndarray:
        return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)

    def run_once(self, X: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray, float]:
        centers, _ = kmeans_plusplus(X, self.n_clusters, random_state=seed)
        centers = self.normalize(centers)
        labels = np.full(len(X), -1)
        for _ in range(MAX_ITER):
            new_labels = np.argmax(X @ centers.T, axis=1)
            if np.array_equal(new_labels, labels):
                break
            labels = new_labels
            for c in range(self.n_clusters):
                members = X[labels == c]
                if len(members):
                    centers[c] = members.sum(axis=0)
                else:
                    # cluster vazio: recomeça no ponto mais distante do próprio centroide
                    worst = np.argmin((X * centers[labels]).sum(axis=1))
                    centers[c] = X[worst]
            centers = self.normalize(centers)
        inertia = float((1 - (X * centers[labels]).sum(axis=1)).sum())
        return centers, labels, inertia

    def fit(self, X: np.ndarray) -> "SphericalKMeans":
        seeds = np.random.RandomState(self.random_state).randint(0, 2**31 - 1, size=self.n_init)
        best = None
        for seed in seeds:
            result = self.run_once(X, int(seed))
            if best is None or result[2] < best[2]:
                best = result
        self.cluster_centers_, self.labels_, self.inertia_ = best
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.argmax(X @ self.cluster_centers_.T, axis=1)

    def transform(self, X: np.ndarray) -> np.ndarray:
        """Distância de cosseno (1 - cos) a cada centroide."""
        return 1 - X @ self.cluster_centers_.T


class Clusterer:
    RECORDS_PATH = Path("data/jsonl/candidates_abstracts.jsonl")

    @classmethod
    def output_dir(cls, model_key: str, metric: str) -> Path:
        return CLUSTER_DIR / model_key / metric

    @classmethod
    def load_records(cls) -> list[dict]:
        """Candidatos que seguem para o clustering (sem exclusion_reason)."""
        records = []
        with open(cls.RECORDS_PATH, encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                if record["exclusion_reason"] is None:
                    records.append(record)
        return records

    @classmethod
    def split_by_abstract(cls, records: list[dict]) -> tuple[list[int], list[int]]:
        """Índices dos que têm abstract válido (entram no ajuste) e dos que só têm título."""
        with_abstract = []
        title_only = []
        for i, record in enumerate(records):
            if record["title_only"]:
                title_only.append(i)
            else:
                with_abstract.append(i)
        return with_abstract, title_only

    @classmethod
    def new_kmeans(cls, k: int, metric: str = METRIC) -> KMeans | SphericalKMeans:
        if metric == "cosine":
            return SphericalKMeans(n_clusters=k, n_init=N_INIT, random_state=SEED)
        return KMeans(n_clusters=k, n_init=N_INIT, random_state=SEED)

    @classmethod
    def fit(cls, X: np.ndarray, k: int, metric: str = METRIC) -> KMeans | SphericalKMeans:
        return cls.new_kmeans(k, metric).fit(X)

    @classmethod
    def sweep(cls, X: np.ndarray, metric: str = METRIC, k_min: int = K_MIN, k_max: int = K_MAX) -> list[dict]:
        """Inércia e silhouette para cada K."""
        rows = []
        for k in range(k_min, k_max + 1):
            kmeans = cls.fit(X, k, metric)
            silhouette = silhouette_score(X, kmeans.labels_, metric=metric)
            rows.append({"k": k, "inertia": float(kmeans.inertia_), "silhouette": float(silhouette)})
            print(f"  K={k:2d}  inércia={kmeans.inertia_:.2f}  silhouette={silhouette:.4f}")
        return rows

    @classmethod
    def save_sweep_csv(cls, rows: list[dict], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["k", "inertia", "silhouette"])
            writer.writeheader()
            writer.writerows(rows)

    @classmethod
    def style_axes(cls, fig, ax, title: str) -> None:
        fig.patch.set_facecolor(SURFACE)
        ax.set_facecolor(SURFACE)
        ax.set_title(title, color=TEXT, loc="left", fontsize=12)
        ax.tick_params(colors=TEXT, labelsize=8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)

    @classmethod
    def plot_metric(cls, rows: list[dict], metric: str, title: str, ylabel: str, path: Path) -> None:
        ks = [r["k"] for r in rows]
        values = [r[metric] for r in rows]
        fig, ax = plt.subplots(figsize=(9, 5), dpi=150)
        cls.style_axes(fig, ax, title)
        ax.plot(ks, values, color=LINE_COLOR, linewidth=2, marker="o", markersize=6,
                markeredgecolor=SURFACE, markeredgewidth=1.5)
        ax.set_xlabel("K (número de clusters)", color=TEXT)
        ax.set_ylabel(ylabel, color=TEXT)
        ax.set_xticks(ks)
        ax.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        fig.tight_layout()
        fig.savefig(path, facecolor=SURFACE)
        plt.close(fig)

    @classmethod
    def umap_layout(cls, embeddings: np.ndarray, ids: list[str], model_key: str) -> np.ndarray:
        """Projeção 2D de todos os registros; fica em disco para todos os gráficos do modelo usarem o mesmo layout."""
        model_dir = CLUSTER_DIR / model_key
        npy_path = model_dir / "umap_2d.npy"
        ids_path = model_dir / "umap_ids.json"
        if npy_path.exists() and ids_path.exists() and json.loads(ids_path.read_text()) == ids:
            return np.load(npy_path)
        reducer = UMAP(n_components=2, metric="cosine", n_neighbors=UMAP_NEIGHBORS,
                       min_dist=UMAP_MIN_DIST, random_state=SEED)
        layout = reducer.fit_transform(embeddings)
        model_dir.mkdir(parents=True, exist_ok=True)
        np.save(npy_path, layout)
        ids_path.write_text(json.dumps(ids), encoding="utf-8")
        return layout

    @classmethod
    def plot_umap(cls, layout: np.ndarray, labels: np.ndarray, by_title: np.ndarray, title: str, path: Path) -> None:
        """
        Cor + forma identificam o cluster (8 cores, a forma muda a cada 8 clusters) e
        o número de cada cluster fica na mediana dos seus pontos.
        Pontos atribuídos só pelo título aparecem vazados.
        """
        fig, ax = plt.subplots(figsize=(10, 8), dpi=150)
        cls.style_axes(fig, ax, title)
        ax.set_xticks([])
        ax.set_yticks([])
        for c in sorted(set(labels.tolist())):
            color = CATEGORICAL[c % len(CATEGORICAL)]
            marker = MARKERS[c // len(CATEGORICAL)]
            filled = (labels == c) & ~by_title
            hollow = (labels == c) & by_title
            ax.scatter(layout[filled, 0], layout[filled, 1], s=14, c=color, marker=marker,
                       edgecolors=SURFACE, linewidths=0.4, label=f"{c}")
            if hollow.any():
                ax.scatter(layout[hollow, 0], layout[hollow, 1], s=18, facecolors="none",
                           edgecolors=color, marker=marker, linewidths=0.9)
            center = np.median(layout[labels == c], axis=0)
            ax.annotate(str(c), center, color=TEXT, fontsize=10, fontweight="bold", ha="center", va="center",
                        bbox={"boxstyle": "round,pad=0.2", "fc": SURFACE, "ec": GRID, "alpha": 0.9})
        ax.legend(title="cluster", loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False,
                  fontsize=8, title_fontsize=9, labelcolor=TEXT, markerscale=1.5)
        if by_title.any():
            ax.text(0, -0.03, "Marcadores vazados: atribuídos ao cluster só pelo título.",
                    transform=ax.transAxes, color=TEXT, fontsize=8)
        fig.tight_layout()
        fig.savefig(path, facecolor=SURFACE)
        plt.close(fig)

    @classmethod
    def assignments(
        cls, records: list[dict], embeddings: np.ndarray, kmeans: KMeans | SphericalKMeans,
        with_abstract: list[int], title_only: list[int],
    ) -> list[dict]:
        """Cluster e distância ao centroide; os title_only vão para o centroide mais próximo."""
        rows = []
        groups = ((with_abstract, False), (title_only, True))
        for indices, by_title in groups:
            if not indices:
                continue
            X = embeddings[indices]
            labels = kmeans.predict(X)
            distances = kmeans.transform(X)
            for row_i, record_i in enumerate(indices):
                label = int(labels[row_i])
                record = records[record_i]
                rows.append({
                    "id": record["id"],
                    "titulo": record["title"],
                    "cluster": label,
                    "distancia_centroide": round(float(distances[row_i, label]), 6),
                    "tem_abstract": not by_title,
                    "atribuido_por_titulo": by_title,
                })
        rows.sort(key=lambda r: (r["cluster"], r["distancia_centroide"]))
        return rows

    @classmethod
    def save_assignments(cls, rows: list[dict], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = ["id", "titulo", "cluster", "distancia_centroide", "tem_abstract", "atribuido_por_titulo"]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    @classmethod
    def cluster_sizes(cls, rows: list[dict]) -> dict[int, dict[str, int]]:
        """Por cluster: quantos têm abstract e quantos entraram pelo título."""
        sizes: dict[int, dict[str, int]] = {}
        for row in rows:
            counts = sizes.setdefault(row["cluster"], {"com_abstract": 0, "por_titulo": 0})
            if row["atribuido_por_titulo"]:
                counts["por_titulo"] += 1
            else:
                counts["com_abstract"] += 1
        return dict(sorted(sizes.items()))
