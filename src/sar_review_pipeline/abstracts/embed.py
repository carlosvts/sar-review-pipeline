"""
    Embedding de título + abstract com um modelo treinado em artigos científicos.
    Formato e pooling seguem o model card (https://huggingface.co/allenai/specter2):
    título + [SEP] + abstract (vazio para quem só tem título), token CLS, até 512 tokens.
    Os vetores ficam em disco (npy + ids + meta) e só são recalculados se o
    modelo ou os textos de entrada mudarem.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from adapters import AutoAdapterModel
from huggingface_hub import HfApi
from transformers import AutoModel, AutoTokenizer

# modelo usado no clustering; o SciNCL usa o mesmo formato de entrada e o mesmo pooling
EMBEDDING_MODEL = "specter2"
MODELS = {
    # adapter de proximidade: o model card indica para tarefas não listadas, como clustering
    "specter2": {"base": "allenai/specter2_base", "adapter": "allenai/specter2"},
    "scincl": {"base": "malteos/scincl", "adapter": None},
}
BATCH_SIZE = 8  # cabe numa GPU de 4GB com 512 tokens
MAX_LENGTH = 512


class PaperEmbedder:
    DIR = Path("data/cluster")

    def __init__(self, model_key: str = EMBEDDING_MODEL, batch_size: int = BATCH_SIZE):
        self.model_key = model_key
        self.base = MODELS[model_key]["base"]
        self.adapter = MODELS[model_key]["adapter"]
        self.batch_size = batch_size
        self.model_dir = self.DIR / model_key
        self.npy_path = self.model_dir / "embeddings.npy"
        self.ids_path = self.model_dir / "ids.json"
        self.meta_path = self.model_dir / "meta.json"

    def load_model(self):
        self.tokenizer = AutoTokenizer.from_pretrained(self.base)
        if self.adapter:
            self.model = AutoAdapterModel.from_pretrained(self.base)
            self.model.load_adapter(self.adapter, source="hf", load_as=self.model_key, set_active=True)
        else:
            self.model = AutoModel.from_pretrained(self.base)
        self.model.eval()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device)

    def build_text(self, record: dict) -> str:
        return (record["title"] or "") + self.tokenizer.sep_token + (record["abstract"] or "")

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        inputs = self.tokenizer(
            texts, padding=True, truncation=True, max_length=MAX_LENGTH,
            return_tensors="pt", return_token_type_ids=False,
        ).to(self.device)
        with torch.no_grad():
            output = self.model(**inputs)
        return output.last_hidden_state[:, 0, :].float().cpu().numpy()

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Vetores CLS normalizados (L2). Se a GPU estourar a memória, continua na CPU."""
        vectors = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            try:
                vectors.append(self.embed_batch(batch))
            except torch.cuda.OutOfMemoryError:
                print("GPU sem memória, seguindo na CPU")
                torch.cuda.empty_cache()
                self.device = "cpu"
                self.model.to(self.device)
                vectors.append(self.embed_batch(batch))
            print(f"  {min(i + self.batch_size, len(texts))}/{len(texts)}")
        matrix = np.vstack(vectors)
        return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)

    def model_versions(self) -> dict:
        """Commit de cada repositório no Hugging Face, para registrar a versão usada."""
        api = HfApi()
        versions = {self.base: api.model_info(self.base).sha}
        if self.adapter:
            versions[self.adapter] = api.model_info(self.adapter).sha
        return versions

    @staticmethod
    def texts_hash(texts: list[str]) -> str:
        return hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()

    def load_cached(self, ids: list[str], texts_hash: str) -> np.ndarray | None:
        if not (self.npy_path.exists() and self.ids_path.exists() and self.meta_path.exists()):
            return None
        meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        cached_ids = json.loads(self.ids_path.read_text(encoding="utf-8"))
        if meta["base"] != self.base or meta["adapter"] != self.adapter:
            return None
        if cached_ids != ids or meta["texts_sha256"] != texts_hash:
            return None
        return np.load(self.npy_path)

    def embed_records(self, records: list[dict]) -> np.ndarray:
        """Matriz (n, dim) na ordem de records; usa o que está em disco se nada mudou."""
        self.tokenizer = AutoTokenizer.from_pretrained(self.base)
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
        meta = {
            "model_key": self.model_key,
            "base": self.base,
            "adapter": self.adapter,
            "versions": self.model_versions(),
            "pooling": "cls",
            "max_length": MAX_LENGTH,
            "normalized": "l2",
            "n": int(matrix.shape[0]),
            "dim": int(matrix.shape[1]),
            "texts_sha256": texts_hash,
        }
        self.meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        return matrix
