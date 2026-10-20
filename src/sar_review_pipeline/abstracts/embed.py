"""
    Embedding de título + abstract para o clustering.
    Cada modelo tem a sua configuração em MODELS: forma de carregar, formato do texto,
    pooling, dtype, max_length, batch_size, revisão (commit) no Hugging Face e o extra
    em que roda. O PaperEmbedder só lê essa configuração.

    specter2 (https://huggingface.co/allenai/specter2): título + [SEP] + abstract
    (vazio para quem só tem título), token CLS, até 512 tokens, fp32.

    Os vetores ficam em disco (npy + ids + meta) e só são reaproveitados se a
    configuração do modelo, os ids e os textos de entrada forem os mesmos.

    Determinismo: o modelo roda em eval() e sem gradiente, sem nenhuma etapa aleatória.
    Na GPU, com a mesma ordem dos textos e o mesmo batch_size (os mesmos lotes), o resultado
    se repete na mesma máquina. Em outra GPU, driver ou versão do torch os kernels podem
    mudar a ordem das somas em ponto flutuante, com diferenças pequenas (da ordem de 1e-6
    no cosseno em fp32, maiores em fp16); isso não dá para eliminar.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import torch

# o formato de entrada é um modelo de str.format com {title} e {abstract};
# a revisão é o commit do Hugging Face usado no from_pretrained (nada de versão flutuante)
MODELS = {
    "specter2": {
        "extra": "cluster-specter",
        # adapters: AutoAdapterModel com o adapter carregado por cima da base
        "loader": "adapters",
        "base": "allenai/specter2_base",
        "base_revision": "3447645e1def9117997203454fa4495937bfbd83",
        # adapter de proximidade: o model card indica para tarefas não listadas, como clustering
        "adapter": "allenai/specter2",
        "adapter_revision": "2081559630a80fc5851d8f798a05ba81e9468089",
        "input_format": "{title}[SEP]{abstract}",
        "pooling": "cls",
        "dtype": "float32",
        "max_length": 512,
        "batch_size": 8,  # cabe numa GPU de 4GB com 512 tokens
    },
    "mpnet": {
        "extra": "cluster-sentence-transformers",
        # sentence_transformers: SentenceTransformer com os parâmetros do model card
        "loader": "sentence_transformers",
        "base": "sentence-transformers/all-mpnet-base-v2",
        "base_revision": "e8c3b32edf5434bc2275fc9bab85f82640a19130",
        "adapter": None,
        "adapter_revision": None,
        # mesmo padrão do specter2: quem só tem título fica com o abstract vazio
        "input_format": "{title}\n{abstract}",
        # o pooling vem da configuração do próprio modelo (média dos tokens, no caso do mpnet)
        "pooling": "sentence_transformers",
        "dtype": "float32",
        "max_length": 384,  # máximo do model card (treinado com 128)
        "batch_size": 32,
    },
    "qwen3": {
        "extra": "cluster-sentence-transformers",
        "loader": "sentence_transformers",
        "base": "Qwen/Qwen3-Embedding-0.6B",
        "base_revision": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
        "adapter": None,
        "adapter_revision": None,
        # documentos sem instrução, como no RAG; mesmo padrão do mpnet
        "input_format": "{title}\n{abstract}",
        # o pooling vem da configuração do próprio modelo (último token, no caso do Qwen3)
        "pooling": "sentence_transformers",
        "dtype": "float16",
        "max_length": 512,
        "batch_size": 12,
        "model_kwargs": {"attn_implementation": "sdpa"},
        "processor_kwargs": {"padding_side": "left"},
    },
}

# campos da configuração que precisam bater com o meta.json para reaproveitar o cache
CACHE_KEYS = (
    "loader", "base", "base_revision", "adapter", "adapter_revision",
    "input_format", "pooling", "dtype", "max_length",
)


class PaperEmbedder:
    DIR = Path("data/cluster")

    def __init__(self, model_key: str):
        self.model_key = model_key
        self.config = MODELS[model_key]
        self.batch_size = self.config["batch_size"]
        self.model_dir = self.DIR / model_key
        self.npy_path = self.model_dir / "embeddings.npy"
        self.ids_path = self.model_dir / "ids.json"
        self.meta_path = self.model_dir / "meta.json"
        self.check_environment()

    def check_environment(self) -> None:
        """Falha cedo se o extra do modelo não estiver instalado ou a revisão não estiver fixada."""
        extra = self.config["extra"]
        if importlib.util.find_spec(self.config["loader"]) is None:
            raise SystemExit(f"o modelo {self.model_key} roda no extra {extra}, que não está instalado neste ambiente")
        if not self.config["base_revision"]:
            raise SystemExit(f"o modelo {self.model_key} não tem a revisão fixada em MODELS")
        if self.config["adapter"] and not self.config["adapter_revision"]:
            raise SystemExit(f"o adapter de {self.model_key} não tem a revisão fixada em MODELS")

    def load_model(self) -> None:
        """Carrega o modelo na GPU; sem GPU, para antes de carregar."""
        if not torch.cuda.is_available():
            raise SystemExit("GPU (CUDA) indisponível: o embedding só roda na GPU")
        self.device = "cuda"
        dtype = getattr(torch, self.config["dtype"])

        if self.config["loader"] == "adapters":
            # import aqui: adapters só existe no ambiente do extra cluster-specter
            from adapters import AutoAdapterModel
            from transformers import AutoTokenizer

            self.tokenizer = AutoTokenizer.from_pretrained(self.config["base"], revision=self.config["base_revision"])
            self.model = AutoAdapterModel.from_pretrained(
                self.config["base"], revision=self.config["base_revision"], dtype=dtype,
            )
            self.model.load_adapter(
                self.config["adapter"], source="hf", version=self.config["adapter_revision"],
                load_as=self.model_key, set_active=True,
            )
            self.model.to(self.device)
            self.encode_batch = self.encode_cls
        else:
            # import aqui: sentence_transformers só existe no ambiente do extra cluster-sentence-transformers
            from sentence_transformers import SentenceTransformer

            model_kwargs = dict(self.config.get("model_kwargs", {}))
            model_kwargs["dtype"] = dtype
            self.model = SentenceTransformer(
                self.config["base"],
                revision=self.config["base_revision"],
                device=self.device,
                model_kwargs=model_kwargs,
                processor_kwargs=self.config.get("processor_kwargs", {}),
            )
            self.model.max_seq_length = self.config["max_length"]
            self.encode_batch = self.encode_sentence_transformers
        self.model.eval()

    def build_text(self, record: dict) -> str:
        return self.config["input_format"].format(title=record["title"] or "", abstract=record["abstract"] or "")

    def encode_cls(self, texts: list[str]) -> np.ndarray:
        """Token CLS da última camada (specter2)."""
        inputs = self.tokenizer(
            texts, padding=True, truncation=True, max_length=self.config["max_length"],
            return_tensors="pt", return_token_type_ids=False,
        ).to(self.device)
        with torch.no_grad():
            output = self.model(**inputs)
        return output.last_hidden_state[:, 0, :].float().cpu().numpy()

    def encode_sentence_transformers(self, texts: list[str]) -> np.ndarray:
        """Pooling do próprio modelo; a normalização fica para embed_texts, igual para todos."""
        with torch.no_grad():
            vectors = self.model.encode(
                texts, batch_size=len(texts), normalize_embeddings=False,
                convert_to_numpy=True, show_progress_bar=False,
            )
        return vectors.astype(np.float32)

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Vetores normalizados (L2), lote a lote na ordem dos textos."""
        vectors = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            vectors.append(self.encode_batch(batch))
            print(f"  {min(i + self.batch_size, len(texts))}/{len(texts)}")
        matrix = np.vstack(vectors)
        return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)

    @staticmethod
    def texts_hash(texts: list[str]) -> str:
        return hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()

    def load_cached(self, ids: list[str], texts_hash: str) -> np.ndarray | None:
        if not (self.npy_path.exists() and self.ids_path.exists() and self.meta_path.exists()):
            return None
        meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        cached_ids = json.loads(self.ids_path.read_text(encoding="utf-8"))
        # qualquer campo diferente (ou ausente num meta.json antigo) => recalcular
        for key in CACHE_KEYS:
            if meta.get(key) != self.config[key]:
                return None
        if cached_ids != ids or meta.get("texts_sha256") != texts_hash:
            return None
        return np.load(self.npy_path)

    def embed_records(self, records: list[dict]) -> np.ndarray:
        """Matriz (n, dim) na ordem de records; usa o que está em disco se nada mudou."""
        ids = [r["id"] for r in records]
        texts = [self.build_text(r) for r in records]
        texts_hash = self.texts_hash(texts)
        if (cached := self.load_cached(ids, texts_hash)) is not None:
            print(f"Embeddings em disco: {self.npy_path}")
            return cached

        self.load_model()
        print(f"Calculando embeddings ({self.model_key}, {self.device}) de {len(texts)} textos")
        matrix = self.embed_texts(texts)

        self.model_dir.mkdir(parents=True, exist_ok=True)
        np.save(self.npy_path, matrix)
        self.ids_path.write_text(json.dumps(ids), encoding="utf-8")
        meta = {"model_key": self.model_key, "extra": self.config["extra"]}
        for key in CACHE_KEYS:
            meta[key] = self.config[key]
        meta["batch_size"] = self.batch_size
        meta["normalized"] = "l2"
        meta["n"] = int(matrix.shape[0])
        meta["dim"] = int(matrix.shape[1])
        meta["texts_sha256"] = texts_hash
        self.meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        return matrix
