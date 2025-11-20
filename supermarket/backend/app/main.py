from fastapi import FastAPI, Query, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
import os

from .analytics.ingestion import repo, process_new_transactions
from .analytics.metrics import executive_summary, time_series, boxplot_data, heatmap_features
from .analytics.segmentation import kmeans_segments
from .analytics.recommender import recommend_for_customer, recommend_for_product, get_rules, initialize_rules
from .analytics.insights import generate_insights

app = FastAPI(title="Supermarket Transactions Analytics API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Inicializa datos y modelos al arrancar la aplicación."""
    print("Inicializando aplicación...")
    repo.refresh()
    initialize_rules()
    print("✓ Aplicación lista")


@app.get("/health")
def health() -> Dict[str, Any]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/refresh")
def refresh() -> Dict[str, Any]:
    """Refresca los datos y recalcula las reglas de asociación."""
    repo.refresh()
    # Limpiar y recalcular reglas
    from .analytics import recommender as rec
    rec._cached_rules = {}
    initialize_rules()
    return {"status": "refreshed"}


@app.get("/metrics/executive-summary")
def get_exec_summary() -> Dict[str, Any]:
    """Obtiene métricas ejecutivas agregadas del negocio."""
    return executive_summary()


@app.get("/visualizations/time-series")
def get_time_series(level: str = Query("daily", enum=["daily", "weekly", "monthly"])) -> Dict[str, Any]:
    """Genera series temporales de transacciones y productos."""
    return time_series(level)


@app.get("/visualizations/boxplot")
def get_boxplot(by: str = Query("customer", enum=["customer", "category"])) -> Dict[str, Any]:
    """Genera datos para boxplot de distribución."""
    return boxplot_data(by)


@app.get("/visualizations/correlation")
def get_correlation() -> Dict[str, Any]:
    """Calcula matriz de correlación entre features de clientes."""
    return heatmap_features()


@app.get("/segmentation/kmeans")
def segment(k: int = 4) -> Dict[str, Any]:
    """Segmenta clientes usando K-means."""
    return kmeans_segments(k=k)


@app.get("/recommend/customer/{customer_id}")
def recommend_customer(customer_id: str, top_n: int = 5) -> Dict[str, Any]:
    """Recomienda productos para un cliente específico."""
    return recommend_for_customer(customer_id, top_n)


@app.get("/recommend/product/{product_code}")
def recommend_product(product_code: str, top_n: int = 5) -> Dict[str, Any]:
    """Recomienda productos relacionados a un producto específico."""
    return recommend_for_product(product_code, top_n)


@app.get("/rules")
def rules() -> Dict[str, Any]:
    """Obtiene las top 50 reglas de asociación."""
    all_rules = get_rules()
    return {
        'rules': all_rules['rules'][:50],
        'frequent_items': all_rules['frequent_items'],
        'total_rules': len(all_rules['rules'])
    }


@app.post("/insights/generate")
def generate(k: int = 4) -> Dict[str, Any]:
    """Genera reporte de insights de negocio."""
    path = generate_insights(k=k)
    return {"status": "ok", "file": path}


@app.post("/upload/transactions")
async def upload_transactions(file: UploadFile = File(...), store_id: str = "999") -> Dict[str, Any]:
    """
    Sube nuevas transacciones desde un archivo CSV.
    Pipeline: validación → limpieza → normalización → guardado → refresh.
    
    Formato esperado: date|customer|products (sin encabezado)
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos CSV")
    
    try:
        # Leer contenido del archivo
        content = await file.read()
        csv_content = content.decode('utf-8')
        
        # Procesar transacciones
        result = process_new_transactions(csv_content, store_id)
        
        # Refrescar datos y modelos
        repo.refresh()
        from .analytics import recommender as rec
        rec._cached_rules = {}
        initialize_rules()
        
        result['data_refreshed'] = True
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar archivo: {str(e)}")
