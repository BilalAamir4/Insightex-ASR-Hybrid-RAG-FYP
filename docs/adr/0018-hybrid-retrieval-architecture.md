# ADR-0018: Hybrid retrieval architecture

Status: Accepted
Date decided: not recorded; before 2026-10-08
Date recorded: 2026-10-08
Module: Project

## Context

The system answers questions over concepts (graph-shaped queries) and free text (vector queries).

## Decision

- A knowledge graph (NetworkX, primary) plus a FAISS vector index (`faiss-cpu`).
- A query router: graph-first when the query matches a known concept label, otherwise vector fallback or merge.
- Router quality is checked in M9.

## Alternatives considered

Neo4j: deferred (ADR-0021). Vector-only retrieval: kept as the fallback; M9 compares the router against it.

## Consequences

- The graph needs canonicalised concept labels (ADR-0019).
- If the router does not beat vector-only on graph-shaped queries, it is simplified.

## Evidence

`docs/BUILD_ORDER.md` (M9); `requirements.lock.txt` (`networkx==3.6.1`, `faiss-cpu==1.15.1`).

## Gate / revisit when

Gate (M9 exit): the router beats vector-only on graph-shaped queries, or the router is simplified.
