import os
import pandas as pd
from app.analytics.ingestion import repo, DataRepository
from app.analytics.metrics import executive_summary, time_series, boxplot_data, heatmap_features


def test_load_and_summary():
    # Asegura que carga sin excepción y retorna llaves esperadas
    repo.refresh()
    summary = executive_summary()
    assert 'total_units' in summary
    assert 'num_transactions' in summary
    assert isinstance(summary['top_products'], dict)


def test_time_series_levels():
    daily = time_series('daily')
    weekly = time_series('weekly')
    monthly = time_series('monthly')
    assert isinstance(daily, dict) and isinstance(weekly, dict) and isinstance(monthly, dict)


def test_boxplot_customer():
    data = boxplot_data('customer')
    assert 'series' in data and 'describe' in data


def test_heatmap_features():
    hm = heatmap_features()
    assert 'columns' in hm and 'matrix' in hm
