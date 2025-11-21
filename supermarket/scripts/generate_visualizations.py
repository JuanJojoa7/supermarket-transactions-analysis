#!/usr/bin/env python3
"""
Genera visualizaciones analíticas y datos agregados para el informe.

Salida:
 - results/plots/timeseries_daily.png
 - results/plots/timeseries_weekly.png
 - results/plots/boxplot_customers.png
 - results/plots/boxplot_categories.png
 - results/plots/heatmap_features.png
 - results/plots/*.csv (agregados utilizados)

Ejecutar desde la raíz del proyecto:
  $env:DATASET_DIR = $PWD
  $env:RESULTS_DIR = (Join-Path $PWD 'results')
  $env:PYTHONPATH = $PWD
  python .\scripts\generate_visualizations.py

Requiere: pandas, matplotlib, seaborn, backend package importable (ejecutar desde carpeta raíz del repo).
"""
import os
import json
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from backend.app.analytics.ingestion import repo, RESULTS_DIR


def ensure_out_dirs(base: str) -> str:
    out = base or os.path.join(os.getcwd(), 'results')
    plots = os.path.join(out, 'plots')
    os.makedirs(plots, exist_ok=True)
    return plots


def save_csv(df: pd.DataFrame, path: str) -> None:
    df.to_csv(path, index=True)


def timeseries_plots(tx: pd.DataFrame, out_dir: str) -> None:
    # Daily aggregates
    daily = tx.groupby(tx['date'].dt.strftime('%Y-%m-%d')).agg(
        transactions=('customer', 'size'),
        total_products=('num_products', 'sum')
    )
    daily.index = pd.to_datetime(daily.index)
    daily = daily.sort_index()
    save_csv(daily, os.path.join(out_dir, 'timeseries_daily.csv'))

    plt.figure(figsize=(12,5))
    ax = daily['total_products'].plot(title='Evolución diaria de unidades vendidas', color='tab:blue')
    ax.set_xlabel('Fecha')
    ax.set_ylabel('Unidades vendidas')
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'timeseries_daily.png'))
    plt.close()

    # Weekly aggregates (ISO week)
    weekly = tx.set_index('date').resample('W-MON').agg(
        transactions=('customer', 'size'),
        total_products=('num_products', 'sum')
    )
    save_csv(weekly, os.path.join(out_dir, 'timeseries_weekly.csv'))

    plt.figure(figsize=(12,5))
    ax = weekly['total_products'].plot(title='Evolución semanal de unidades vendidas', color='tab:blue', marker='o')
    ax.set_xlabel('Semana')
    ax.set_ylabel('Unidades vendidas')
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'timeseries_weekly.png'))
    plt.close()


def boxplots(tx: pd.DataFrame, exploded: pd.DataFrame, out_dir: str) -> None:
    # Boxplot: distribución de totales por cliente (total_items por cliente)
    cust = tx.groupby('customer')['num_products'].sum().rename('total_items')
    cust_df = cust.to_frame()
    save_csv(cust_df, os.path.join(out_dir, 'boxplot_customers.csv'))

    plt.figure(figsize=(8,6))
    sns.boxplot(x=cust_df['total_items'])
    plt.title('Distribución de unidades totales por cliente')
    plt.xlabel('Total unidades por cliente')
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'boxplot_customers.png'))
    plt.close()

    # Boxplot por categoría: total unidades por categoría (agregado global)
    cat_counts = exploded.groupby('category_id').size().rename('count').sort_values(ascending=False)
    cat_df = cat_counts.to_frame()
    save_csv(cat_df, os.path.join(out_dir, 'boxplot_categories.csv'))

    # For boxplot we need distribution over categories — use log scale if skewed
    plt.figure(figsize=(10,6))
    sns.barplot(x=cat_df['count'].values, y=cat_df.index.astype(str), palette='viridis')
    plt.title('Volumen por categoría (top categories)')
    plt.xlabel('Unidades vendidas')
    plt.ylabel('Category ID')
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'boxplot_categories.png'))
    plt.close()


def heatmap_features(out_dir: str) -> None:
    feats = repo.customer_features().set_index('customer')
    corr = feats.select_dtypes(include=['number']).corr()
    save_csv(corr, os.path.join(out_dir, 'features_correlation.csv'))

    plt.figure(figsize=(8,6))
    sns.heatmap(corr, annot=True, fmt='.2f', cmap='vlag', center=0)
    plt.title('Correlación entre features de cliente')
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'heatmap_features.png'))
    plt.close()


def main():
    # Asegurar que los datos estén cargados
    repo.refresh()
    data = repo.data
    plots_dir = ensure_out_dirs(RESULTS_DIR)

    print('Generando series temporales...')
    timeseries_plots(data.transactions, plots_dir)

    print('Generando boxplots y agregados por cliente/categoría...')
    boxplots(data.transactions, data.transactions_exploded, plots_dir)

    print('Generando heatmap de correlaciones...')
    heatmap_features(plots_dir)

    print('\nVisualizaciones generadas en:', plots_dir)


if __name__ == '__main__':
    main()
