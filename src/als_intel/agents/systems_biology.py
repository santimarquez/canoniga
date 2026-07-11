from __future__ import annotations

from collections import defaultdict


PATHWAY_EDGE_TYPES = {
    "part_of_pathway",
    "pathway_member",
    "annotated_with",
    "affects_outcome",
    "in_pathway",
}
PATHWAY_SOURCE_TOKENS = ("kegg", "reactome", "go:", "gene ontology")


def _pathway_entities(evidence_rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in evidence_rows:
        source_doi = str(row.get("source_doi", "")).lower()
        source_title = str(row.get("source_title", "")).lower()
        entity = str(row.get("entity", "")).strip()
        if not entity:
            continue
        if any(token in source_doi or token in source_title for token in PATHWAY_SOURCE_TOKENS):
            grouped[entity].append(row)
        elif entity.endswith("pathway") or "ontology" in entity.lower():
            grouped[entity].append(row)
    return grouped


def _kg_bridge_entities(neighbor_rows: list[dict[str, object]]) -> dict[str, set[str]]:
    bridge_entities: dict[str, set[str]] = defaultdict(set)
    for row in neighbor_rows:
        entity = str(row.get("entity", "")).strip()
        neighbor = str(row.get("neighbor_entity", "") or row.get("neighbor_label", "")).strip()
        edge_type = str(row.get("edge_type", "")).strip().lower()
        if not entity or not neighbor:
            continue
        if edge_type and edge_type not in PATHWAY_EDGE_TYPES and edge_type != "affects_outcome":
            continue
        bridge_entities[entity].add(neighbor)
    return bridge_entities


def _edge_semantic_score(neighbor_rows: list[dict[str, object]], entity: str) -> float:
    weights: list[float] = []
    for row in neighbor_rows:
        if str(row.get("entity", "")).strip() != entity:
            continue
        edge_type = str(row.get("edge_type", "")).strip().lower()
        if edge_type not in PATHWAY_EDGE_TYPES:
            continue
        weight = float(row.get("weight", 0.0) or 0.0)
        polarity = str(row.get("polarity", "")).strip().lower()
        polarity_bonus = 0.05 if polarity in {"positive", "supports"} else 0.0
        weights.append(min(1.0, max(0.1, weight) + polarity_bonus))
    if not weights:
        return 0.0
    return sum(weights) / len(weights)


def build_systems_biology_report(
    evidence_rows: list[dict[str, object]],
    support_map_rows: list[dict[str, object]],
    graph_neighbor_rows: list[dict[str, object]] | None = None,
    limit: int = 10,
) -> dict[str, object]:
    pathway_groups = _pathway_entities(evidence_rows)
    neighbor_rows = graph_neighbor_rows or []
    bridge_entities = _kg_bridge_entities(neighbor_rows)

    cards: list[dict[str, object]] = []
    for row in support_map_rows:
        entity = str(row.get("entity", "")).strip()
        outcome = str(row.get("outcome", "")).strip()
        if not entity:
            continue
        pathway_claims = pathway_groups.get(entity, [])
        supports = int(row.get("supports", 0))
        contradicts = int(row.get("contradicts", 0))
        total = max(supports + contradicts, 1)
        contradiction_ratio = contradicts / total
        pathway_coverage = len(pathway_claims)
        neighbor_count = len(bridge_entities.get(entity, set()))
        edge_semantic_score = _edge_semantic_score(neighbor_rows, entity)
        underexplored_index = 1.0 / (1.0 + pathway_coverage + neighbor_count)
        perturbation_score = max(
            0.0,
            min(
                1.0,
                0.3 * contradiction_ratio
                + 0.25 * underexplored_index
                + 0.2 * min(neighbor_count / 5.0, 1.0)
                + 0.25 * edge_semantic_score,
            ),
        )

        cards.append(
            {
                "entity": entity,
                "outcome": outcome,
                "pathway_coverage": pathway_coverage,
                "neighbor_entities": sorted(bridge_entities.get(entity, set()))[:8],
                "kg_edge_semantic_score": round(edge_semantic_score, 4),
                "underexplored_pathway_index": round(underexplored_index, 4),
                "perturbation_priority_score": round(perturbation_score, 4),
                "hypothesis": (
                    f"Perturbing the {entity} pathway neighborhood may resolve ALS {outcome} "
                    "contradictions through cross-pathway coupling."
                ),
                "suggested_validation_experiments": [
                    "Map pathway neighborhood expression in stratified ALS cohorts.",
                    "Test cross-pathway perturbation in coupled in vitro models.",
                ],
                "evidence_counts": {
                    "supports": supports,
                    "contradicts": contradicts,
                    "pathway_claims": pathway_coverage,
                },
            }
        )

    cards.sort(key=lambda item: float(item["perturbation_priority_score"]), reverse=True)
    top_cards = cards[:limit]
    return {
        "count": len(top_cards),
        "items": top_cards,
        "pathway_entity_clusters": len(pathway_groups),
        "kg_edge_semantics_used": bool(neighbor_rows),
    }
