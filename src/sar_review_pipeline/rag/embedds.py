from sentence_transformers import SentenceTransformer
from pathlib import Path
import torch
import json

ROOT = Path(__file__).resolve().parents[3]
CLUSTER_FILE = ROOT / "data/fulltext/chunks.jsonl" 
QUESTIONS = ROOT / "src/sar_review_pipeline/rag/questions.json"

def load_questions(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        questions = json.load(f)
        return questions

def load_clusters(path: Path):
    clusters = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            jsoned_line = json.loads(line)
            clusters.append(jsoned_line)
        return clusters

def sanitize_subqueries(questions):
    """
        sanitiza as subqueries de cada QP para o modelo 
        retorna dict[QPX, [lista de subqueries]]
    """
    # print(questions)
    sanitized_qps = {}
    for question in questions:
        # print(question)
        # print(sanitized_qps)
        q = ""
        for query in question["sub_queries"]:
            q += query
        sanitized_qps.update({question["id"] : q})
    return sanitized_qps

# boilerplate work from: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
# Load the model
model = SentenceTransformer(
        "Qwen/Qwen3-Embedding-0.6B",
        # scaled dot product attention
        model_kwargs={"attn_implementation": "sdpa", "device_map": "auto", "dtype": torch.float16},
        processor_kwargs={"padding_side": "left"},
)

questions = load_questions(Path(QUESTIONS))
sn_subqueries = sanitize_subqueries(questions)
print(sn_subqueries)

document  = load_clusters(Path(CLUSTER_FILE))

# query_embeddings = model.encode(questions, prompt_name="query")
# print(query_embeddings)


# The queries and documents to embed
#queries = [
        #    "What is the capital of China?",
        #"Exp#lain gravity",
        #]
#documents = [
        #    "The capital of China is Beijing.",
        #"Gravity is a force that attracts two bodies towards each other. It gives weight to physical objects and is responsible for the movement of planets around the sun.",
        #]

# Encode the queries and documents. Note that queries benefit from using a prompt
# Here we use the prompt called "query" stored under `model.prompts`, but you can
# also pass your own prompt via the `prompt` argument
#query_embeddings = model.encode(queries, prompt_name="query")
#document_embeddings = model.encode(documents)

# Compute the (cosine) similarity between the query and document embeddings
#similarity = model.similarity(query_embeddings, document_embeddings)
#print(similarity)
# tensor([[0.7646, 0.1414],
#         [0.1355, 0.6000]])
