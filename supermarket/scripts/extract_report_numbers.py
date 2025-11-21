#!/usr/bin/env python3
"""
Script reproducible para extraer métricas y resultados usados en el informe técnico.

Genera dos archivos JSON en el directorio de `RESULTS_DIR` definido por la app:
- `report_numbers.json`: métricas agregadas y tops (productos, clientes, días)
- `business_insights.json`: salida de segmentación (kmeans) y reglas de asociación

Ejecutar desde la raíz del proyecto (donde está la carpeta `backend`) con:
    python .\scripts\extract_report_numbers.py

Nota: el script asume que las dependencias del proyecto están instaladas y que
las rutas relativas del paquete `backend` son importables desde el directorio actual.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict

from backend.app.analytics.ingestion import repo, RESULTS_DIR
from backend.app.analytics.segmentation import kmeans_segments
from backend.app.analytics.recommender import initialize_rules, get_rules


def ensure_results_dir() -> str:
    out = RESULTS_DIR if RESULTS_DIR else os.path.join(os.getcwd(), "results")
    os.makedirs(out, exist_ok=True)
    return out


def summarize_basic_metrics() -> Dict[str, Any]:
    repo.refresh()
    data = repo.data

    total_transactions = len(data.transactions)
    total_units = int(data.transactions['num_products'].sum())
    unique_customers = int(data.transactions['customer'].nunique())
    unique_products = int(data.transactions_exploded['product_code'].nunique())

    # Top 10 productos por volumen
    top_products_series = repo.product_counts().head(10)
    top_products = [{'product_code': str(idx), 'count': int(v)} for idx, v in top_products_series.items()]

    # Top 10 clientes por número de transacciones
    cust_feats = repo.customer_features()
    top_clients_df = cust_feats.sort_values('frequency', ascending=False).head(10)
    top_clients = [{'customer': str(r['customer']), 'transactions': int(r['frequency'])} for _, r in top_clients_df.iterrows()]

    # Días pico: top 10 fechas por número de transacciones
    daily = data.transactions.groupby(data.transactions['date'].dt.strftime('%Y-%m-%d')).size().sort_values(ascending=False)
    top_days = [{'date': d, 'transactions': int(c)} for d, c in daily.head(10).items()]

    # Top 10 categorías por volumen (mapear id -> nombre cuando esté disponible)
    cat_counts = repo.category_counts().head(10)
    cat_map = data.categories.set_index('category_id')['category_name'].to_dict()
    top_categories = []
    for cid, cnt in cat_counts.items():
        name = cat_map.get(str(cid), str(cid))
        top_categories.append({'category_id': str(cid), 'category_name': name, 'count': int(cnt)})

    return {
        'total_transactions': total_transactions,
        'total_units': total_units,
        'unique_customers': unique_customers,
        'unique_products': unique_products,
        'top_products': top_products,
        'top_clients': top_clients,
        'top_days': top_days,
        'top_categories': top_categories,
    }


def gather_business_insights() -> Dict[str, Any]:
    insights: Dict[str, Any] = {}

    # Segmentation
    print("Running KMeans segmentation (k=4)...")
    k_res = kmeans_segments(k=4, random_state=42, remove_outliers=True)
    insights['kmeans'] = k_res

    # Association rules
    print("Initializing association rules (this may take a moment)...")
    initialize_rules()
    rules = get_rules()
    # Provide summary stats and top rules
    insights['rules_summary'] = {
        'num_rules': len(rules.get('rules', [])),
        'num_frequent_items': len(rules.get('frequent_items', {})),
        'top_rules': rules.get('rules', [])[:20]
    }

    return insights


def write_json(obj: Any, path: str) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main() -> None:
    out_dir = ensure_results_dir()
    report_path = os.path.join(out_dir, 'report_numbers.json')
    insights_path = os.path.join(out_dir, 'business_insights.json')

    print('Summarizing basic metrics...')
    report = summarize_basic_metrics()
    print(f'Writing {report_path}...')
    write_json(report, report_path)

    print('Gathering business insights...')
    insights = gather_business_insights()
    print(f'Writing {insights_path}...')
    write_json(insights, insights_path)

    print('\nDone. Generated the following files:')
    print(f' - {report_path}')
    print(f' - {insights_path}')


if __name__ == '__main__':
    main()
