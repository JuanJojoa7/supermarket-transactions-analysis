from typing import Dict, Any
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import joblib
import os
from .ingestion import repo, RESULTS_DIR


def kmeans_segments(k: int = 4, random_state: int = 42, remove_outliers: bool = True) -> Dict[str, Any]:
    """
    Segmenta clientes usando K-means con normalización estándar.
    
    Args:
        k: Número de clusters
        random_state: Semilla para reproducibilidad
        remove_outliers: Si True, elimina outliers usando IQR antes de clustering
    
    Returns:
        Diccionario con clusters, centroides, asignaciones y descripciones
    """
    # Obtener características de clientes
    feats = repo.customer_features().copy()
    ids = feats['customer'].tolist()
    
    # Vectorizar: convertir DataFrame a matriz numpy
    X = feats.drop(columns=['customer']).values
    feature_names = feats.drop(columns=['customer']).columns.tolist()
    
    # Filtrar outliers usando IQR (rango intercuartílico)
    if remove_outliers:
        mask = np.ones(len(X), dtype=bool)
        for i, col in enumerate(feature_names):
            Q1 = np.percentile(X[:, i], 25)
            Q3 = np.percentile(X[:, i], 75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            mask &= (X[:, i] >= lower_bound) & (X[:, i] <= upper_bound)
        
        # Aplicar máscara
        X_filtered = X[mask]
        ids_filtered = [ids[i] for i in range(len(ids)) if mask[i]]
        removed_count = len(X) - len(X_filtered)
        
        print(f"Outliers removidos: {removed_count} ({removed_count/len(X)*100:.1f}%)")
    else:
        X_filtered = X
        ids_filtered = ids
    
    # Normalización: estandarizar features (media=0, std=1)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_filtered)
    
    # Aplicar K-means en datos normalizados
    km = KMeans(n_clusters=k, n_init=10, random_state=random_state)
    labels = km.fit_predict(X_scaled)
    
    # Guardar modelo y scaler para uso posterior
    os.makedirs(RESULTS_DIR, exist_ok=True)
    joblib.dump(km, os.path.join(RESULTS_DIR, 'kmeans_model.pkl'))
    joblib.dump(scaler, os.path.join(RESULTS_DIR, 'scaler.pkl'))
    
    # Invertir transformación para interpretar centroides
    centers = scaler.inverse_transform(km.cluster_centers_)
    centers_df = pd.DataFrame(centers, columns=feature_names)
    
    # Conteo por cluster
    counts = pd.Series(labels).value_counts().sort_index().to_dict()
    
    # Descripción heurística de cada cluster
    descriptions = {}
    business_recommendations = {}
    
    for c in range(k):
        center = centers_df.iloc[c]
        desc_parts = []
        recommendations = []
        
        # Clasificar frecuencia
        if center['frequency'] > centers_df['frequency'].quantile(0.75):
            desc_parts.append('Clientes muy frecuentes (top 25%)')
            freq_level = 'muy_alta'
        elif center['frequency'] > centers_df['frequency'].median():
            desc_parts.append('Clientes frecuentes')
            freq_level = 'alta'
        elif center['frequency'] > centers_df['frequency'].quantile(0.25):
            desc_parts.append('Clientes ocasionales')
            freq_level = 'media'
        else:
            desc_parts.append('Clientes esporádicos')
            freq_level = 'baja'
        
        # Clasificar volumen
        if center['total_items'] > centers_df['total_items'].quantile(0.75):
            desc_parts.append('compras de alto volumen')
            volume_level = 'alto'
        elif center['total_items'] > centers_df['total_items'].median():
            desc_parts.append('volumen medio de compra')
            volume_level = 'medio'
        else:
            desc_parts.append('compras pequeñas')
            volume_level = 'bajo'
        
        # Clasificar diversidad
        if center['distinct_products'] > centers_df['distinct_products'].quantile(0.75):
            desc_parts.append('gran variedad de productos')
            diversity_level = 'alta'
        elif center['distinct_products'] > centers_df['distinct_products'].median():
            diversity_level = 'media'
        else:
            diversity_level = 'baja'
        
        descriptions[c] = ', '.join(desc_parts) if desc_parts else 'Perfil estándar'
        
        # Generar recomendaciones de negocio específicas
        if freq_level == 'muy_alta' and volume_level == 'alto':
            recommendations += [
                '🎖️ Club VIP: Acceso anticipado a productos exclusivos',
                '🧠 Recomendaciones predictivas basadas en comportamiento',
                '🎀 Beneficios personalizados según categorías favoritas'
            ]

        elif freq_level == 'muy_alta' and volume_level == 'medio':
            recommendations += [
                '⭐ Programa de fidelización con recompensas escalonadas',
                '🔔 Promociones personalizadas en categorías recurrentes',
                '💳 Ofertas para incrementar el volumen promedio del ticket'
            ]

        elif freq_level == 'alta' and volume_level == 'bajo':
            recommendations += [
                '📈 Estrategias de upselling: Productos premium sugeridos',
                '🛒 Packs y combos de productos complementarios',
                '💰 Descuentos por niveles según monto de compra'
            ]

        elif freq_level == 'media' and volume_level == 'medio':
            recommendations += [
                '🎯 Campañas dirigidas para aumentar frecuencia mensual',
                '📅 Recordatorios basados en ciclos reales de compra',
                '🏆 Retos gamificados con premios por constancia'
            ]

        elif freq_level == 'baja' and volume_level == 'alto':
            recommendations += [
                '🔄 Re-engagement automatizado cuando se supera su ciclo natural',
                '📱 Notificaciones push segmentadas sobre productos ya comprados',
                '🎫 Descuentos progresivos para incentivar compras más frecuentes'
            ]

        else:  # baja frecuencia y bajo volumen
            recommendations += [
                '🎉 Activación inicial con descuentos fuertes en la próxima compra',
                '📬 Campañas de email con productos esenciales acorde al perfil',
                '🆓 Pruebas gratuitas y promociones de nuevos productos'
            ]

        # Recomendaciones adicionales según diversidad
        if diversity_level == 'alta':
            recommendations += [
                '🔍 Sistema de sugerencias basado en IA para explorar nuevas categorías'
            ]
        elif diversity_level == 'baja':
            recommendations += [
                '🌟 Incentivos para expandir categorías: cupones dirigidos a nuevos tipos de productos'
            ]
        
        business_recommendations[c] = recommendations
    
    # Asignar cada cliente a su cluster
    assignments = [{'customer': cid, 'cluster': int(lbl)} for cid, lbl in zip(ids_filtered, labels)]
    
    return {
        'k': k,
        'counts': counts,
        'centers': centers_df.round(2).to_dict(orient='records'),
        'assignments': assignments,
        'descriptions': descriptions,
        'business_recommendations': business_recommendations,
        'outliers_removed': removed_count if remove_outliers else 0,
        'total_customers': len(ids_filtered)
    }
