import os
import glob
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np

# Default dataset root inside container
DATASET_DIR = os.getenv("DATASET_DIR", "/app/dataset")
RESULTS_DIR = os.getenv("RESULTS_DIR", "/app/results")

@dataclass
class LoadedData:
    categories: pd.DataFrame
    product_category: pd.DataFrame
    transactions: pd.DataFrame
    transactions_exploded: pd.DataFrame
    product_to_category: Dict[str, str]


def _read_categories(dataset_dir: str) -> pd.DataFrame:
    path = os.path.join(dataset_dir, "Products", "Categories.csv")
    df = pd.read_csv(path, sep='|', header=None, names=['category_id', 'category_name'])
    df['category_id'] = df['category_id'].astype(str)
    return df


def _read_product_category(dataset_dir: str) -> pd.DataFrame:
    path = os.path.join(dataset_dir, "Products", "ProductCategory.csv")
    df = pd.read_csv(path, sep='|', header=None, names=['product_code', 'category_id'])
    df['product_code'] = df['product_code'].astype(str)
    df['category_id'] = df['category_id'].astype(str)
    return df


def _read_transactions(dataset_dir: str) -> pd.DataFrame:
    tx_files = glob.glob(os.path.join(dataset_dir, "Transactions", "*.csv"))
    frames: List[pd.DataFrame] = []
    for fp in tx_files:
        part = pd.read_csv(fp, sep='|', header=None, names=['date', 'store', 'customer', 'products'])
        frames.append(part)
    if not frames:
        raise FileNotFoundError("No se encontraron archivos en Transactions/*.csv")
    tx = pd.concat(frames, ignore_index=True)
    tx['date'] = pd.to_datetime(tx['date'])
    tx['store'] = tx['store'].astype(str)
    tx['customer'] = tx['customer'].astype(str)
    tx['products_list'] = tx['products'].fillna("").astype(str).str.split()
    tx['num_products'] = tx['products_list'].apply(len)
    tx['year'] = tx['date'].dt.year
    tx['month'] = tx['date'].dt.month
    tx['week'] = tx['date'].dt.isocalendar().week.astype(int)
    tx['day_of_week'] = tx['date'].dt.dayofweek
    tx['day_name'] = tx['date'].dt.day_name()
    return tx


def load_all(dataset_dir: Optional[str] = None) -> LoadedData:
    """Carga datasets y construye vistas derivadas útiles."""
    root = dataset_dir or DATASET_DIR
    categories = _read_categories(root)
    prod_cat = _read_product_category(root)
    tx = _read_transactions(root)

    # Explode productos
    exploded = tx[['date', 'store', 'customer', 'products_list']].explode('products_list')
    exploded = exploded.rename(columns={'products_list': 'product_code'})
    exploded['product_code'] = exploded['product_code'].astype(str)

    # Mapear a categoría
    product_to_category = prod_cat.set_index('product_code')['category_id'].to_dict()
    exploded['category_id'] = exploded['product_code'].map(product_to_category)

    return LoadedData(
        categories=categories,
        product_category=prod_cat,
        transactions=tx,
        transactions_exploded=exploded,
        product_to_category=product_to_category,
    )


class DataRepository:
    """Repositorio en memoria con caché simple y utilidades de features."""
    def __init__(self, dataset_dir: Optional[str] = None) -> None:
        self.dataset_dir = dataset_dir or DATASET_DIR
        self._data: Optional[LoadedData] = None
        self._customer_features: Optional[pd.DataFrame] = None
        self._category_counts: Optional[pd.Series] = None
        self._product_counts: Optional[pd.Series] = None

    def refresh(self) -> None:
        self._data = load_all(self.dataset_dir)
        self._customer_features = None
        self._category_counts = None
        self._product_counts = None

    @property
    def data(self) -> LoadedData:
        if self._data is None:
            self.refresh()
        return self._data  # type: ignore

    def product_counts(self) -> pd.Series:
        if self._product_counts is None:
            s = self.data.transactions_exploded['product_code'].value_counts()
            self._product_counts = s
        return self._product_counts

    def category_counts(self) -> pd.Series:
        if self._category_counts is None:
            s = self.data.transactions_exploded['category_id'].value_counts()
            self._category_counts = s
        return self._category_counts

    def customer_features(self) -> pd.DataFrame:
        if self._customer_features is None:
            tx = self.data.transactions
            ex = self.data.transactions_exploded
            # Frecuencia (#transacciones)
            freq = tx.groupby('customer').size().rename('frequency')
            # Total items
            total_items = tx.groupby('customer')['num_products'].sum().rename('total_items')
            # Distintos productos
            distinct_products = ex.groupby('customer')['product_code'].nunique().rename('distinct_products')
            # Distintas categorías
            distinct_categories = ex.groupby('customer')['category_id'].nunique().fillna(0).rename('distinct_categories')
            # Tamaño promedio del carrito
            avg_basket = (total_items / freq).rename('avg_basket_size')
            features = pd.concat([freq, total_items, distinct_products, distinct_categories, avg_basket], axis=1).fillna(0)
            self._customer_features = features.reset_index()
        return self._customer_features

# Singleton para uso del API
repo = DataRepository()
