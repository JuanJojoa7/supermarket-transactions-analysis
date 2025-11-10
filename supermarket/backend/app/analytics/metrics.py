from typing import Dict, Any
import pandas as pd
from .ingestion import repo


def executive_summary() -> Dict[str, Any]:
    data = repo.data
    tx = data.transactions
    ex = data.transactions_exploded

    total_units = int(ex.shape[0])  # total productos (unit = producto)
    num_transactions = int(tx.shape[0])
    top_products = ex['product_code'].value_counts().head(10).to_dict()
    top_clients = tx['customer'].value_counts().head(10).to_dict()

    # Días pico (por número de transacciones)
    daily = tx.groupby('date').size().rename('transactions')
    peak_days = daily.sort_values(ascending=False).head(10)
    peak_days_dict = {str(d.date()): int(v) for d, v in peak_days.items()}

    # Categorías "más rentables" => usamos volumen relativo
    ex['category_id'] = ex['category_id'].fillna('UNKNOWN')
    cat_counts = ex['category_id'].value_counts()
    cat_freq_rel = (cat_counts / cat_counts.sum()).head(10)
    top_categories = cat_freq_rel.round(4).to_dict()

    return {
        'total_units': total_units,
        'num_transactions': num_transactions,
        'top_products': top_products,
        'top_clients': top_clients,
        'peak_days': peak_days_dict,
        'top_categories_relative_volume': top_categories,
    }


def time_series(level: str = 'daily') -> Dict[str, Any]:
    tx = repo.data.transactions.copy()
    tx['num_products'] = tx['num_products']
    if level == 'daily':
        grp = tx.groupby('date').agg(num_transactions=('customer', 'count'), total_products=('num_products', 'sum'))
    elif level == 'weekly':
        grp = tx.groupby(['year', 'week']).agg(num_transactions=('customer', 'count'), total_products=('num_products', 'sum'))
    elif level == 'monthly':
        grp = tx.groupby(['year', 'month']).agg(num_transactions=('customer', 'count'), total_products=('num_products', 'sum'))
    else:
        raise ValueError('level debe ser daily|weekly|monthly')
    return {str(k): v for k, v in grp.to_dict('index').items()}


def boxplot_data(by: str = 'customer') -> Dict[str, Any]:
    ex = repo.data.transactions_exploded
    tx = repo.data.transactions
    if by == 'customer':
        agg = tx.groupby('customer')['num_products'].sum()
    elif by == 'category':
        agg = ex.groupby('category_id').size()
    else:
        raise ValueError('by debe ser customer|category')
    desc = agg.describe().to_dict()
    return {'series': agg.tolist(), 'describe': desc}


def heatmap_features() -> Dict[str, Any]:
    feats = repo.customer_features().drop(columns=['customer'])
    corr = feats.corr().round(4)
    return {'columns': corr.columns.tolist(), 'matrix': corr.values.tolist()}
