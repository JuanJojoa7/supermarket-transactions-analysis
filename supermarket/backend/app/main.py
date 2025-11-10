from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
import os

from .analytics.ingestion import repo
from .analytics.metrics import executive_summary, time_series, boxplot_data, heatmap_features
from .analytics.segmentation import kmeans_segments
from .analytics.recommender import recommend_for_customer, recommend_for_product, get_rules
from .analytics.insights import generate_insights

app = FastAPI(title="Supermarket Transactions Analytics API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok"}


@app.post("/refresh")
def refresh() -> Dict[str, Any]:
    repo.refresh()
    # reset cached rules
    from .analytics import recommender as rec
    rec._cached_rules = {}
    return {"status": "refreshed"}


@app.get("/metrics/executive-summary")
def get_exec_summary() -> Dict[str, Any]:
    return executive_summary()


@app.get("/visualizations/time-series")
def get_time_series(level: str = Query("daily", enum=["daily", "weekly", "monthly"])) -> Dict[str, Any]:
    return time_series(level)


@app.get("/visualizations/boxplot")
def get_boxplot(by: str = Query("customer", enum=["customer", "category"])) -> Dict[str, Any]:
    return boxplot_data(by)


@app.get("/visualizations/correlation")
def get_correlation() -> Dict[str, Any]:
    return heatmap_features()


@app.get("/segmentation/kmeans")
def segment(k: int = 4) -> Dict[str, Any]:
    return kmeans_segments(k=k)


@app.get("/recommend/customer/{customer_id}")
def recommend_customer(customer_id: str, top_n: int = 5) -> Dict[str, Any]:
    return recommend_for_customer(customer_id, top_n)


@app.get("/recommend/product/{product_code}")
def recommend_product(product_code: str, top_n: int = 5) -> Dict[str, Any]:
    return recommend_for_product(product_code, top_n)


@app.get("/rules")
def rules() -> Dict[str, Any]:
    return get_rules()


@app.post("/insights/generate")
def generate(k: int = 4) -> Dict[str, Any]:
    path = generate_insights(k=k)
    return {"status": "ok", "file": path}
