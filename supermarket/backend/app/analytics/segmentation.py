from typing import Dict, Any
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from .ingestion import repo


def kmeans_segments(k: int = 4, random_state: int = 42) -> Dict[str, Any]:
    feats = repo.customer_features().copy()
    ids = feats['customer'].tolist()
    X = feats.drop(columns=['customer']).values
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    km = KMeans(n_clusters=k, n_init=10, random_state=random_state)
    labels = km.fit_predict(Xs)

    centers = scaler.inverse_transform(km.cluster_centers_)
    centers_df = pd.DataFrame(centers, columns=feats.drop(columns=['customer']).columns)

    # Conteo por cluster
    counts = pd.Series(labels).value_counts().sort_index().to_dict()

    # Descripción simple (heurística)
    descriptions = {}
    cols = centers_df.columns
    for c in range(k):
        center = centers_df.iloc[c]
        desc_parts = []
        if center['frequency'] > centers_df['frequency'].median():
            desc_parts.append('Alta frecuencia')
        else:
            desc_parts.append('Baja frecuencia')
        if center['total_items'] > centers_df['total_items'].median():
            desc_parts.append('alto volumen')
        if center['distinct_products'] > centers_df['distinct_products'].median():
            desc_parts.append('alta diversidad de productos')
        if center['distinct_categories'] > centers_df['distinct_categories'].median():
            desc_parts.append('variedad de categorías')
        descriptions[c] = ', '.join(desc_parts)

    assignments = [{'customer': cid, 'cluster': int(lbl)} for cid, lbl in zip(ids, labels)]

    return {
        'k': k,
        'counts': counts,
        'centers': centers_df.round(2).to_dict(orient='records'),
        'assignments': assignments,
        'descriptions': descriptions,
    }
