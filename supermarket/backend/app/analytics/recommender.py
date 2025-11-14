from typing import Dict, Any, List
from collections import Counter
from itertools import combinations
from .ingestion import repo

MIN_SUPPORT = 0.01
MIN_CONFIDENCE = 0.3


def build_association_rules() -> Dict[str, Any]:
    tx = repo.data.transactions
    trans_lists: List[List[str]] = tx['products'].astype(str).str.split().tolist()
    total = len(trans_lists)

    # Item counts
    item_counts = Counter()
    for t in trans_lists:
        for item in set(t):
            item_counts[item] += 1
    frequent_items = {i: c for i, c in item_counts.items() if c/total >= MIN_SUPPORT}

    pair_counts = Counter()
    for t in trans_lists:
        for a, b in combinations(sorted(set(t)), 2):
            pair_counts[(a, b)] += 1

    rules = []
    for (a, b), c_ab in pair_counts.items():
        support_ab = c_ab / total
        if support_ab < MIN_SUPPORT:
            continue
        support_a = item_counts[a] / total
        support_b = item_counts[b] / total
        conf_ab = c_ab / item_counts[a]
        conf_ba = c_ab / item_counts[b]
        lift_ab = conf_ab / support_b
        lift_ba = conf_ba / support_a
        if conf_ab >= MIN_CONFIDENCE:
            rules.append({'antecedent': a, 'consequent': b, 'support': support_ab, 'confidence': conf_ab, 'lift': lift_ab})
        if conf_ba >= MIN_CONFIDENCE:
            rules.append({'antecedent': b, 'consequent': a, 'support': support_ab, 'confidence': conf_ba, 'lift': lift_ba})

    rules_sorted = sorted(rules, key=lambda r: r['lift'], reverse=True)
    # Guardar TODAS las reglas, no solo 50, para que recommend_for_product funcione correctamente
    return {'rules': rules_sorted, 'frequent_items': frequent_items}


_cached_rules: Dict[str, Any] = {}


def get_rules() -> Dict[str, Any]:
    global _cached_rules
    if not _cached_rules:
        _cached_rules = build_association_rules()
    return _cached_rules


def recommend_for_product(product_code: str, top_n: int = 5) -> Dict[str, Any]:
    rules = get_rules()['rules']
    related = [r for r in rules if r['antecedent'] == product_code]
    return {'product': product_code, 'recommendations': related[:top_n]}


def recommend_for_customer(customer_id: str, top_n: int = 5) -> Dict[str, Any]:
    tx = repo.data.transactions
    cust_products = tx[tx['customer'] == customer_id]['products'].astype(str).str.split().sum()
    rules = get_rules()['rules']
    scored = []
    owned = set(cust_products)
    for r in rules:
        if r['antecedent'] in owned and r['consequent'] not in owned:
            scored.append(r)
    # Deduplicate by consequent keeping highest lift
    best_by_consequent = {}
    for r in scored:
        c = r['consequent']
        if c not in best_by_consequent or r['lift'] > best_by_consequent[c]['lift']:
            best_by_consequent[c] = r
    ordered = sorted(best_by_consequent.values(), key=lambda r: r['lift'], reverse=True)
    return {'customer': customer_id, 'recommendations': ordered[:top_n]}
