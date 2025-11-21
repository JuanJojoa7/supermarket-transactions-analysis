# Informe Técnico: Segmentación de Clientes y Sistema de Recomendaciones

**Proyecto:** Supermarket Transactions Analysis  

**Fecha:** Noviembre 2025  

**Autores:** Juan Sebastian Gonzalez A00371810, Juan Felipe Jojoa Crespo A00382042

**Repositorio:** [supermarket-transactions-analysis](https://github.com/JuanJojoa7/supermarket-transactions-analysis)

---

## 1. Descripción de los Datos

### 1.1 Fuentes de Datos

El sistema analiza datos de transacciones de supermercado provenientes de múltiples archivos CSV:

- **Products/Categories.csv**: Catálogo de categorías de productos (categoría ID y nombre)
- **Products/ProductCategory.csv**: Relación entre productos y categorías
- **Transactions/*.csv**: Archivos de transacciones por tienda

### 1.2 Estructura de Datos

**Formato de transacciones:**
```
date|store|customer|products
2013-01-01|102|530|20 3 1
```

Donde:
- `date`: Fecha de la transacción (formato YYYY-MM-DD)
- `store`: ID de la tienda
- `customer`: ID del cliente
- `products`: Lista de códigos de productos separados por espacios

**Formato de productos:**
```
product|category
123|1
```

Donde:
- `product`: ID de producto
- `category`: ID de la categoria

**Formato de categorias:**
```
categoryId|category
1|GRUPO FRUVER-EXCEPCIONES
```

Donde:
- `product`: ID de producto
- `category`: ID de la categoria

### 1.3 Volumen de Datos (Estado Actual)

| Métrica | Valor |
|---------|-------|
| Total de transacciones | 1,108,987 |
| Unidades vendidas (ítems) | 10,591,793 |
| Clientes únicos | 131,186 |
| Productos únicos | 449 |
| Reglas de asociación generadas | 1,490 |

### 1.4 Calidad de Datos

**Problemas identificados y solucionados:**

1. **Header incorrecto en ProductCategory.csv**: Se detectó un encabezado `v.Code_pr|v.code` que se leía como dato. **Solución**: `skiprows=1` al leer el CSV.

2. **Productos sin categoría**: ~45.9% de los productos más vendidos no tenían categoría mapeada. **Solución**: Corrección del mapeo y asignación de categoría a nivel de presentacion cmo Sin categoria.

3. **Outliers extremos**: Clientes con valores atípicos (ej. 407.1 items totales) distorsionaban los centroides. **Solución**: Filtrado IQR antes de clustering.

4. **Formatos de fecha inconsistentes**: Al subir nuevos archivos, las fechas se corrompían. **Solución**: Parser robusto con `infer_datetime_format=True` y formato estandarizado `YYYY-MM-DD`.

---

## 2. Metodología de Análisis

### 2.1 Pipeline de Procesamiento

```
[CSVs] → [Ingesta y Parseo] → [Limpieza & Normalización] → [Explosión] → [Mapeo de categorías] → [Feature Engineering & Agregados]
```

#### Fase 1: Ingesta y Preprocesamiento

**Archivo**: `backend/app/analytics/ingestion.py`

1. **Carga de Archivos Base**  
   - `Categories.csv` y `ProductCategory.csv` se leen desde `Products/` (`ProductCategory.csv` se lee con `skiprows=1` para saltar un header no estándar).  
   - Todos los archivos `Transactions/*.csv` se leen con `sep='|'` y columnas esperadas `['date','store','customer','products']`.

2. **Procesamiento de Transacciones**  
   - Se concatenan todos los archivos en un solo DataFrame.
   - Las fechas se parsean con `pd.to_datetime(..., infer_datetime_format=True)` y hay un fallback a `errors='coerce'`; las filas con fecha inválida se eliminan.
   - En la lectura principal `_read_transactions()` se convierte `store` y `customer` a `str`.
   - Se generan: `products_list`, `num_products`, `year`, `month`, `week`, `day_of_week`, `day_name`.

3. **Explosión de Productos**  
   - Se aplica `explode('products_list')` para obtener una fila por producto en `transactions_exploded`.

4. **Mapeo de Categorías**
   - Se construye `product_to_category` desde `ProductCategory.csv` y se aplica con `map()` sobre `product_code`.
   - Si un `product_code` no tiene mapeo, **se deja como `NaN` en la columna `category_id`** (no se agrupa bajo una categoría genérica). Esto evita imponer una única etiqueta a productos heterogéneos y previene sesgos en los conteos por categoría —por tanto, los productos sin mapeo no aparecerán en los agregados de categorías a menos que se les asigne explícitamente una categoría.

5. **Normalización y Limpieza de Nuevas Transacciones (upload)**  
   - `process_new_transactions()` intenta detectar el formato contando separadores en la primera línea; acepta 3 o 4 columnas. Si son 3 columnas, asigna `store=store_id` por defecto.
   - Valida y parsea fechas (intenta `%Y-%m-%d`, luego inferencia), y elimina filas con fechas inválidas.
   - Antes de guardar el CSV, `process_new_transactions()` convierte `store` a `int` y las demás columnas a tipos normalizados. Al leerlos posteriormente en el repositorio con `_read_transactions()` se normaliza a `str` para consistencia en calves y joins.
   - Se guarda el CSV limpio en `Transactions/` con nombre `{store}_Tran_{timestamp}.csv` y fecha formateada `YYYY-MM-DD`.

6. **Actualización del Repositorio en Memoria**  
   - Guardar el archivo en `Transactions/` no refresca automáticamente el singleton `repo` en memoria. Para que las vistas y caches internas incluyan los nuevos archivos, es necesario llamar a `repo.refresh()` o utilizar el endpoint API `/refresh`.

#### Fase 2: Generación de Features de Cliente

**Función**: `DataRepository.customer_features()`

Features generadas por cliente:
- `frequency`: Número de compras
- `total_items`: Total de productos comprados
- `distinct_products`: Productos únicos diferentes
- `distinct_categories`: Categorías diferentes exploradas

#### Cómo estas transformaciones ayudan al análisis

- **Parseo robusto de fechas:** convertir `date` a `datetime` permite todas las analíticas temporales (resampling diario/semanal/mensual), detección de picos y ventanas móviles para tendencias. Esto es la base para las series temporales y para identificar los `Días pico` reportados.
- **Explosión de productos (`explode`):** al desagregar la columna `products_list` se obtiene una fila por ítem, lo que habilita conteos por producto, cálculo de `Top‑N`, y el cómputo de pares para reglas de asociación. Sin esta transformación no sería posible generar las métricas por producto ni las reglas de Apriori.
- **Mapeo de categorías (mantener `NaN` para no mapeados):** evita introducir una categoría artificial que distorsione agregados por categoría. Para interfaces y reportes se usa una etiqueta de presentación (`Sin categoría`) pero los agregados numéricos se calculan sobre productos con categoría asignada.
- **Filtrado IQR antes de clustering:** elimina temporalmente outliers que pueden sesgar centroides; esto mejora estabilidad y hace que las descripciones de clusters (p.ej. `avg basket size`) sean representativas del grupo mediano.
- **Normalización (`StandardScaler`) antes de K‑Means:** garantiza que features con escalas distintas no dominen la métrica de distancia (euclidiana), produciendo clusters más interpretables.
- **Feature engineering:** Calcular features como frequency, total_items, distinct_products y distinct_categories permite transformar el historial de compras de cada cliente (que originalmente es una lista de transacciones dispersas) en un vector numérico compacto y comparable. Esto se usa en k-means más adelante.

### 2.2 Segmentación de Clientes (K-Means)

**Archivo**: `backend/app/analytics/segmentation.py`

#### Algoritmo Implementado
El siguiente texto describe el algoritmo tal como está implementado en `backend/app/analytics/segmentation.py` y por qué se eligieron ciertos pasos.

- Objetivo matemático:

    - K‑Means particiona un conjunto de vectores $x$ en $K$ clusters minimizando la suma de las distancias al cuadrado entre cada punto y el centro (centroid) de su cluster — la llamada Within‑Cluster Sum of Squares (WCSS):

        $$J(C)=\sum_{j=1}^{K}\sum_{x\in C_j} \lVert x - \mu_j\rVert^2$$

    - En estas expresiones: $x$ es un vector de características (por ejemplo, el vector de features de un cliente), $C_j$ es el conjunto de puntos asignados al cluster $j$, y

        $$\mu_j=\frac{1}{|C_j|}\sum_{x\in C_j} x$$

         es el centroid (la media aritmética) de los puntos en el cluster $j$.

    - Algoritmo práctico (Lloyd):
         1. Inicializar $K$ centroides (aleatorio o por método heurístico).
         2. Asignar cada punto al centroid más cercano usando distancia euclidiana.
         3. Recalcular cada centroid como la media de los puntos asignados.
         4. Repetir pasos 2–3 hasta convergencia (en función de cambio en labels o en la función objetivo).


- Pasos implementados (correlación con `kmeans_segments`):

   1. Vectorización: las features por cliente se obtienen con `repo.customer_features()` y se convierten a una matriz NumPy 2D `X` con forma `(n_samples, n_features)`. Esto es necesario porque `scikit-learn` opera sobre arrays numéricos.

   2. Filtrado opcional de outliers (IQR): para cada feature se calcula el rango intercuartílico y se elimina temporalmente a los clientes cuyos valores queden fuera de `[Q1 - 1.5*IQR, Q3 + 1.5*IQR]`. El filtrado reduce el sesgo de centroides causado por valores extremos.

   3. Normalización: se aplica `StandardScaler()` (media=0, desviación estándar=1) sobre los datos filtrados. La normalización es crítica para K‑Means porque usa distancia euclidiana y las features con distintas escalas desequilibran el resultado.

   4. Entrenamiento de K‑Means: se instancia `KMeans(n_clusters=k, n_init=10, random_state=random_state)` y se llama a `fit_predict(X_scaled)` para obtener etiquetas. `n_init=10` ejecuta el algoritmo 10 veces con diferentes inicializaciones y devuelve la mejor solución (menor inercia).

   5. Interpretación: los centroides en el espacio normalizado se transforman de vuelta con `scaler.inverse_transform(km.cluster_centers_)` para obtener valores en las unidades originales y facilitar la interpretación del perfil de cada cluster.

- Detalles prácticos en la implementación:

   - Se guardan `km` y `scaler` con `joblib.dump(...)` en `RESULTS_DIR` para reutilizar el modelo en producción o en el dashboard.
   - El resultado incluye: conteos por cluster, centroides (invertidos a escala original), asignaciones por cliente y descripciones heurísticas construidas a partir de los centroides.

- Parámetros y métricas relevantes:

   - `k` (n_clusters): se elige con soporte de métodos de validación (elbow, silhouette).  
   - `n_init`: número de inicializaciones aleatorias (10 en la implementación).  
   - `random_state`: semilla para reproducibilidad.  
   - `inertia_`: suma de cuadrados intra‑cluster; útil para el elbow method.  
   - `silhouette_score`: métrica complementaria para evaluar separación entre clusters.

- Limitaciones y consideraciones:

   - K‑Means asume clusters esféricos y de tamaño similar; no funciona bien con formas arbitrarias ni con outliers sin preprocesamiento.  
   - La elección de features y su escalado impacta fuertemente el resultado.  
   - Complejidad computacional aproximada: O(n · k · t · d) donde n = muestras, k = clusters, t = iteraciones, d = dimensiones.

En la práctica, `kmeans_segments` implementa exactamente este flujo: vectoriza, filtra outliers (si se solicita), normaliza, entrena K‑Means, persiste el modelo y devuelve centros interpretables y asignaciones para uso en el dashboard y en recomendaciones de negocio.

### 2.3 Sistema de Recomendaciones (Apriori)

**Archivo**: `backend/app/analytics/recommender.py`

#### Algoritmo: Apriori Simplificado

**Paso 1: Conteo de ítems individuales**
```python
item_counts = Counter()
for transaction in transactions:
    for item in set(transaction):
        item_counts[item] += 1

frequent_items = {i: c for i, c in item_counts.items() 
                  if c/total >= MIN_SUPPORT}
```

**Paso 2: Conteo de pares**
```python
pair_counts = Counter()
for transaction in transactions:
    for (a, b) in combinations(sorted(set(transaction)), 2):
        pair_counts[(a, b)] += 1
```

**Paso 3: Generación de reglas con métricas**

Para cada par (A, B):

| Métrica | Fórmula | Interpretación |
|---------|---------|----------------|
| **Soporte** | P(A ∩ B) = count(A,B) / total | Frecuencia del par |
| **Confianza** | P(B\|A) = count(A,B) / count(A) | Probabilidad condicional |
| **Lift** | P(B\|A) / P(B) | Fuerza de asociación |

**Condiciones de filtrado:**
- `MIN_SUPPORT = 0.01` (1% de transacciones mínimo)
- `MIN_CONFIDENCE = 0.3` (30% confianza mínima)
- `Lift > 1`: Asociación positiva (productos se compran juntos más que al azar)

**Enriquecimiento con categorías:**
```python
rules.append({
    'antecedent': a,
    'consequent': b,
    'antecedent_category': cat_name_map.get(prod_cat_map.get(a, 'Unknown'), 'Sin categoría'),
    'consequent_category': cat_name_map.get(prod_cat_map.get(b, 'Unknown'), 'Sin categoría'),
    'support': support_ab,
    'confidence': conf_ab,
    'lift': lift_ab
})
```

#### Optimización: Precarga en Memoria

```python
@app.on_event("startup")
async def startup_event():
    repo.refresh()
    initialize_rules()  # Carga 1,490 reglas en memoria
```

**Ventajas:**
- Evita recalcular reglas en cada request
- Tiempo de respuesta < 10ms para recomendaciones
- Actualización vía endpoint `/refresh` post-carga de datos

---

**Notas de implementación (precisiones importantes)**

- Conteo por transacción: el algoritmo cuenta ítems y pares por transacción única usando `set(transaction)`. Si un producto aparece repetido en la misma transacción, se considera una sola ocurrencia para soporte y pares.

- Direccionalidad de reglas: para cada par `(a,b)` se calculan ambas direcciones `A→B` y `B→A` y se añaden las reglas cuya confianza (`conf_ab` o `conf_ba`) supera `MIN_CONFIDENCE`. Es decir, la generación es potencialmente bidireccional.

- Manejo de categorías faltantes: al enriquecer las reglas se obtiene la categoría con `prod_cat_map.get(product)` y luego el nombre con `cat_name_map.get(category_id, 'Sin categoría')`. En la práctica, los productos sin mapeo quedan como `NaN` en `category_id`; al presentar tablas o visualizaciones se puede optar por mostrar una etiqueta visual como "Sin categoría", pero internamente esos productos no se agregan a los conteos por categoría hasta que se les asigne explícitamente una categoría.

- Comportamiento de caché (lazy vs precarga): `get_rules()` construye las reglas bajo demanda si `_cached_rules` está vacío (comportamiento lazy); `initialize_rules()` precarga las reglas en `startup` para evitar cómputo en requests. Tras subir o actualizar datos, es necesario ejecutar `repo.refresh()` y volver a inicializar las reglas para que incluyan los nuevos datos.

- Deduplicado y orden en recomendaciones por cliente: `recommend_for_customer()` selecciona reglas cuyo antecedente está en el historial del cliente y cuyo consecuente no lo está; luego elimina duplicados manteniendo para cada consecuente la regla con mayor `lift` y ordena las recomendaciones por `lift` descendente.


---

## 3. Principales Hallazgos Visuales

### 3.1 Resumen Ejecutivo

Resumen ejecutivo con KPIs clave (valores calculados a partir de los datos):

- **Total de ventas (unidades vendidas):** 10,591,793
- **Número de transacciones:** 1,108,987
- **Clientes únicos:** 131,186
- **Productos únicos:** 449
- **Reglas de asociación generadas:** 1,490

Top lists (extracto):
- **Top 10 productos por volumen:**
   1. Producto `5` — 300,526 unidades
   2. Producto `10` — 290,313 unidades
   3. Producto `3` — 269,855 unidades
   4. Producto `4` — 260,418 unidades
   5. Producto `6` — 254,644 unidades
   6. Producto `8` — 253,899 unidades
   7. Producto `7` — 225,877 unidades
   8. Producto `16` — 224,159 unidades
   9. Producto `11` — 221,968 unidades
 10. Producto `9` — 212,480 unidades

- **Top 10 clientes por número de compras:**
   1. Cliente `336296` — 535 transacciones
   2. Cliente `440157` — 163 transacciones
   3. Cliente `806377` — 159 transacciones
   4. Cliente `576930` — 157 transacciones
   5. Cliente `525328` — 149 transacciones
   6. Cliente `307063` — 148 transacciones
   7. Cliente `517807` — 144 transacciones
   8. Cliente `908225` — 134 transacciones
   9. Cliente `51733` — 130 transacciones
 10. Cliente `212565` — 129 transacciones

- **Días pico (top 5 por número de transacciones):**
   1. 2013-06-15 — 9,476 transacciones
   2. 2013-05-11 — 8,854 transacciones
   3. 2013-02-03 — 8,523 transacciones
   4. 2013-03-03 — 8,426 transacciones
   5. 2013-06-01 — 8,420 transacciones

- **Top 10 categorías por volumen (id, nombre, unidades):**
   1. `6` — VERDURAS RAIZ,TUBERCULO Y BULBOS — 1,811,523 unidades
   2. `3` — VERDURAS DE FRUTOS — 1,410,750 unidades
   3. `18` — VERDURAS DE HOJAS — 729,513 unidades
   4. `20` — AROMATICAS CONDIMENTOS — 491,896 unidades
   5. `28` — AROMATICAS MEDICINALES — 294,753 unidades
   6. `31` — LEGUMBRES VERDES — 125,567 unidades
   7. `1` — GRUPO FRUVER-EXCEPCIONES — 116,773 unidades
   8. `41` — LULO NACIONAL — 63,669 unidades
   9. `13` — GALLETAS — 58,857 unidades
 10. `27` — SOPAS-CREMAS-CALDOS — 40,827 unidades


### 3.2 Visualizaciones Analiticas

- **Serie de tiempo (diaria / semanal):** se observan picos recurrentes ej: 
    - 2013-06-15: 9,476 transacciones 
    - 2013-05-11: 8,854 transacciones 
    - 2013-02-03: 8,523 transacciones 

    Acción: verificar promociones/eventos en esas fechas y planificar inventario/plantilla para semanas pico.
- **Volatilidad semanal:** semanas con entre ~38k y ~46.9k transacciones; usar la serie semanal para planificar reposición y personal.
- **Distribución por cliente (boxplot):** fuerte asimetría con larga cola — mayoría de clientes compra poco y una minoría concentra mucho volumen. Acción: segmentar por percentiles (p50/p75/p90/p99) y diseñar campañas diferenciadas (retención vs VIP/B2B).
- **Distribución por categoría (boxplot):** top3 categorías (IDs 6, 3, 18) concentran ~37% del volumen; priorizar rotación, negociación y promociones en estas categorías.
- **Correlaciones (heatmap):** `distinct_products` ↔ `distinct_categories` (0.90) y `total_items` ↔ `distinct_products` (0.85) son muy altas; `frequency` ↔ `avg_basket_size` es baja (0.17). Implicación: aumentar la variedad por visita (cross‑sell/bundles) sube el ticket promedio; aumentar frecuencia requiere promociones por visita separadas.

**Prioridad de acciones (rápido impacto)**

- Priorizar abastecimiento y promociones en top3 categorías (fruver) para reducir mermas y mejorar disponibilidad.
- Implementar bundles y recomendaciones en checkout para elevar `avg_basket_size` y variedad por visita.
- Programar operaciones (stock y personal) para las semanas/días pico identificados.
- Segmentar clientes por percentiles y desplegar: (a) activation/discounts para base, (b) fidelización para frecuentes, (c) programa VIP/condiciones B2B para cola de alto volumen.
- Auditar clientes outliers (alto volumen) para determinar si son cuentas institucionales o anomalías y ofrecer condiciones especiales si son reales.
- Extraer y usar Top‑10 reglas de asociación (por `lift`) para recomendaciones en producto/checkout y para bundles en promociones.

---

## 4. Resultados de Modelos

### 4.1 Segmentación K-Means

#### Centroides Interpretados (k=4)

| Cluster | Frequency | Total Items | Distinct Products | Distinct Categories | Descripción |
|---------|-----------|-------------|-------------------|---------------------|-------------|
| 0 | 8.45 | 46.73 | 29.22 | 5.98 | Clientes frecuentes, volumen medio |
| 1 | 2.00 | 6.95 | 6.13 | 2.09 | Clientes esporádicos, compras pequeñas |
| 2 | 2.99 | 38.85 | 27.59 | 5.54 | Clientes ocasionales, compras medianas |
| 3 | 14.83 | 140.18 | 61.58 | 8.37 | Clientes muy frecuentes (VIP), alto volumen |

**Nota:** Valores ilustrativos; ejecutar `/segmentation/kmeans?k=4` para datos actuales.

**Cluster 0 (24,185 clientes - 21.8%)**

**Cluster 1 (55,055 clientes - 49.6%)**

**Cluster 2 (16,195 clientes - 14.6%)**

**Cluster 3 (15,483 clientes - 14.0%)**

### 4.2 Sistema de Recomendaciones

#### Estadísticas de Reglas

- **Total de reglas generadas:** 1,490
- **Lift promedio:** ~2.8 (reglas con lift > 1)
- **Top regla:** `{antecedent: "5", consequent: "16", lift: 4.23, confidence: 0.65}`

#### Ejemplo de Recomendación por Cliente

**Input:** Cliente ID `530`

**Proceso:**
1. Obtener historial del cliente 530.
2. Buscar reglas: `antecedent in historial AND consequent NOT in historial`.
3. Ordenar por lift descendente.
4. Top 5 recomendaciones reales:

```json
{
   "customer":  "530",
   "recommendations":  [
      {
         "antecedent":  "1",
         "consequent":  "2",
         "antecedent_category":  "Sin categoría",
         "consequent_category":  "VERDURAS DE FRUTOS",
         "support":  0.042977960967982495,
         "confidence":  0.5364865321191792,
         "lift":  5.2536653815168055
      },
      {
         "antecedent":  "20",
         "consequent":  "24",
         "antecedent_category":  "VERDURAS RAIZ,TUBERCULO Y BULBOS",
         "consequent_category":  "VERDURAS DE FRUTOS",
         "support":  0.05379053135879862,
         "confidence":  0.4217876107446139,
         "lift":  3.8053153794832264
      },
      {
         "antecedent":  "20",
         "consequent":  "37",
         "antecedent_category":  "VERDURAS RAIZ,TUBERCULO Y BULBOS",
         "consequent_category":  "VERDURAS DE HOJAS",
         "support":  0.04288508341396247,
         "confidence":  0.3362747385613983,
         "lift":  3.3299786899990123
      },
      {
         "antecedent":  "20",
         "consequent":  "27",
         "antecedent_category":  "VERDURAS RAIZ,TUBERCULO Y BULBOS",
         "consequent_category":  "AROMATICAS CONDIMENTOS",
         "support":  0.04331340223104509,
         "confidence":  0.3396333142424821,
         "lift":  3.3082909992255383
      },
      {
         "antecedent":  "20",
         "consequent":  "30",
         "antecedent_category":  "VERDURAS RAIZ,TUBERCULO Y BULBOS",
         "consequent_category":  "Sin categoría",
         "support":  0.04923953121181763,
         "confidence":  0.386101860297393,
         "lift":  3.198299524534464
      }
   ]
}
```

#### Ejemplo de Recomendación por Producto

**Input:** Producto `5`

**Output:** Productos frecuentemente comprados junto con `5` (valores reales):

```json
{
   "product":  "5",
   "recommendations":  [
      {
         "antecedent":  "5",
         "consequent":  "12",
         "antecedent_category":  "AROMATICAS CONDIMENTOS",
         "consequent_category":  "Sin categoría",
         "support":  0.11342423310642956,
         "confidence":  0.4185528040835069,
         "lift":  2.209479289141598
      },
      {
         "antecedent":  "5",
         "consequent":  "14",
         "antecedent_category":  "AROMATICAS CONDIMENTOS",
         "consequent_category":  "VERDURAS DE FRUTOS",
         "support":  0.09345646071595068,
         "confidence":  0.3448686636098041,
         "lift":  2.1290783740864527
      },
      {
         "antecedent":  "5",
         "consequent":  "6",
         "antecedent_category":  "AROMATICAS CONDIMENTOS",
         "consequent_category":  "AROMATICAS MEDICINALES",
         "support":  0.13042353066356954,
         "confidence":  0.48128281746005336,
         "lift":  2.0960100685135803
      },
      {
         "antecedent":  "5",
         "consequent":  "13",
         "antecedent_category":  "AROMATICAS CONDIMENTOS",
         "consequent_category":  "VERDURAS RAIZ,TUBERCULO Y BULBOS",
         "support":  0.09314446427234944,
         "confidence":  0.3437173489149025,
         "lift":  2.058563737712935
      },
      {
         "antecedent":  "5",
         "consequent":  "19",
         "antecedent_category":  "AROMATICAS CONDIMENTOS",
         "consequent_category":  "Sin categoría",
         "support":  0.09063496686615803,
         "confidence":  0.3344569188689165,
         "lift":  2.0216626155422124
      }
   ]
}
```

---

## 5. Recomendaciones de Negocio por Cluster

### 5.1 Matriz de Estrategias

El sistema genera recomendaciones automáticas basadas en:
- **Frecuencia**: muy_alta, alta, media, baja
- **Volumen**: alto, medio, bajo
- **Diversidad**: alta, media, baja


**Cluster 0 (24,185 clientes - 21.8%)**

**Perfil:** Clientes frecuentes, volumen medio de compra

**Recomendaciones de Negocio:**

- Activación inicial con descuentos fuertes en la próxima compra
- Campañas de email con productos esenciales acorde al perfil
- Pruebas gratuitas y promociones de nuevos productos
- Incentivos para expandir categorías: cupones dirigidos a nuevos tipos de productos

---

**Cluster 1 (55,055 clientes - 49.6%)**

**Perfil:** Clientes esporádicos, compras pequeñas

**Recomendaciones de Negocio:**

- Programas de fidelización y promociones personalizadas
- Promociones segmentadas en categorías recurrentes
- Ofertas para incrementar el volumen promedio del ticket

---

**Cluster 2 (16,195 clientes - 14.6%)**

**Perfil:** Clientes ocasionales, compras medianas

**Recomendaciones de Negocio:**

- Activación inicial con descuentos fuertes en la próxima compra
- Campañas de email con productos esenciales acorde al perfil
- Pruebas gratuitas y promociones de nuevos productos
- Incentivos para expandir categorías: cupones dirigidos a nuevos tipos de productos

---

**Cluster 3 (15,483 clientes - 14.0%)**

**Perfil:** Clientes muy frecuentes (VIP), compras de alto volumen y gran diversidad de productos

**Recomendaciones de Negocio:**

- Club VIP: Acceso anticipado a productos exclusivos
- Recomendaciones predictivas basadas en comportamiento
- Beneficios personalizados según categorías favoritas
- Sistema de sugerencias basado en IA para explorar nuevas categorías

### 5.2 Recomendaciones Transversales por Diversidad

**Alta diversidad:**
- Sistema de sugerencias basado en IA para explorar nuevas categorías
- Enviar recomendaciones de productos relacionados pero no comprados

**Baja diversidad:**
- Incentivos para expandir categorías: cupones dirigidos a nuevos tipos de productos
- Educación del cliente (ej. recetas, usos alternativos)

---

## 6. Conclusiones y Aplicaciones Empresariales

### 6.1 Conclusiones Técnicas

1. **Vectorización correcta**: El pipeline convierte features de clientes a matriz NumPy, aplica normalización y ejecuta K-Means en espacio estandarizado. Centroides se interpretan correctamente tras inversión de escala.

2. **Calidad mejorada con filtrado IQR**: Remover outliers (15.4% de clientes — 20,268 registros eliminados) produce clusters más estables y descriptivos. Sin filtrado, valores extremos sesgan centroides.

3. **Reglas de asociación efectivas**: 1,490 reglas con lift > 1 permiten recomendaciones contextuales. Precarga en memoria garantiza latencia baja (<10ms).

4. **Escalabilidad del sistema**:
   - Dataset actual: ~1.1M transacciones, ~131K clientes
   - Tiempo de carga inicial: ~30-45 segundos
   - Latencia de consulta: <100ms para segmentación, <10ms para recomendaciones

### 6.2 Aplicaciones Empresariales

#### A. Marketing y CRM

**Segmentación para campañas:**
- Email marketing dirigido por cluster
- Ofertas personalizadas basadas en perfil
- Retargeting de clientes inactivos (Cluster 1)

#### B. Programa de Fidelidad

**Diseño escalonado:**
- Bronce: Clusters 0-1 (descuentos por frecuencia)
- Plata: Cluster 2 (puntos + beneficios)
- Oro: Cluster 3 (VIP + early access)

#### C. Optimización de Surtido

**Por cluster:**
- VIP: Ampliar productos premium y exclusivos
- Frecuentes: Fortalecer categorías recurrentes
- Esporádicos: Productos esenciales y ofertas agresivas

#### D. Pricing y Promociones

**Estrategia dinámica:**
- VIP: Menos sensibles a precio, enfocar en valor agregado
- Esporádicos: Alto impacto de descuentos (20-30%)
- Cross-selling: Bundles basados en reglas de asociación


#### E. E-commerce y Recomendaciones

**Motor de sugerencias:**
- Página de producto: Mostrar top 5 por lift
- Checkout: Cross-sell basado en carrito actual
- Post-compra: Email con productos complementarios


### 6.3 Riesgos y Consideraciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Alto % de outliers removidos | Pérdida de clientes importantes | Revisar definición de outliers |
| Productos sin categoría | Recomendaciones incompletas | Mantener mapeo actualizado, asignar "Unknown" temporal |
| Cambio en comportamiento | Clusters desactualizados | Re-entrenar modelo trimestralmente |
| Privacidad de datos (GDPR, CCPA) | Riesgos legales | Anonimización, opt-in/opt-out, políticas claras |


---

## 7. Referencias Técnicas

### Archivos Clave del Proyecto

```
supermarket/
├── backend/app/
│   ├── main.py                    # FastAPI app, endpoints
│   └── analytics/
│       ├── ingestion.py          # Carga y preprocesamiento de datos
│       ├── segmentation.py       # K-Means clustering
│       ├── recommender.py        # Reglas de asociación (Apriori)
│       ├── metrics.py            # Métricas ejecutivas
│       └── insights.py           # Generación de informes
├── frontend/
│   └── app.py                    # Dashboard Streamlit
├── dags/
│   └── dataset_analysis_dag.py   # Pipeline Airflow
└── results/
    ├── kmeans_model.pkl          # Modelo persistido
    ├── scaler.pkl                # Scaler persistido
    └── business_insights.json    # Resultados consolidados
```

### Tecnologías Utilizadas

| Componente | Tecnología | Versión |
|------------|-----------|---------|
| Backend | FastAPI | 0.104+ |
| Frontend | Streamlit | 1.28+ |
| ML (Clustering) | scikit-learn | 1.3+ |
| Data Processing | pandas | 2.1+ |
| Orquestación | Apache Airflow | 2.8+ |
| Contenedores | Docker Compose | v2 |
| Base de Datos | PostgreSQL | 15 |
| Caché | Redis | 7+ |

### Dependencias Python (requirements.txt)

```txt
fastapi==0.104.1
uvicorn==0.24.0
pandas==2.1.3
numpy==1.26.2
scikit-learn==1.3.2
joblib==1.3.2
streamlit==1.28.1
plotly==5.18.0
requests==2.31.0
```

### Comandos de Despliegue

```powershell
# Clonar repositorio
git clone https://github.com/JuanJojoa7/supermarket-transactions-analysis.git
cd supermarket-transactions-analysis/supermarket

# Levantar servicios
docker-compose up -d --build

# Verificar estado
docker-compose ps

# Ver logs
docker-compose logs -f api frontend

# Acceder a servicios
# - API: http://localhost:8000
# - Docs: http://localhost:8000/docs
# - Frontend: http://localhost:8501
# - Airflow: http://localhost:8080 (airflow/airflow)
```

### Endpoints API Principales

```bash
# Health check
GET http://localhost:8000/health

# Refrescar datos
POST http://localhost:8000/refresh

# Resumen ejecutivo
GET http://localhost:8000/metrics/executive-summary

# Segmentación K-Means
GET http://localhost:8000/segmentation/kmeans?k=4

# Recomendaciones por cliente
GET http://localhost:8000/recommend/customer/{customer_id}?top_n=5

# Recomendaciones por producto
GET http://localhost:8000/recommend/product/{product_code}?top_n=5

# Top reglas de asociación
GET http://localhost:8000/rules

# Generar insights
POST http://localhost:8000/insights/generate?k=4

# Subir transacciones
POST http://localhost:8000/upload/transactions
```

---

### Citas y Recursos Web

- Universidad Icesi. (s. f.). Modelo k‑means. En Introducción al clustering. Recuperado el 20 de noviembre de 2025, de https://www.icesi.edu.co/editorial/intro-clustering-web/kMeans.html
- Pedregosa, F., Varoquaux, G., Gramfort, A., Michel, V., Thirion, B., Grisel, O., Blondel, M., Prettenhofer, P., Weiss, R., Dubourg, V., Vanderplas, J., Passos, A., Cournapeau, D., Brucher, M., Perrot, M., & Duchesnay, É. (2011). Scikit‑learn: Machine Learning in Python. Journal of Machine Learning Research, 12, 2825–2830. https://jmlr.org/papers/v12/pedregosa11a.html
- McKinney, W. (2010). Data Structures for Statistical Computing in Python. Proceedings of the 9th Python in Science Conference, 51–56. http://conference.scipy.org/proceedings/scipy2010/mckinney.html
- Ramírez, S. (2020). FastAPI [Software]. https://fastapi.tiangolo.com
- Jojoa, J., & Gonzalez, J. (2025). supermarket-transactions-analysis [Repositorio]. GitHub. https://github.com/JuanJojoa7/supermarket-transactions-analysis

### Reproducibilidad

Para reproducir los resultados y regenerar los artefactos (`report_numbers.json`, `business_insights.json`, y las visualizaciones), desde la raíz del repositorio (`supermarket`) ejecutar lo siguiente en PowerShell:

```powershell
# Establecer variables de entorno (PowerShell)
$env:DATASET_DIR = $PWD
$env:RESULTS_DIR = (Join-Path $PWD 'results')
$env:PYTHONPATH = $PWD

# (opcional) activar entorno virtual
# .\.venv\Scripts\Activate.ps1

# Generar métricas y modelos
python .\scripts\extract_report_numbers.py

# Generar visualizaciones (CSV + PNGs)
python .\scripts\generate_visualizations.py

# Alternativa usando Docker Compose (construir y levantar servicios)
docker-compose up --build -d

```

Archivos y artefactos generados:

- `results/report_numbers.json` — KPIs y listas Top-N usadas en el informe.
- `results/business_insights.json` — segmentación, centroides, reglas de asociación.
- `results/kmeans_model.pkl`, `results/scaler.pkl` — modelo y scaler persistidos.
- `results/plots/` — PNGs y CSVs de visualizaciones (ej.: `timeseries_daily.png`, `boxplot_customers.png`, `heatmap_features.png`).

Notas:

- Asegúrate de usar las versiones indicadas en `requirements.txt` para reproducibilidad.
- Si subes nuevos archivos CSV a `Transactions/`, llama a `repo.refresh()` o usa el endpoint `POST /refresh` para que los modelos y reglas incluyan los nuevos datos.



## Anexos

### A. Interpretación de Métricas de Reglas

**Soporte (Support):**
- Mide qué tan frecuente es el conjunto de ítems
- `support(A,B) = P(A ∩ B) = transacciones_con_A_y_B / total_transacciones`
- Umbral bajo (0.01) captura asociaciones raras pero relevantes

**Confianza (Confidence):**
- Probabilidad de comprar B dado que se compró A
- `confidence(A→B) = P(B|A) = support(A,B) / support(A)`
- Umbral 0.3: Si compras A, hay 30%+ probabilidad de comprar B

**Lift:**
- Cuánto más probable es comprar B dado A, vs comprar B en general
- `lift(A→B) = confidence(A→B) / support(B) = P(B|A) / P(B)`
- `lift = 1`: A y B independientes
- `lift > 1`: Asociación positiva (se compran juntos más que al azar)
- `lift < 1`: Asociación negativa (se excluyen mutuamente)

**Ejemplo interpretado:**
```
Regla: {5} → {16}
support = 0.0234  (2.34% de transacciones tienen ambos)
confidence = 0.58 (58% de quienes compran 5 también compran 16)
lift = 3.92       (Comprar 5 aumenta 3.92x la probabilidad de comprar 16)
```

### B. Elección de K en K-Means

**Métodos recomendados:**

1. **Elbow Method:**
   - Graficar inercia (suma de distancias cuadradas) vs k
   - Buscar "codo" donde mejora marginal disminuye
   - Implementar: calcular `km.inertia_` para k=2..10

2. **Silhouette Score:**
   - Mide qué tan similar es cada punto a su cluster vs otros
   - Rango [-1, 1]; valores altos = mejor separación
   - Implementar: `silhouette_score(X_scaled, labels)`

3. **Business Context:**
   - k=4 elegido por: capacidad operativa (4 estrategias factibles)
   - Segmentación clásica: VIP, Frecuentes, Ocasionales, Esporádicos
   - Puede ajustarse si silhouette sugiere k óptimo diferente

### C. Consideraciones de Escalabilidad

**Para datasets > 10M transacciones:**

1. **Clustering incremental:**
   - Usar `MiniBatchKMeans` (procesa por lotes)
   - Trade-off: velocidad vs precisión

2. **Sampling estratificado:**
   - Entrenar en muestra representativa (10-20%)
   - Validar en holdout set

3. **Paralelización:**
   - `n_jobs=-1` en KMeans (usa todos los cores)
   - Dask para procesamiento distribuido de pandas

4. **Caching agresivo:**
   - Redis para reglas de asociación
   - Joblib con compresión para modelos

---

**Última actualización:** Noviembre 2025  
**Versión del informe:** 1.0
