import faiss
import numpy as np
import networkx as nx

def test_faiss_networkx():
    print("\n==========================================")
    print("6d Check: FAISS & NetworkX Smoke Test")
    print("==========================================")
    
    # FAISS test (Inner Product / Cosine Similarity for BGE-M3 1024-dim)
    dim = 1024
    num_vectors = 100
    np.random.seed(42)
    vectors = np.random.randn(num_vectors, dim).astype(np.float32)
    faiss.normalize_L2(vectors)
    
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    print(f"FAISS index total vectors: {index.ntotal}")
    
    query = np.random.randn(1, dim).astype(np.float32)
    faiss.normalize_L2(query)
    distances, indices = index.search(query, k=5)
    print(f"FAISS top-5 search results: {indices[0]} with cosine scores: {distances[0]}")
    assert len(indices[0]) == 5
    
    # NetworkX test (Knowledge Graph representation)
    G = nx.DiGraph()
    G.add_node("Concept:GradientDescent", type="concept", name="Gradient Descent")
    G.add_node("Concept:BatchGD", type="concept", name="Batch Gradient Descent")
    G.add_node("VideoChunk:001", type="chunk", start_time="00:01:15", end_time="00:02:30")
    
    G.add_edge("Concept:BatchGD", "Concept:GradientDescent", relation="SUBCLASS_OF")
    G.add_edge("VideoChunk:001", "Concept:BatchGD", relation="MENTIONS")
    
    print(f"NetworkX graph nodes: {G.number_of_nodes()}, edges: {G.number_of_edges()}")
    neighbors = list(G.neighbors("VideoChunk:001"))
    print(f"VideoChunk:001 mentions: {neighbors}")
    assert len(neighbors) == 1
    
    print("STATUS: PASS for FAISS & NetworkX")

if __name__ == "__main__":
    test_faiss_networkx()
