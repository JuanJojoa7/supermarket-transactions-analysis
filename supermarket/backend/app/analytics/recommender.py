from typing import Dict, Any, List
from collections import Counter
from itertools import combinations
from .ingestion import repo

MIN_SUPPORT = 0.01
MIN_CONFIDENCE = 0.3

# Caché global para reglas
_cached_rules: Dict[str, Any] = {}


def build_association_rules() -> Dict[str, Any]:
    """
    Construye reglas de asociación usando algoritmo Apriori simplificado.
    Calcula soporte, confianza y lift para pares de productos.
    
    Returns:
        Diccionario con reglas ordenadas por lift y items frecuentes
    """
    tx = repo.data.transactions
    trans_lists: List[List[str]] = tx['products'].astype(str).str.split().tolist()
    total = len(trans_lists)
    
    # Mapeo de producto a categoría y nombre
    prod_cat_map = repo.data.product_to_category
    categories = repo.data.categories
    cat_name_map = categories.set_index('category_id')['category_name'].to_dict()
    
    # Contar items individuales
    item_counts = Counter()
    for t in trans_lists:
        for item in set(t):
            item_counts[item] += 1
    frequent_items = {i: c for i, c in item_counts.items() if c/total >= MIN_SUPPORT}
    
    # Contar pares de items
    pair_counts = Counter()
    for t in trans_lists:
        for a, b in combinations(sorted(set(t)), 2):
            pair_counts[(a, b)] += 1
    
    # Generar reglas con métricas
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
        
        # Agregar información de categoría
        cat_a = prod_cat_map.get(a, 'Unknown')
        cat_b = prod_cat_map.get(b, 'Unknown')
        cat_name_a = cat_name_map.get(cat_a, 'Sin categoría')
        cat_name_b = cat_name_map.get(cat_b, 'Sin categoría')
        
        if conf_ab >= MIN_CONFIDENCE:
            rules.append({
                'antecedent': a, 
                'consequent': b, 
                'antecedent_category': cat_name_a,
                'consequent_category': cat_name_b,
                'support': support_ab, 
                'confidence': conf_ab, 
                'lift': lift_ab
            })
        if conf_ba >= MIN_CONFIDENCE:
            rules.append({
                'antecedent': b, 
                'consequent': a,
                'antecedent_category': cat_name_b,
                'consequent_category': cat_name_a,
                'support': support_ab, 
                'confidence': conf_ba, 
                'lift': lift_ba
            })
    
    rules_sorted = sorted(rules, key=lambda r: r['lift'], reverse=True)
    return {'rules': rules_sorted, 'frequent_items': frequent_items}


def initialize_rules() -> None:
    """
    Pre-carga las reglas de asociación al iniciar la aplicación.
    Esto evita recalcularlas en cada request.
    """
    global _cached_rules
    if not _cached_rules:
        print("Cargando reglas de asociación...")
        _cached_rules = build_association_rules()
        print(f"✓ {len(_cached_rules['rules'])} reglas cargadas")


def get_rules() -> Dict[str, Any]:
    """Obtiene las reglas cacheadas, calculándolas si es necesario."""
    global _cached_rules
    if not _cached_rules:
        _cached_rules = build_association_rules()
    return _cached_rules


def recommend_for_product(product_code: str, top_n: int = 5) -> Dict[str, Any]:
    """
    Recomienda productos basados en reglas de asociación para un producto dado.
    
    Args:
        product_code: Código del producto base
        top_n: Número máximo de recomendaciones
    
    Returns:
        Diccionario con producto y lista de recomendaciones con categorías
    """
    rules = get_rules()['rules']
    related = [r for r in rules if r['antecedent'] == product_code]
    return {'product': product_code, 'recommendations': related[:top_n]}


def recommend_for_customer(customer_id: str, top_n: int = 5) -> Dict[str, Any]:
    """
    Recomienda productos para un cliente basado en su historial de compras.
    
    Args:
        customer_id: ID del cliente
        top_n: Número máximo de recomendaciones
    
    Returns:
        Diccionario con cliente y lista de recomendaciones con categorías
    """
    tx = repo.data.transactions
    cust_products = tx[tx['customer'] == customer_id]['products'].astype(str).str.split().sum()
    rules = get_rules()['rules']
    scored = []
    owned = set(cust_products)
    
    # Buscar reglas donde el antecedente está en el historial del cliente
    for r in rules:
        if r['antecedent'] in owned and r['consequent'] not in owned:
            scored.append(r)
    
    # Eliminar duplicados manteniendo el lift más alto por consecuente
    best_by_consequent = {}
    for r in scored:
        c = r['consequent']
        if c not in best_by_consequent or r['lift'] > best_by_consequent[c]['lift']:
            best_by_consequent[c] = r
    
    ordered = sorted(best_by_consequent.values(), key=lambda r: r['lift'], reverse=True)
    return {'customer': customer_id, 'recommendations': ordered[:top_n]}

