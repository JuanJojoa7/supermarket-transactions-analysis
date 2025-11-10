import os
import json
import pandas as pd
from .segmentation import kmeans_segments
from .recommender import get_rules
from .ingestion import repo

RESULTS_DIR = os.getenv('RESULTS_DIR', '/app/results')


def generate_insights(k: int = 4) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    seg = kmeans_segments(k=k)
    rules = get_rules()

    # Guardar como texto legible + JSON
    txt_path = os.path.join(RESULTS_DIR, 'business_insights.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write('=== RESUMEN DE SEGMENTACIÓN ===\n')
        f.write(f"Clusters: {seg['k']}\n")
        for cid, desc in seg['descriptions'].items():
            f.write(f"Cluster {cid}: {desc}\n")
        f.write('\n=== TOP REGLAS DE ASOCIACIÓN (por lift) ===\n')
        for i, r in enumerate(rules['rules'][:20], 1):
            f.write(f"{i}. {r['antecedent']} -> {r['consequent']} (lift={r['lift']:.3f}, conf={r['confidence']:.3f})\n")
    # JSON
    json_path = os.path.join(RESULTS_DIR, 'business_insights.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({'segmentation': seg, 'rules': rules}, f, ensure_ascii=False, indent=2)

    return txt_path
