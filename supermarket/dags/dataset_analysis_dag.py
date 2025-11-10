from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import pandas as pd
import os
import glob
import matplotlib.pyplot as plt
from itertools import combinations
from collections import defaultdict, Counter
import numpy as np

DATA_DIR = "/opt/airflow/data"
DATASET_DIR = "/opt/airflow/dataset"
RESULTS_DIR = "/opt/airflow/results"

default_args = {
    "owner": "JojoaGonzalez",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(seconds=30),
}


def load_data(**context):
    """
    Carga todos los archivos CSV del dataset.
    """
    # Cargar el dataset Categories
    categories_path = os.path.join(DATASET_DIR, "Products", "Categories.csv")
    categories_df = pd.read_csv(categories_path, sep='|', header=None, names=['category_id', 'category_name'])

    # Cargar el dataset ProductCategory
    product_category_path = os.path.join(DATASET_DIR, "Products", "ProductCategory.csv")
    product_category_df = pd.read_csv(product_category_path, sep='|', header=None, names=['product_code', 'category_id'])

    # Cargar el dataset Transactions (todos los csv)
    transactions_files = glob.glob(os.path.join(DATASET_DIR, "Transactions", "*.csv"))
    transactions_list = []
    for file in transactions_files:
        df = pd.read_csv(file, sep='|', header=None, names=['date', 'store', 'customer', 'products'])
        transactions_list.append(df)
    transactions_df = pd.concat(transactions_list, ignore_index=True)
    
    # Convertir fecha a datetime y crear variables temporales
    transactions_df['date'] = pd.to_datetime(transactions_df['date'])
    transactions_df['year'] = transactions_df['date'].dt.year
    transactions_df['month'] = transactions_df['date'].dt.month
    transactions_df['week'] = transactions_df['date'].dt.isocalendar().week
    transactions_df['day_of_week'] = transactions_df['date'].dt.dayofweek
    transactions_df['day_name'] = transactions_df['date'].dt.day_name()
    
    # Convertir store y customer a categóricas (son IDs, no variables numéricas continuas)
    transactions_df['store'] = transactions_df['store'].astype(str)
    transactions_df['customer'] = transactions_df['customer'].astype(str)
    
    # Guardar en XCom (para pasar a las siguientes tareas)
    context['ti'].xcom_push(key='categories_df', value=categories_df.to_json())
    context['ti'].xcom_push(key='product_category_df', value=product_category_df.to_json())
    context['ti'].xcom_push(key='transactions_df', value=transactions_df.to_json(date_format='iso'))
    
    print(f"Loaded {len(categories_df)} categories, {len(product_category_df)} product categories, {len(transactions_df)} transactions")


def data_review(**context):
    """
    Realiza revisión inicial del dataset: estructura, tipos, nulos, duplicados.
    """
    categories_json = context['ti'].xcom_pull(key='categories_df')
    product_category_json = context['ti'].xcom_pull(key='product_category_df')
    transactions_json = context['ti'].xcom_pull(key='transactions_df')
    
    categories_df = pd.read_json(categories_json)
    product_category_df = pd.read_json(product_category_json)
    transactions_df = pd.read_json(transactions_json)
    
    review_results = {}
    
    # Categories
    review_results['categories'] = {
        'num_records': len(categories_df),
        'num_columns': len(categories_df.columns),
        'columns': categories_df.columns.tolist(),
        'dtypes': {k: str(v) for k, v in categories_df.dtypes.to_dict().items()},
        'nulls': categories_df.isnull().sum().to_dict(),
        'duplicates': int(categories_df.duplicated().sum())
    }
    
    # ProductCategory
    review_results['product_category'] = {
        'num_records': len(product_category_df),
        'num_columns': len(product_category_df.columns),
        'columns': product_category_df.columns.tolist(),
        'dtypes': {k: str(v) for k, v in product_category_df.dtypes.to_dict().items()},
        'nulls': product_category_df.isnull().sum().to_dict(),
        'duplicates': int(product_category_df.duplicated().sum())
    }
    
    # Transactions
    review_results['transactions'] = {
        'num_records': len(transactions_df),
        'num_columns': len(transactions_df.columns),
        'columns': transactions_df.columns.tolist(),
        'dtypes': {k: str(v) for k, v in transactions_df.dtypes.to_dict().items()},
        'nulls': transactions_df.isnull().sum().to_dict(),
        'duplicates': int(transactions_df.duplicated().sum())
    }
    
    # Imprimir resultados en consola (para logs)
    for table, stats in review_results.items():
        print(f"\n=== {table.upper()} ===")
        for key, value in stats.items():
            print(f"{key}: {value}")
    
    context['ti'].xcom_push(key='review_results', value=review_results)


def descriptive_stats(**context):
    """
    Calcula estadísticas descriptivas.
    """
    categories_json = context['ti'].xcom_pull(key='categories_df')
    product_category_json = context['ti'].xcom_pull(key='product_category_df')
    transactions_json = context['ti'].xcom_pull(key='transactions_df')
    
    categories_df = pd.read_json(categories_json)
    product_category_df = pd.read_json(product_category_json)
    transactions_df = pd.read_json(transactions_json)
    
    stats_results = {}
    
    # Para Transactions: expandir productos y calcular estadísticas
    transactions_expanded = transactions_df.copy()
    transactions_expanded['num_products'] = transactions_expanded['products'].str.split().str.len()
    
    # Estadísticas numéricas solo para num_products (store y customer son categóricas)
    numeric_vars = ['num_products']
    stats_results['numeric'] = {}
    for var in numeric_vars:
        desc = transactions_expanded[[var]].describe(percentiles=[0.25, 0.5, 0.75])
        mode = transactions_expanded[var].mode().tolist()
        stats_results['numeric'][var] = {
            'describe': desc.to_dict(),
            'mode': mode
        }
    
    # Detectar outliers usando IQR para num_products
    stats_results['outliers'] = {}
    for var in numeric_vars:
        Q1 = transactions_expanded[var].quantile(0.25)
        Q3 = transactions_expanded[var].quantile(0.75)
        IQR = Q3 - Q1
        outliers = transactions_expanded[(transactions_expanded[var] < (Q1 - 1.5 * IQR)) | (transactions_expanded[var] > (Q3 + 1.5 * IQR))]
        stats_results['outliers'][var] = {
            'count': int(len(outliers)),
            'min_outlier': float(outliers[var].min()) if len(outliers) > 0 else None,
            'max_outlier': float(outliers[var].max()) if len(outliers) > 0 else None
        }
    
    # Estadísticas categóricas (categorías)
    category_counts = product_category_df['category_id'].value_counts()
    category_freq = (category_counts / len(product_category_df) * 100).round(2)
    stats_results['categorical'] = {
        'category_counts': category_counts.to_dict(),
        'category_frequencies': category_freq.to_dict()
    }
    
    # Frecuencia de productos (top 20)
    all_products = []
    for products in transactions_df['products']:
        all_products.extend(products.split())
    product_counts = pd.Series(all_products).value_counts()
    stats_results['product_frequencies'] = product_counts.head(20).to_dict()
    
    # Frecuencias para store (ahora categórica)
    store_counts = transactions_df['store'].value_counts()
    store_freq = (store_counts / len(transactions_df) * 100).round(2)
    stats_results['store_frequencies'] = {
        'counts': store_counts.to_dict(),
        'frequencies': store_freq.to_dict()
    }
    
    # Imprimir resultados
    print("\n=== ESTADÍSTICAS NUMÉRICAS ===")
    for var, stats in stats_results['numeric'].items():
        print(f"\n--- {var.upper()} ---")
        desc_df = pd.DataFrame(stats['describe'])
        print(desc_df)
        print(f"Moda: {stats['mode']}")
        print(f"Outliers: {stats_results['outliers'][var]}")
    
    print("\n=== ESTADÍSTICAS CATEGÓRICAS ===")
    print("Top categorías:")
    for cat, count in list(category_counts.items())[:10]:
        print(f"Categoría {cat}: {count} productos ({category_freq[cat]}%)")
    
    print("\nTop productos:")
    for prod, count in list(product_counts.items())[:10]:
        print(f"Producto {prod}: {count} veces")
    
    print("\nTop stores:")
    for store, count in list(store_counts.items())[:10]:
        print(f"Store {store}: {count} transacciones ({store_freq[store]}%)")
    
    context['ti'].xcom_push(key='stats_results', value=stats_results)


def temporal_analysis(**context):
    """
    Analiza patrones temporales en las ventas.
    """
    transactions_json = context['ti'].xcom_pull(key='transactions_df')
    transactions_df = pd.read_json(transactions_json)
    
    transactions_df['date'] = pd.to_datetime(transactions_df['date'])
    transactions_df['num_products'] = transactions_df['products'].str.split().str.len()
    
    temporal_results = {}
    
    # Ventas diarias
    daily_sales = transactions_df.groupby('date').agg({
        'customer': 'count',
        'num_products': 'sum'
    }).rename(columns={'customer': 'num_transactions', 'num_products': 'total_products'})
    temporal_results['daily_sales'] = {str(k): v for k, v in daily_sales.to_dict('index').items()}
    
    # Ventas semanales
    weekly_sales = transactions_df.groupby(['year', 'week']).agg({
        'customer': 'count',
        'num_products': 'sum'
    }).rename(columns={'customer': 'num_transactions', 'num_products': 'total_products'})
    temporal_results['weekly_sales'] = {str(k): v for k, v in weekly_sales.to_dict('index').items()}
    
    # Ventas mensuales
    monthly_sales = transactions_df.groupby(['year', 'month']).agg({
        'customer': 'count',
        'num_products': 'sum'
    }).rename(columns={'customer': 'num_transactions', 'num_products': 'total_products'})
    temporal_results['monthly_sales'] = {str(k): v for k, v in monthly_sales.to_dict('index').items()}
    
    # Ventas por día de la semana
    day_of_week_sales = transactions_df.groupby('day_name').agg({
        'customer': 'count',
        'num_products': 'sum'
    }).rename(columns={'customer': 'num_transactions', 'num_products': 'total_products'})
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    day_of_week_sales = day_of_week_sales.reindex(day_order)
    temporal_results['day_of_week_sales'] = day_of_week_sales.to_dict('index')
    
    # Estadísticas de tendencia
    daily_sales_stats = {
        'mean_daily_transactions': float(daily_sales['num_transactions'].mean()),
        'max_daily_transactions': int(daily_sales['num_transactions'].max()),
        'min_daily_transactions': int(daily_sales['num_transactions'].min()),
        'std_daily_transactions': float(daily_sales['num_transactions'].std())
    }
    temporal_results['daily_stats'] = daily_sales_stats
    
    print("\n=== ANÁLISIS TEMPORAL ===")
    print(f"\nEstadísticas diarias:")
    print(f"Media de transacciones diarias: {daily_sales_stats['mean_daily_transactions']:.2f}")
    print(f"Máximo de transacciones en un día: {daily_sales_stats['max_daily_transactions']}")
    print(f"Mínimo de transacciones en un día: {daily_sales_stats['min_daily_transactions']}")
    
    print(f"\nVentas por día de la semana:")
    for day, stats in day_of_week_sales.iterrows():
        print(f"{day}: {stats['num_transactions']} transacciones, {stats['total_products']} productos")
    
    context['ti'].xcom_push(key='temporal_results', value=temporal_results)


def customer_analysis(**context):
    """
    Analiza patrones de comportamiento de clientes.
    """
    transactions_json = context['ti'].xcom_pull(key='transactions_df')
    transactions_df = pd.read_json(transactions_json)
    
    transactions_df['date'] = pd.to_datetime(transactions_df['date'])
    transactions_df['num_products'] = transactions_df['products'].str.split().str.len()
    
    customer_results = {}
    
    # Frecuencia de compra por cliente
    customer_freq = transactions_df.groupby('customer').size()
    customer_results['purchase_frequency'] = {
        'mean': float(customer_freq.mean()),
        'median': float(customer_freq.median()),
        'std': float(customer_freq.std()),
        'max': int(customer_freq.max()),
        'min': int(customer_freq.min())
    }
    
    # Tiempo promedio entre compras
    customer_dates = transactions_df.groupby('customer')['date'].apply(lambda x: x.sort_values().tolist())
    time_between_purchases = []
    for customer, dates in customer_dates.items():
        if isinstance(dates, list) and len(dates) > 1:
            for i in range(1, len(dates)):
                diff = (dates[i] - dates[i-1]).days
                time_between_purchases.append(diff)
    
    if time_between_purchases:
        customer_results['time_between_purchases'] = {
            'mean_days': float(np.mean(time_between_purchases)),
            'median_days': float(np.median(time_between_purchases)),
            'std_days': float(np.std(time_between_purchases))
        }
    else:
        customer_results['time_between_purchases'] = None
    
    # Segmentación de clientes basada en frecuencia y valor
    customer_stats = transactions_df.groupby('customer').agg({
        'date': 'count',
        'num_products': 'sum'
    }).rename(columns={'date': 'num_purchases', 'num_products': 'total_products'})
    
    # Calcular cuartiles para segmentación
    freq_q75 = customer_stats['num_purchases'].quantile(0.75)
    value_q75 = customer_stats['total_products'].quantile(0.75)
    
    def segment_customer(row):
        if row['num_purchases'] >= freq_q75 and row['total_products'] >= value_q75:
            return 'High Value'
        elif row['num_purchases'] >= freq_q75:
            return 'Frequent'
        elif row['total_products'] >= value_q75:
            return 'Big Spender'
        else:
            return 'Regular'
    
    customer_stats['segment'] = customer_stats.apply(segment_customer, axis=1)
    segment_counts = customer_stats['segment'].value_counts()
    customer_results['segmentation'] = segment_counts.to_dict()
    
    print("\n=== ANÁLISIS DE CLIENTES ===")
    print(f"\nFrecuencia de compra:")
    print(f"Promedio de compras por cliente: {customer_results['purchase_frequency']['mean']:.2f}")
    print(f"Mediana de compras por cliente: {customer_results['purchase_frequency']['median']:.2f}")
    print(f"Máximo de compras de un cliente: {customer_results['purchase_frequency']['max']}")
    
    if customer_results['time_between_purchases']:
        print(f"\nTiempo entre compras:")
        print(f"Promedio: {customer_results['time_between_purchases']['mean_days']:.2f} días")
        print(f"Mediana: {customer_results['time_between_purchases']['median_days']:.2f} días")
    
    print(f"\nSegmentación de clientes:")
    for segment, count in segment_counts.items():
        print(f"{segment}: {count} clientes")
    
    context['ti'].xcom_push(key='customer_results', value=customer_results)


def product_association_analysis(**context):
    """
    Analiza reglas de asociación entre productos usando el algoritmo Apriori.
    """
    transactions_json = context['ti'].xcom_pull(key='transactions_df')
    transactions_df = pd.read_json(transactions_json)
    
    # Convertir transacciones a lista de listas de productos
    transactions_list = []
    for products_str in transactions_df['products']:
        products = products_str.split()
        transactions_list.append(products)
    
    # Parámetros para Apriori
    min_support = 0.01  # 1% de las transacciones
    min_confidence = 0.3  # 30% de confianza
    
    association_results = {}
    
    # Calcular frecuencia de itemsets individuales
    item_counts = Counter()
    for transaction in transactions_list:
        for item in set(transaction):
            item_counts[item] += 1
    
    total_transactions = len(transactions_list)
    frequent_items = {item: count for item, count in item_counts.items() 
                     if count / total_transactions >= min_support}
    
    association_results['frequent_items'] = {k: int(v) for k, v in sorted(frequent_items.items(), 
                                                                           key=lambda x: x[1], 
                                                                           reverse=True)[:20]}
    
    # Calcular pares frecuentes
    pair_counts = Counter()
    for transaction in transactions_list:
        items = list(set(transaction))
        for pair in combinations(sorted(items), 2):
            pair_counts[pair] += 1
    
    frequent_pairs = {pair: count for pair, count in pair_counts.items() 
                     if count / total_transactions >= min_support}
    
    # Calcular reglas de asociación
    rules = []
    for (item_a, item_b), count_ab in frequent_pairs.items():
        support_ab = count_ab / total_transactions
        support_a = item_counts[item_a] / total_transactions
        support_b = item_counts[item_b] / total_transactions
        
        # Regla A -> B
        confidence_ab = count_ab / item_counts[item_a]
        lift_ab = confidence_ab / support_b
        
        if confidence_ab >= min_confidence:
            rules.append({
                'antecedent': item_a,
                'consequent': item_b,
                'support': float(support_ab),
                'confidence': float(confidence_ab),
                'lift': float(lift_ab)
            })
        
        # Regla B -> A
        confidence_ba = count_ab / item_counts[item_b]
        lift_ba = confidence_ba / support_a
        
        if confidence_ba >= min_confidence:
            rules.append({
                'antecedent': item_b,
                'consequent': item_a,
                'support': float(support_ab),
                'confidence': float(confidence_ba),
                'lift': float(lift_ba)
            })
    
    # Ordenar por lift y tomar las top 20
    rules_sorted = sorted(rules, key=lambda x: x['lift'], reverse=True)[:20]
    association_results['top_rules'] = rules_sorted
    
    print("\n=== ANÁLISIS DE ASOCIACIÓN DE PRODUCTOS ===")
    print(f"\nTotal de transacciones: {total_transactions}")
    print(f"Items frecuentes encontrados: {len(frequent_items)}")
    print(f"Pares frecuentes encontrados: {len(frequent_pairs)}")
    print(f"Reglas generadas: {len(rules)}")
    
    print(f"\nTop 10 reglas de asociación (ordenadas por lift):")
    for i, rule in enumerate(rules_sorted[:10], 1):
        print(f"{i}. {rule['antecedent']} -> {rule['consequent']}: "
              f"Support={rule['support']:.4f}, "
              f"Confidence={rule['confidence']:.4f}, "
              f"Lift={rule['lift']:.4f}")
    
    context['ti'].xcom_push(key='association_results', value=association_results)


def generate_plots(**context):
    """
    Genera gráficas basadas en las estadísticas calculadas.
    """
    categories_json = context['ti'].xcom_pull(key='categories_df')
    product_category_json = context['ti'].xcom_pull(key='product_category_df')
    transactions_json = context['ti'].xcom_pull(key='transactions_df')
    stats_results = context['ti'].xcom_pull(key='stats_results')
    temporal_results = context['ti'].xcom_pull(key='temporal_results')
    customer_results = context['ti'].xcom_pull(key='customer_results')
    association_results = context['ti'].xcom_pull(key='association_results')
    
    categories_df = pd.read_json(categories_json)
    product_category_df = pd.read_json(product_category_json)
    transactions_df = pd.read_json(transactions_json)
    transactions_df['date'] = pd.to_datetime(transactions_df['date'])
    
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    # Gráficas originales
    
    # 1. Top productos vendidos
    product_counts = pd.Series(stats_results['product_frequencies']).head(10)
    plt.figure(figsize=(10, 6))
    product_counts.plot(kind='barh', color='skyblue')
    plt.title('Top 10 Productos Mas Vendidos')
    plt.xlabel('Numero de Ventas')
    plt.ylabel('Producto')
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, 'top_products.png'))
    plt.close()
    
    # 2. Ranking de tiendas
    store_counts = pd.Series(stats_results['store_frequencies']['counts'])
    plt.figure(figsize=(8, 6))
    store_counts.plot(kind='bar', color='lightgreen')
    plt.title('Ranking de Tiendas por Numero de Transacciones')
    plt.xlabel('Tienda')
    plt.ylabel('Numero de Transacciones')
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, 'store_ranking.png'))
    plt.close()
    
    # 3. Histograma de número de productos por transacción
    transactions_expanded = transactions_df.copy()
    transactions_expanded['num_products'] = transactions_expanded['products'].str.split().str.len()
    plt.figure(figsize=(10, 6))
    plt.hist(transactions_expanded['num_products'], bins=30, edgecolor='black', alpha=0.7)
    plt.title('Distribucion del Numero de Productos por Transaccion')
    plt.xlabel('Numero de Productos')
    plt.ylabel('Frecuencia')
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, 'products_histogram.png'))
    plt.close()
    
    # 4. Distribución de categorías
    category_id_to_name = categories_df.set_index('category_id')['category_name'].to_dict()
    category_counts = pd.Series(stats_results['categorical']['category_counts'])
    category_counts_named = category_counts.rename(index=category_id_to_name).head(10)
    plt.figure(figsize=(12, 6))
    category_counts_named.plot(kind='bar', color='coral')
    plt.title('Top 10 Categorias por Numero de Productos')
    plt.xlabel('Categoria')
    plt.ylabel('Numero de Productos')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, 'category_distribution.png'))
    plt.close()
    
    # Nuevas gráficas de análisis temporal
    
    # 5. Ventas diarias (serie temporal)
    daily_sales_df = pd.DataFrame(temporal_results['daily_sales']).T
    daily_sales_df.index = pd.to_datetime(daily_sales_df.index)
    plt.figure(figsize=(14, 6))
    plt.plot(daily_sales_df.index, daily_sales_df['num_transactions'], linewidth=1)
    plt.title('Serie Temporal de Transacciones Diarias')
    plt.xlabel('Fecha')
    plt.ylabel('Numero de Transacciones')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, 'daily_sales_timeseries.png'))
    plt.close()
    
    # 6. Ventas por día de la semana
    day_of_week_df = pd.DataFrame(temporal_results['day_of_week_sales']).T
    plt.figure(figsize=(10, 6))
    day_of_week_df['num_transactions'].plot(kind='bar', color='steelblue')
    plt.title('Transacciones por Dia de la Semana')
    plt.xlabel('Dia de la Semana')
    plt.ylabel('Numero de Transacciones')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, 'sales_by_day_of_week.png'))
    plt.close()
    
    # 7. Ventas mensuales
    monthly_sales_list = []
    for key, value in temporal_results['monthly_sales'].items():
        year, month = eval(key)
        monthly_sales_list.append({
            'year': year,
            'month': month,
            'num_transactions': value['num_transactions']
        })
    monthly_sales_df = pd.DataFrame(monthly_sales_list)
    monthly_sales_df['date'] = pd.to_datetime(monthly_sales_df[['year', 'month']].assign(day=1))
    monthly_sales_df = monthly_sales_df.sort_values('date')
    
    plt.figure(figsize=(12, 6))
    plt.plot(monthly_sales_df['date'], monthly_sales_df['num_transactions'], marker='o', linewidth=2)
    plt.title('Ventas Mensuales')
    plt.xlabel('Mes')
    plt.ylabel('Numero de Transacciones')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, 'monthly_sales.png'))
    plt.close()
    
    # Nuevas gráficas de análisis de clientes
    
    # 8. Segmentación de clientes
    segment_df = pd.Series(customer_results['segmentation'])
    plt.figure(figsize=(10, 6))
    colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99']
    plt.pie(segment_df.values, labels=segment_df.index, autopct='%1.1f%%', 
            colors=colors, startangle=90)
    plt.title('Segmentacion de Clientes')
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, 'customer_segmentation.png'))
    plt.close()
    
    # 9. Top reglas de asociación
    if association_results['top_rules']:
        top_rules = association_results['top_rules'][:10]
        rules_labels = [f"{r['antecedent']}->{r['consequent']}" for r in top_rules]
        rules_lift = [r['lift'] for r in top_rules]
        
        plt.figure(figsize=(12, 6))
        plt.barh(range(len(rules_labels)), rules_lift, color='teal')
        plt.yticks(range(len(rules_labels)), rules_labels)
        plt.xlabel('Lift')
        plt.title('Top 10 Reglas de Asociacion (por Lift)')
        plt.tight_layout()
        plt.savefig(os.path.join(RESULTS_DIR, 'association_rules.png'))
        plt.close()
    
    print("Plots generated and saved to files")


def save_results(**context):
    """
    Guarda los resultados en archivos.
    """
    review_results = context['ti'].xcom_pull(key='review_results')
    stats_results = context['ti'].xcom_pull(key='stats_results')
    temporal_results = context['ti'].xcom_pull(key='temporal_results')
    customer_results = context['ti'].xcom_pull(key='customer_results')
    association_results = context['ti'].xcom_pull(key='association_results')
    
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    # Guardar revisión de datos
    with open(os.path.join(RESULTS_DIR, "data_review.txt"), "w") as f:
        for table, stats in review_results.items():
            f.write(f"=== {table.upper()} ===\n")
            for key, value in stats.items():
                f.write(f"{key}: {value}\n")
            f.write("\n")
    
    # Guardar estadísticas descriptivas
    with open(os.path.join(RESULTS_DIR, "descriptive_stats.txt"), "w") as f:
        f.write("=== ESTADÍSTICAS NUMÉRICAS ===\n")
        for var, stats in stats_results['numeric'].items():
            f.write(f"\n--- {var.upper()} ---\n")
            desc_df = pd.DataFrame(stats['describe'])
            f.write(desc_df.to_string())
            f.write(f"\nModa: {stats['mode']}\n")
            f.write(f"Outliers: {stats_results['outliers'][var]}\n")
        
        f.write("\n=== ESTADÍSTICAS CATEGÓRICAS ===\n")
        f.write("Categorías:\n")
        for cat, count in list(stats_results['categorical']['category_counts'].items())[:10]:
            freq = stats_results['categorical']['category_frequencies'][cat]
            f.write(f"Categoría {cat}: {count} productos ({freq}%)\n")
        
        f.write("\nTop productos:\n")
        for prod, count in list(stats_results['product_frequencies'].items())[:10]:
            f.write(f"Producto {prod}: {count} veces\n")
        
        f.write("\nTop stores:\n")
        for store, count in list(stats_results['store_frequencies']['counts'].items())[:10]:
            freq = stats_results['store_frequencies']['frequencies'][store]
            f.write(f"Store {store}: {count} transacciones ({freq}%)\n")
    
    # Guardar análisis temporal
    with open(os.path.join(RESULTS_DIR, "temporal_analysis.txt"), "w") as f:
        f.write("=== ANÁLISIS TEMPORAL ===\n\n")
        
        f.write("Estadísticas diarias:\n")
        for key, value in temporal_results['daily_stats'].items():
            f.write(f"{key}: {value}\n")
        
        f.write("\nVentas por día de la semana:\n")
        for day, stats in temporal_results['day_of_week_sales'].items():
            f.write(f"{day}: {stats['num_transactions']} transacciones, {stats['total_products']} productos\n")
        
        f.write("\nTop 10 días con más ventas:\n")
        daily_sales_sorted = sorted(temporal_results['daily_sales'].items(), 
                                    key=lambda x: x[1]['num_transactions'], 
                                    reverse=True)[:10]
        for date, stats in daily_sales_sorted:
            f.write(f"{date}: {stats['num_transactions']} transacciones\n")
    
    # Guardar análisis de clientes
    with open(os.path.join(RESULTS_DIR, "customer_analysis.txt"), "w") as f:
        f.write("=== ANÁLISIS DE CLIENTES ===\n\n")
        
        f.write("Frecuencia de compra:\n")
        for key, value in customer_results['purchase_frequency'].items():
            f.write(f"{key}: {value}\n")
        
        if customer_results['time_between_purchases']:
            f.write("\nTiempo entre compras:\n")
            for key, value in customer_results['time_between_purchases'].items():
                f.write(f"{key}: {value}\n")
        
        f.write("\nSegmentación de clientes:\n")
        for segment, count in customer_results['segmentation'].items():
            f.write(f"{segment}: {count} clientes\n")
    
    # Guardar análisis de asociación de productos
    with open(os.path.join(RESULTS_DIR, "product_association.txt"), "w") as f:
        f.write("=== ANÁLISIS DE ASOCIACIÓN DE PRODUCTOS ===\n\n")
        
        f.write("Items frecuentes (Top 20):\n")
        for item, count in association_results['frequent_items'].items():
            f.write(f"Producto {item}: {count} transacciones\n")
        
        f.write(f"\nReglas de asociación (Top 20 por lift):\n")
        for i, rule in enumerate(association_results['top_rules'], 1):
            f.write(f"{i}. {rule['antecedent']} -> {rule['consequent']}: "
                   f"Support={rule['support']:.4f}, "
                   f"Confidence={rule['confidence']:.4f}, "
                   f"Lift={rule['lift']:.4f}\n")
    
    print("Results saved to files")


# Definición del DAG
with DAG(
    dag_id="dataset_analysis_dag",
    default_args=default_args,
    description="Análisis de dataset de transacciones",
    schedule_interval=None,
    start_date=datetime(2025, 10, 11),
    catchup=False,
    max_active_runs=1,
    tags=["dataset", "analysis"],
) as dag:

    t_load = PythonOperator(
        task_id="load_data",
        python_callable=load_data,
    )

    t_review = PythonOperator(
        task_id="data_review",
        python_callable=data_review,
    )

    t_stats = PythonOperator(
        task_id="descriptive_stats",
        python_callable=descriptive_stats,
    )

    t_temporal = PythonOperator(
        task_id="temporal_analysis",
        python_callable=temporal_analysis,
    )

    t_customer = PythonOperator(
        task_id="customer_analysis",
        python_callable=customer_analysis,
    )

    t_association = PythonOperator(
        task_id="product_association",
        python_callable=product_association_analysis,
    )

    t_generate_plots = PythonOperator(
        task_id="generate_plots",
        python_callable=generate_plots,
    )

    t_save = PythonOperator(
        task_id="save_results",
        python_callable=save_results,
    )

    t_load >> t_review >> t_stats
    t_stats >> [t_temporal, t_customer, t_association]
    [t_temporal, t_customer, t_association] >> t_generate_plots >> t_save