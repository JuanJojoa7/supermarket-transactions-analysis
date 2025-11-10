# Supermarket Transactions Analysis – Plataforma Analítica Completa

## Objetivo
Solución tecnológica para analizar y visualizar el comportamiento de transacciones de supermercado aplicando analítica descriptiva, diagnóstica y componentes avanzados (clustering y recomendación).

## Arquitectura
Componentes dentro de `docker-compose`:
1. Airflow: Orquesta el pipeline de análisis batch (`dataset_analysis_dag`).
2. API (FastAPI): Endpoints JSON para KPIs, visualizaciones, segmentación, recomendador y generación de insights.
3. Frontend (Streamlit): Dashboard interactivo de uso final.
4. PostgreSQL + Redis: Backend de Airflow.

Flujo:
CSV nuevos → (Airflow DAG opcional) → `/refresh` API recarga → Frontend consume endpoints.

## Endpoints Principales (FastAPI)
| Endpoint | Descripción |
|----------|-------------|
| `GET /health` | Estado del servicio |
| `POST /refresh` | Recarga datos desde CSV |
| `GET /metrics/executive-summary` | KPIs resumen ejecutivo |
| `GET /visualizations/time-series?level=daily|weekly|monthly` | Serie de tiempo |
| `GET /visualizations/boxplot?by=customer|category` | Datos para boxplot |
| `GET /visualizations/correlation` | Matriz de correlación |
| `GET /segmentation/kmeans?k=4` | Clustering K-Means clientes |
| `GET /recommend/customer/{id}` | Recomendaciones para cliente |
| `GET /recommend/product/{code}` | Recomendaciones para producto |
| `GET /rules` | Reglas de asociación (lift, soporte, confianza) |
| `POST /insights/generate?k=4` | Genera `business_insights.txt` y `.json` |

## KPIs Cubiertos
- Total de unidades vendidas (conteo de productos individuales).
- Número de transacciones.
- Top 10 productos y clientes.
- Días pico de compra.
- Categorías más "rentables" (volumen relativo).

## Visualizaciones Analíticas
Implementadas en el frontend usando Plotly:
- Serie de tiempo diaria/semanal/mensual.
- Boxplot (distribución por cliente o categoría).
- Heatmap de correlación de features de clientes.
- Distribución y centros de clusters K-Means.
- Reglas de asociación y recomendaciones.

## Segmentación (K-Means)
Features: frecuencia, total de items, productos distintos, categorías distintas, tamaño promedio del carrito. Se generan descripciones heurísticas de cada cluster.

## Recomendador
Basado en reglas de asociación (soporte mínimo 1%, confianza mínima 30%). Se ofrecen recomendaciones para un cliente (productos complementarios) y para un producto.

## Cómo Ejecutar (Windows con Docker Desktop)
1. Clona el repositorio:
```powershell
git clone https://github.com/JuanJojoa7/supermarket-transactions-analysis.git
cd supermarket-transactions-analysis/"supermarket"
```
2. Inicia los servicios:
```powershell
docker compose up --build
```
3. Accesos:
	 - Airflow UI: http://localhost:8080 (usuario/clave por defecto: airflow/airflow)
	 - API: http://localhost:8000/docs (Swagger interactivo)
	 - Dashboard: http://localhost:8501
4. Refrescar datos tras añadir nuevos CSV a `Products/` o `Transactions/`:
```powershell
Invoke-RestMethod -Method Post http://localhost:8000/refresh
```
5. Generar insights de negocio (clusters + reglas):
```powershell
Invoke-RestMethod -Method Post "http://localhost:8000/insights/generate?k=4"
```
6. Ejecutar pruebas (requiere entorno Python fuera de contenedor opcional):
```powershell
docker compose run --rm api pytest -q
```

## Actualización de Datos
Al colocar nuevos archivos en `Transactions/` o `Products/`:
1. Ejecuta el DAG en Airflow si quieres regenerar artefactos batch.
2. Llama al endpoint `/refresh` para que la API recargue todo en memoria.
3. El frontend se actualiza automáticamente al volver a cargar las secciones.

## Resultados Persistidos
Archivos generados en `results/`:
- `data_review.txt`, `descriptive_stats.txt`, `temporal_analysis.txt`, `customer_analysis.txt`, `product_association.txt` (pipeline Airflow).
- `business_insights.txt`, `business_insights.json` (endpoint `/insights/generate`).

## Futuras Mejoras
- Autenticación y control de acceso (JWT).
- Persistencia en base de datos transaccional (PostgreSQL) en lugar de solo CSV.
- Detección de anomalías en patrones de compra.
- Panel React + micro-frontends.
- Modelo de recomendación colaborativo (matrix factorization) cuando existan ratings.
- Notificaciones automáticas al detectar cambios significativos.

## Calidad y Pruebas
Pruebas incluidas: métricas, clustering. Para extender pruebas: crear casos en `backend/tests/` verificando estabilidad de reglas de asociación y límites (k pequeño, dataset reducido).

## Diagrama Simplificado
```
CSV -> Airflow DAG ----> archivos resultados
	|         |                 |
	|         v                 v
	|      API /refresh <---- Dashboard (Streamlit)
	|            |                |
	|            v                v
	+--> Segmentación / Reglas -> Insights
```

## Troubleshooting
- Puertos en uso: cambiar mapeo en `docker-compose.yaml`.
- Memoria insuficiente para clustering: reducir `k`.
- CSV corrupto: validar separador `|` y columnas esperadas.

---
Proyecto académico – Ingeniería de Datos & Analítica.

