import os
import glob
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any
import pandas as pd
import numpy as np
from datetime import datetime

# Default dataset root inside container
DATASET_DIR = os.getenv("DATASET_DIR", "/app/dataset")
RESULTS_DIR = os.getenv("RESULTS_DIR", "/app/results")

@dataclass
class LoadedData:
    """Contenedor de datos cargados del dataset."""
    categories: pd.DataFrame
    product_category: pd.DataFrame
    transactions: pd.DataFrame
    transactions_exploded: pd.DataFrame
    product_to_category: Dict[str, str]


def _read_categories(dataset_dir: str) -> pd.DataFrame:
    """Carga el catálogo de categorías desde Products/Categories.csv."""
    path = os.path.join(dataset_dir, "Products", "Categories.csv")
    df = pd.read_csv(path, sep='|', header=None, names=['category_id', 'category_name'])
    df['category_id'] = df['category_id'].astype(str)
    return df


def _read_product_category(dataset_dir: str) -> pd.DataFrame:
    """Carga la relación producto-categoría desde Products/ProductCategory.csv."""
    path = os.path.join(dataset_dir, "Products", "ProductCategory.csv")
    # Saltar primera línea que es header (v.Code_pr|v.code)
    df = pd.read_csv(path, sep='|', header=None, names=['product_code', 'category_id'], skiprows=1)
    df['product_code'] = df['product_code'].astype(str)
    df['category_id'] = df['category_id'].astype(str)
    return df


def _read_transactions(dataset_dir: str) -> pd.DataFrame:
    """
    Carga todas las transacciones desde Transactions/*.csv.
    Agrega features temporales y de conteo de productos.
    """
    tx_files = glob.glob(os.path.join(dataset_dir, "Transactions", "*.csv"))
    frames: List[pd.DataFrame] = []
    for fp in tx_files:
        part = pd.read_csv(fp, sep='|', header=None, names=['date', 'store', 'customer', 'products'])
        frames.append(part)
    if not frames:
        raise FileNotFoundError("No se encontraron archivos en Transactions/*.csv")
    tx = pd.concat(frames, ignore_index=True)
    
    # Parsear fechas con manejo robusto de diferentes formatos
    try:
        tx['date'] = pd.to_datetime(tx['date'], infer_datetime_format=True)
    except:
        tx['date'] = pd.to_datetime(tx['date'], errors='coerce')
    
    # Eliminar filas con fechas inválidas
    tx = tx.dropna(subset=['date'])
    
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
    """
    Repositorio en memoria para datos del supermercado.
    Cachea datos y características calculadas para optimizar rendimiento.
    """
    def __init__(self, dataset_dir: Optional[str] = None) -> None:
        self.dataset_dir = dataset_dir or DATASET_DIR
        self._data: Optional[LoadedData] = None
        self._customer_features: Optional[pd.DataFrame] = None
        self._category_counts: Optional[pd.Series] = None
        self._product_counts: Optional[pd.Series] = None

    def refresh(self) -> None:
        """Recarga los datos desde disco y limpia el caché."""
        self._data = load_all(self.dataset_dir)
        self._customer_features = None
        self._category_counts = None
        self._product_counts = None

    @property
    def data(self) -> LoadedData:
        """Acceso lazy a los datos cargados."""
        if self._data is None:
            self.refresh()
        return self._data  # type: ignore

    def product_counts(self) -> pd.Series:
        """Obtiene conteo de productos ordenado por frecuencia."""
        if self._product_counts is None:
            s = self.data.transactions_exploded['product_code'].value_counts()
            self._product_counts = s
        return self._product_counts

    def category_counts(self) -> pd.Series:
        """Obtiene conteo de categorías ordenado por frecuencia."""
        if self._category_counts is None:
            s = self.data.transactions_exploded['category_id'].value_counts()
            self._category_counts = s
        return self._category_counts

    def customer_features(self) -> pd.DataFrame:
        """
        Calcula features agregadas de clientes para segmentación.
        Features: frecuencia, total_items, distinct_products, distinct_categories, avg_basket_size.
        """
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


def process_new_transactions(csv_content: str, store_id: str = "999") -> Dict[str, Any]:
    """
    Procesa nuevas transacciones desde un CSV subido.
    Pipeline completo: validación, limpieza, normalización y guardado.
    
    Args:
        csv_content: Contenido del archivo CSV
        store_id: ID de la tienda (default: 999 para transacciones manuales)
    
    Returns:
        Diccionario con estadísticas del procesamiento
    """
    from io import StringIO
    
    # 1. Cargar y validar - detectar automáticamente si tiene columna store
    first_line = csv_content.split('\n')[0]
    num_columns = len(first_line.split('|'))
    
    if num_columns == 4:
        # Formato completo: date|store|customer|products
        df = pd.read_csv(StringIO(csv_content), sep='|', header=None, 
                         names=['date', 'store', 'customer', 'products'])
    elif num_columns == 3:
        # Formato simplificado: date|customer|products
        df = pd.read_csv(StringIO(csv_content), sep='|', header=None, 
                         names=['date', 'customer', 'products'])
        df['store'] = store_id
    else:
        return {
            'status': 'error',
            'message': f'Formato inválido: se esperaban 3 o 4 columnas, se encontraron {num_columns}'
        }
    
    initial_count = len(df)
    
    # 2. Limpieza de datos
    # Eliminar filas vacías o con datos inválidos
    df = df.dropna(subset=['date', 'customer'])
    df = df[df['products'].notna() & (df['products'].str.strip() != '')]
    
    # Validar formato de fecha
    try:
        df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d')
    except:
        try:
            df['date'] = pd.to_datetime(df['date'], infer_datetime_format=True)
        except:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
    
    df = df.dropna(subset=['date'])
    
    # 3. Normalización
    df['store'] = df['store'].astype(int)
    df['customer'] = df['customer'].astype(str).str.strip()
    df['products'] = df['products'].astype(str).str.strip()
    
    # Reordenar columnas al formato estándar
    df = df[['date', 'store', 'customer', 'products']]
    
    # 4. Guardar en archivo de transacciones
    transactions_dir = os.path.join(DATASET_DIR, "Transactions")
    os.makedirs(transactions_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(transactions_dir, f"{int(df['store'].iloc[0])}_Tran_{timestamp}.csv")
    
    # Guardar con formato simple de fecha (YYYY-MM-DD) como archivos originales
    df['date'] = df['date'].dt.strftime('%Y-%m-%d')
    df.to_csv(output_file, sep='|', header=False, index=False)
    
    cleaned_count = len(df)
    rejected_count = initial_count - cleaned_count
    
    return {
        'status': 'success',
        'file': output_file,
        'initial_rows': initial_count,
        'cleaned_rows': cleaned_count,
        'rejected_rows': rejected_count,
        'message': f'Se procesaron {cleaned_count} transacciones exitosamente'
    }
