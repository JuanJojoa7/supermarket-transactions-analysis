import os
import requests
import streamlit as st
import pandas as pd
import plotly.express as px

API_BASE = os.getenv('API_BASE_URL', 'http://localhost:8000')

st.set_page_config(page_title='Supermarket Transactions Analytics', layout='wide')
st.title('Supermarket Transactions Analytics Dashboard')

# Refresh button
if st.sidebar.button('Refrescar datos'):
    try:
        r = requests.post(f"{API_BASE}/refresh")
        st.sidebar.success(f"Refrescado: {r.json().get('status')}")
    except Exception as e:
        st.sidebar.error(f"Error al refrescar: {e}")

# Executive Summary
st.header('Resumen Ejecutivo')
summary = requests.get(f"{API_BASE}/metrics/executive-summary").json()
col1, col2, col3 = st.columns(3)
col1.metric('Total Unidades Vendidas', summary['total_units'])
col2.metric('Número de Transacciones', summary['num_transactions'])
col3.metric('Categorías (Top) visibles', len(summary['top_categories_relative_volume']))

# Top products
tp_df = pd.DataFrame(list(summary['top_products'].items()), columns=['Producto', 'Frecuencia'])
fig_tp = px.bar(tp_df.sort_values('Frecuencia'), x='Frecuencia', y='Producto', orientation='h', title='Top 10 Productos')
st.plotly_chart(fig_tp, use_container_width=True)

# Top clients
cl_df = pd.DataFrame(list(summary['top_clients'].items()), columns=['Cliente', 'Compras'])
fig_cl = px.bar(cl_df.sort_values('Compras'), x='Compras', y='Cliente', orientation='h', title='Top 10 Clientes')
st.plotly_chart(fig_cl, use_container_width=True)

# Peak days
pd_df = pd.DataFrame(list(summary['peak_days'].items()), columns=['Fecha', 'Transacciones'])
pd_df['Fecha'] = pd.to_datetime(pd_df['Fecha'])
fig_pd = px.line(pd_df.sort_values('Fecha'), x='Fecha', y='Transacciones', title='Días Pico de Compra')
st.plotly_chart(fig_pd, use_container_width=True)

# Top categories
cat_df = pd.DataFrame(list(summary['top_categories_relative_volume'].items()), columns=['Categoria', 'VolumenRel'])
fig_cat = px.bar(cat_df.sort_values('VolumenRel'), x='VolumenRel', y='Categoria', orientation='h', title='Categorías Más "Rentables"')
st.plotly_chart(fig_cat, use_container_width=True)

st.header('Visualizaciones Analíticas')
level = st.selectbox('Nivel Serie de Tiempo', ['daily', 'weekly', 'monthly'], index=0)
ts_data = requests.get(f"{API_BASE}/visualizations/time-series", params={'level': level}).json()
ts_df = pd.DataFrame([(k, v['num_transactions'], v['total_products']) for k, v in ts_data.items()], columns=['Periodo', 'Transacciones', 'TotalProductos'])
fig_ts = px.line(ts_df, x='Periodo', y='Transacciones', title=f'Serie de Tiempo ({level})')
st.plotly_chart(fig_ts, use_container_width=True)

# Boxplot
box_by = st.selectbox('Boxplot por', ['customer', 'category'])
box = requests.get(f"{API_BASE}/visualizations/boxplot", params={'by': box_by}).json()
box_df = pd.DataFrame(box['series'], columns=['Valor'])
fig_box = px.box(box_df, y='Valor', title=f'Distribución por {box_by}')
st.plotly_chart(fig_box, use_container_width=True)

# Heatmap correlaciones
corr = requests.get(f"{API_BASE}/visualizations/correlation").json()
cm_df = pd.DataFrame(corr['matrix'], columns=corr['columns'])
fig_hm = px.imshow(cm_df, text_auto=True, aspect='auto', title='Correlación de Features de Clientes')
st.plotly_chart(fig_hm, use_container_width=True)

st.header('Segmentación de Clientes (K-Means)')
k = st.slider('Clusters (k)', 2, 8, 4)
seg = requests.get(f"{API_BASE}/segmentation/kmeans", params={'k': k}).json()
centers_df = pd.DataFrame(seg['centers'])
centers_df['cluster'] = range(k)
fig_centers = px.bar(centers_df.melt(id_vars='cluster'), x='variable', y='value', color='cluster', barmode='group', title='Centros de Clusters')
st.plotly_chart(fig_centers, use_container_width=True)

st.subheader('Descripciones de Clusters')
for cid, desc in seg['descriptions'].items():
    st.write(f"Cluster {cid}: {desc}")

st.header('Recomendador de Productos')
mode = st.radio('Modo', ['Por Cliente', 'Por Producto'])
if mode == 'Por Cliente':
    cust_id = st.text_input('ID Cliente', '')
    if cust_id:
        try:
            rec = requests.get(f"{API_BASE}/recommend/customer/{cust_id}").json()
            if rec.get('recommendations'):
                st.write("**Recomendaciones:**")
                for i, r in enumerate(rec['recommendations'], 1):
                    st.write(f"{i}. Producto **{r['consequent']}** (lift: {r['lift']:.2f}, confianza: {r['confidence']:.2f})")
            else:
                st.warning(f"No hay recomendaciones disponibles para el cliente {cust_id}")
        except Exception as e:
            st.error(f"Error: {e}")
else:
    prod_id = st.text_input('Código Producto', '')
    if prod_id:
        try:
            rec = requests.get(f"{API_BASE}/recommend/product/{prod_id}").json()
            if rec.get('recommendations'):
                st.write("**Recomendaciones:**")
                for i, r in enumerate(rec['recommendations'], 1):
                    st.write(f"{i}. Producto **{r['consequent']}** (lift: {r['lift']:.2f}, confianza: {r['confidence']:.2f})")
            else:
                st.warning(f"No hay recomendaciones disponibles para el producto {prod_id}. Intenta con productos más populares (ej: 5, 10, 3, 4, 6, 8, 7, 16)")
        except Exception as e:
            st.error(f"Error: {e}")

st.caption('© Proyecto de Análisis de Transacciones de Supermercado')
