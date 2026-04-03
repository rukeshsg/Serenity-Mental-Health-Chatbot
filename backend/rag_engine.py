import faiss
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel
from rank_bm25 import BM25Okapi
import re
import os

# ------------------ Project root path (ADVANCEchatbot) ------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))


def _resolve_knowledge_path():
    """Resolve knowledge file path from project root."""
    candidates = [
        os.path.join(_PROJECT_ROOT, "backend", "data", "mental_health_knowledge.txt"),
        os.path.join(_THIS_DIR, "data", "mental_health_knowledge.txt"),
        "backend/data/mental_health_knowledge.txt",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]

# ------------------ Load MiniLM without sentence-transformers ------------------

tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
model = AutoModel.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")

def embed(texts):
    inputs = tokenizer(
        texts,
        padding=True,
        truncation=True,
        return_tensors="pt"
    )

    with torch.no_grad():
        outputs = model(**inputs)

    # Mean pooling
    embeddings = outputs.last_hidden_state.mean(dim=1)
    return embeddings.numpy()


# ------------------ Load knowledge ------------------

def load_knowledge(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    raw_chunks = content.split("Situation:")
    situations = []
    responses = []

    for chunk in raw_chunks:
        if "Response:" in chunk:
            situation, response = chunk.split("Response:")
            situations.append(situation.strip())
            responses.append(response.strip())

    return situations, responses


# ------------------ Create FAISS index ------------------

def create_faiss_index(situations):
    embeddings = embed(situations)
    dimension = embeddings.shape[1]

    # Use Inner Product (cosine similarity) instead of L2
    index = faiss.IndexFlatIP(dimension)
    
    # Normalize embeddings for cosine similarity
    faiss.normalize_L2(embeddings)
    index.add(np.array(embeddings))

    return index


# ------------------ BM25 Setup ------------------

def create_bm25_index(situations):
    """Create BM25 index from situations"""
    # Tokenize situations
    tokenized = [simple_tokenize(s) for s in situations]
    return BM25Okapi(tokenized)

def simple_tokenize(text):
    """Simple tokenization"""
    text = text.lower()
    tokens = re.findall(r'\b\w+\b', text)
    return tokens


# ------------------ Hybrid Search ------------------

def search_bm25(query, bm25_index, situations, responses, k=3):
    """BM25 search returns top-k results"""
    tokenized_query = simple_tokenize(query)
    scores = bm25_index.get_scores(tokenized_query)
    
    # Get top-k indices
    top_indices = np.argsort(scores)[::-1][:k]
    
    return [(responses[i], scores[i]) for i in top_indices]


def search_faiss(query, faiss_index, situations, responses, k=3):
    """FAISS semantic search returns top-k results"""
    query_embedding = embed([query])
    faiss.normalize_L2(query_embedding)
    
    scores, indices = faiss_index.search(np.array(query_embedding), k)
    
    return [(responses[i], scores[0][j]) for j, i in enumerate(indices[0])]


def hybrid_search(query, faiss_index, bm25_index, situations, responses, k=2, alpha=0.5):
    """
    Combine BM25 and FAISS results
    
    Args:
        query: Search query
        faiss_index: FAISS semantic index
        bm25_index: BM25 keyword index
        situations: List of situation texts
        responses: List of response texts
        k: Number of results to return
        alpha: Weight for FAISS (1-alpha for BM25)
    
    Returns:
        List of (response, combined_score) tuples
    """
    # Get results from both methods
    faiss_results = search_faiss(query, faiss_index, situations, responses, k=k*2)
    bm25_results = search_bm25(query, bm25_index, situations, responses, k=k*2)
    
    # Normalize FAISS scores (they can be negative after normalization)
    if faiss_results:
        max_faiss = max(abs(s) for _, s in faiss_results) if faiss_results else 1
        faiss_scores = {r: abs(s)/max_faiss for r, s in faiss_results}
    else:
        faiss_scores = {}
    
    # Normalize BM25 scores
    if bm25_results:
        max_bm25 = max(s for _, s in bm25_results) if bm25_results else 1
        bm25_scores = {r: s/max_bm25 for r, s in bm25_results}
    else:
        bm25_scores = {}
    
    # Combine all unique responses
    all_responses = set(r for r, _ in faiss_results) | set(r for r, _ in bm25_results)
    
    # Calculate combined scores
    combined = []
    for resp in all_responses:
        f_score = faiss_scores.get(resp, 0)
        b_score = bm25_scores.get(resp, 0)
        combined_score = alpha * f_score + (1 - alpha) * b_score
        combined.append((resp, combined_score))
    
    # Sort by combined score and return top-k
    combined.sort(key=lambda x: x[1], reverse=True)
    return combined[:k]


# ------------------ Simple Search (backward compatible) ------------------

def search(query, index, situations, responses, k=1):
    """Simple FAISS search (backward compatible)"""
    query_embedding = embed([query])
    faiss.normalize_L2(query_embedding)
    scores, indices = index.search(np.array(query_embedding), k)

    return [responses[i] for i in indices[0]]


# ------------------ Initialize once ------------------

situations, responses = load_knowledge(_resolve_knowledge_path())
faiss_index = create_faiss_index(situations)
bm25_index = create_bm25_index(situations)


# ------------------ Test ------------------

if __name__ == "__main__":
    print("Testing Hybrid RAG Engine...")
    print("=" * 50)
    
    test_queries = [
        "I feel anxious about my exams",
        "my friend is depressed",
        "I want to hurt myself"
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 30)
        
        # Simple search
        simple_results = search(query, faiss_index, situations, responses, k=1)
        print(f"Simple FAISS: {simple_results[0][:100]}...")
        
        # Hybrid search
        hybrid_results = hybrid_search(query, faiss_index, bm25_index, situations, responses, k=2)
        print(f"Hybrid (BM25+FAISS): {hybrid_results[0][0][:100]}...")
        
    print("\n" + "=" * 50)
    print("Tests complete!")
  
index = faiss_index 
