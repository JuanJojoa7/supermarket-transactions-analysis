import os
import json
import pandas as pd
from .segmentation import kmeans_segments
from .recommender import get_rules
from .ingestion import repo

RESULTS_DIR = os.getenv('RESULTS_DIR', '/app/results')


def generate_insights(k: int = 4) -> str:
    """
    Genera insights de negocio consolidando segmentación y reglas de asociación.
    Guarda resultados en formato texto y JSON.
    
    Args:
        k: Número de clusters para segmentación
    
    Returns:
        Ruta del archivo de texto generado
    """
    os.makedirs(RESULTS_DIR, exist_ok=True)
    seg = kmeans_segments(k=k)
    rules = get_rules()

    # Guardar como texto legible
    txt_path = os.path.join(RESULTS_DIR, 'business_insights.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write('=== RESUMEN DE SEGMENTACIÓN DE CLIENTES ===\n')
        f.write(f"Número de clusters: {seg['k']}\n\n")
        for cid, desc in seg['descriptions'].items():
            count = seg['counts'][int(cid)]
            f.write(f"Cluster {cid} ({count} clientes): {desc}\n")
        
        f.write('\n=== TOP 20 REGLAS DE ASOCIACIÓN (ordenadas por lift) ===\n')
        f.write('(Lift > 1 indica que los productos se compran juntos más frecuentemente que por azar)\n\n')
        for i, r in enumerate(rules['rules'][:20], 1):
            cat_info = f" [{r.get('antecedent_category', 'N/A')} → {r.get('consequent_category', 'N/A')}]"
            f.write(f"{i}. {r['antecedent']} → {r['consequent']}{cat_info}\n")
            f.write(f"   Lift: {r['lift']:.3f} | Confianza: {r['confidence']:.3f} | Soporte: {r['support']:.4f}\n")
    
    # Guardar como JSON estructurado
    json_path = os.path.join(RESULTS_DIR, 'business_insights.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({'segmentation': seg, 'rules': rules}, f, ensure_ascii=False, indent=2)

    return txt_path
