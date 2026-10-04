import numpy as np
import faiss
import networkx as nx
import tempfile
import os

print(f"FAISS version: {getattr(faiss, '__version__', 'unknown')}")
# Check if CPU or GPU faiss
is_gpu = hasattr(faiss, 'StandardGpuResources')
print(f"FAISS GPU support: {is_gpu}")

# Test FAISS index build & search
d = 64
nb = 100
nq = 5
np.random.seed(42)
xb = np.random.random((nb, d)).astype('float32')
xq = np.random.random((nq, d)).astype('float32')

index = faiss.IndexFlatL2(d)
index.add(xb)
print(f"FAISS total indexed: {index.ntotal}")
D, I = index.search(xq, k=4)
print(f"FAISS search test: D shape {D.shape}, I shape {I.shape} -> SUCCESS")

print(f"\nNetworkX version: {nx.__version__}")
G = nx.Graph()
G.add_edge("concept_A", "concept_B", weight=0.8, relation="prerequisite")
G.add_edge("concept_B", "concept_C", weight=0.5, relation="mentions")

# Round trip through adjlist or gml in tempfile
with tempfile.NamedTemporaryFile(suffix=".gml", delete=False) as tf:
    tmp_path = tf.name

try:
    nx.write_gml(G, tmp_path)
    G_loaded = nx.read_gml(tmp_path)
    assert len(G_loaded.nodes) == 3
    assert len(G_loaded.edges) == 2
    print(f"NetworkX roundtrip (GML): {len(G_loaded.nodes)} nodes, {len(G_loaded.edges)} edges -> SUCCESS")
finally:
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
