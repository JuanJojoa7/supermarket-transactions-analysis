import os
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
import time

API_BASE = os.getenv('API_BASE_URL', 'http://localhost:8000')

# Verificar conexión con el backend
def check_backend_connection(max_retries=3, delay=2):
    """Verifica que el backend esté disponible."""
    for attempt in range(max_retries):
        try:
            r = requests.get(f"{API_BASE}/health", timeout=5)
            if r.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            if attempt < max_retries - 1:
                time.sleep(delay)
    return False

st.set_page_config(page_title='Supermarket Transactions Analytics', layout='wide')
st.title('Supermarket Transactions Analytics Dashboard')

# Verificar conexión con backend
if not check_backend_connection():
    st.error("🔴 No se puede conectar con el backend. Verifica que los contenedores estén corriendo.")
    st.info("Ejecuta: `docker-compose up` en el directorio supermarket/")
    st.stop()

# Sidebar con controles
st.sidebar.header('Controles')

# Botón de refresh
if st.sidebar.button('🔄 Refrescar datos'):
    try:
        r = requests.post(f"{API_BASE}/refresh")
        st.sidebar.success(f"Refrescado: {r.json().get('status')}")
    except Exception as e:
        st.sidebar.error(f"Error al refrescar: {e}")

# Upload de transacciones
st.sidebar.subheader('Subir Transacciones')
uploaded_file = st.sidebar.file_uploader("Selecciona archivo CSV", type=['csv'], help="Formato: date|customer|products")
store_id_input = st.sidebar.text_input("ID Tienda", "999")

if uploaded_file is not None and st.sidebar.button('📤 Subir y Procesar'):
    try:
        files = {'file': (uploaded_file.name, uploaded_file.getvalue(), 'text/csv')}
        r = requests.post(f"{API_BASE}/upload/transactions", files=files, params={'store_id': store_id_input})
        result = r.json()
        if result.get('status') == 'success':
            st.sidebar.success(f"✓ {result['message']}")
            st.sidebar.info(f"Procesadas: {result['cleaned_rows']} | Rechazadas: {result['rejected_rows']}")
            st.sidebar.success("🔄 Datos actualizados. Refrescando dashboard...")
            time.sleep(0.5)
            st.rerun()
        else:
            st.sidebar.error("Error en el procesamiento")
    except Exception as e:
        st.sidebar.error(f"Error: {e}")

# Executive Summary
st.header('📊 Resumen Ejecutivo')
try:
    summary = requests.get(f"{API_BASE}/metrics/executive-summary", timeout=10).json()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric('Total Unidades Vendidas', f"{summary['total_units']:,}")
    col2.metric('Número de Transacciones', f"{summary['num_transactions']:,}")
    col3.metric('Clientes Únicos', f"{summary['unique_customers']:,}")
    col4.metric('Productos Únicos', f"{summary['unique_products']:,}")

    st.subheader('🏆 Productos Más Vendidos')
    tp_df = pd.DataFrame(list(summary['top_products'].items()), columns=['Producto', 'Frecuencia'])
    tp_df = tp_df.sort_values('Frecuencia', ascending=True).tail(10)
    fig_tp = px.bar(tp_df, x='Frecuencia', y='Producto', orientation='h', 
                    title='Top 10 Productos Más Vendidos',
                    labels={'Frecuencia': 'Número de Ventas', 'Producto': 'Código de Producto'},
                    color='Frecuencia', color_continuous_scale='Blues')
    fig_tp.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig_tp, use_container_width=True)

    st.subheader('👥 Clientes Más Activos')
    cl_df = pd.DataFrame(list(summary['top_clients'].items()), columns=['Cliente', 'Compras'])
    cl_df = cl_df.sort_values('Compras', ascending=True).tail(10)
    fig_cl = px.bar(cl_df, x='Compras', y='Cliente', orientation='h',
                    title='Top 10 Clientes por Número de Compras',
                    labels={'Compras': 'Número de Transacciones', 'Cliente': 'ID Cliente'},
                    color='Compras', color_continuous_scale='Greens')
    fig_cl.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig_cl, use_container_width=True)

    st.subheader('📅 Días con Mayor Actividad')
    pd_df = pd.DataFrame(list(summary['peak_days'].items()), columns=['Fecha', 'Transacciones'])
    pd_df['Fecha'] = pd.to_datetime(pd_df['Fecha'])
    pd_df = pd_df.sort_values('Fecha')
    fig_pd = px.line(pd_df, x='Fecha', y='Transacciones', 
                     title='Tendencia de Transacciones Diarias',
                     labels={'Fecha': 'Fecha', 'Transacciones': 'Número de Transacciones'},
                     markers=True)
    fig_pd.update_traces(line_color='#FF6B6B', line_width=2)
    fig_pd.update_layout(hovermode='x unified')
    st.plotly_chart(fig_pd, use_container_width=True)

    st.subheader('📦 Categorías con Mayor Volumen Relativo')
    cat_df = pd.DataFrame(list(summary['top_categories_relative_volume'].items()), columns=['Categoria', 'VolumenRel'])
    cat_df = cat_df.sort_values('VolumenRel', ascending=True).tail(10)
    fig_cat = px.bar(cat_df, x='VolumenRel', y='Categoria', orientation='h',
                     title='Top 10 Categorías por Volumen de Ventas',
                     labels={'VolumenRel': 'Volumen Relativo', 'Categoria': 'Categoría'},
                     color='VolumenRel', color_continuous_scale='Purples')
    fig_cat.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig_cat, use_container_width=True)
except requests.exceptions.RequestException as e:
    st.error(f"❌ Error al cargar resumen ejecutivo: {e}")

st.header('📈 Visualizaciones Analíticas')

try:
    st.subheader('⏰ Serie de Tiempo de Ventas')
    level = st.selectbox('Nivel de Agregación', ['daily', 'weekly', 'monthly'], 
                         index=0, format_func=lambda x: {'daily': 'Diario', 'weekly': 'Semanal', 'monthly': 'Mensual'}[x])
    ts_data = requests.get(f"{API_BASE}/visualizations/time-series", params={'level': level}, timeout=10).json()
    ts_df = pd.DataFrame([(k, v['num_transactions'], v['total_products']) for k, v in ts_data.items()], 
                         columns=['Periodo', 'Transacciones', 'TotalProductos'])
    fig_ts = px.line(ts_df, x='Periodo', y=['Transacciones', 'TotalProductos'], 
                     title=f'Evolución Temporal de Ventas ({level})',
                     labels={'value': 'Cantidad', 'variable': 'Métrica', 'Periodo': 'Período'},
                     markers=True)
    fig_ts.update_layout(hovermode='x unified', legend=dict(title='Métrica', orientation='h', y=1.1))
    st.plotly_chart(fig_ts, use_container_width=True)

    st.subheader('📊 Distribución de Datos')
    box_by = st.selectbox('Análisis de Distribución por', ['customer', 'category'],
                          format_func=lambda x: 'Cliente' if x == 'customer' else 'Categoría')
    box = requests.get(f"{API_BASE}/visualizations/boxplot", params={'by': box_by}, timeout=10).json()
    box_df = pd.DataFrame(box['series'], columns=['Valor'])
    fig_box = px.box(box_df, y='Valor', 
                     title=f'Distribución de Productos por {box_by.capitalize()}',
                     labels={'Valor': 'Número de Productos'},
                     color_discrete_sequence=['#4ECDC4'])
    fig_box.update_layout(showlegend=False)
    st.plotly_chart(fig_box, use_container_width=True)
    st.caption(f"Este gráfico muestra la distribución de productos comprados por {'cliente' if box_by == 'customer' else 'categoría'}, incluyendo valores atípicos.")

    st.subheader('🔥 Correlación de Características de Clientes')
    corr = requests.get(f"{API_BASE}/visualizations/correlation", timeout=10).json()
    cm_df = pd.DataFrame(corr['matrix'], columns=corr['columns'])
    fig_hm = px.imshow(cm_df, text_auto='.2f', aspect='auto', 
                       title='Matriz de Correlación de Comportamiento del Cliente',
                       labels={'x': 'Característica', 'y': 'Característica', 'color': 'Correlación'},
                       color_continuous_scale='RdBu_r', zmin=-1, zmax=1)
    fig_hm.update_xaxes(side='bottom')
    st.plotly_chart(fig_hm, use_container_width=True)
    st.caption("Valores cercanos a 1 indican correlación positiva, cercanos a -1 negativa, y cercanos a 0 sin correlación.")
except requests.exceptions.RequestException as e:
    st.error(f"❌ Error al cargar visualizaciones: {e}")

st.header('🎯 Segmentación de Clientes (K-Means)')
st.markdown("Agrupa clientes con comportamientos de compra similares usando clustering K-means.")

try:
    k = st.slider('Número de Clusters (k)', 2, 8, 4)
    seg = requests.get(f"{API_BASE}/segmentation/kmeans", params={'k': k}, timeout=10).json()
    
    # Mostrar información de preprocesamiento
    if seg.get('outliers_removed', 0) > 0:
        st.info(f"ℹ️ Se removieron {seg['outliers_removed']} outliers ({seg['outliers_removed']/seg['total_customers']*100:.1f}%) para mejorar la calidad del clustering. Total clientes analizados: {seg['total_customers']:,}")
    
    centers_df = pd.DataFrame(seg['centers'])
    centers_df['cluster'] = [f'Cluster {i}' for i in range(k)]

    # Gráfico de centroides
    fig_centers = px.bar(centers_df.melt(id_vars='cluster'), 
                         x='variable', y='value', color='cluster', barmode='group',
                         title='Características Promedio de Cada Cluster',
                         labels={'variable': 'Característica', 'value': 'Valor Promedio', 'cluster': 'Cluster'})
    fig_centers.update_layout(legend=dict(orientation='h', y=1.15))
    st.plotly_chart(fig_centers, use_container_width=True)

    # Distribución de clientes por cluster
    st.subheader('Distribución de Clientes por Cluster')
    counts_df = pd.DataFrame(list(seg['counts'].items()), columns=['Cluster', 'Cantidad'])
    counts_df['Cluster'] = counts_df['Cluster'].apply(lambda x: f'Cluster {x}')
    fig_counts = px.pie(counts_df, values='Cantidad', names='Cluster',
                        title='Proporción de Clientes en Cada Cluster',
                        color_discrete_sequence=px.colors.qualitative.Set3)
    st.plotly_chart(fig_counts, use_container_width=True)

    st.subheader('📝 Descripción de Clusters')
    for cid, desc in seg['descriptions'].items():
        cluster_id = int(cid) if isinstance(cid, str) else cid
        count = seg['counts'].get(cluster_id, seg['counts'].get(str(cluster_id), 0))
        with st.expander(f"**Cluster {cid}** ({count:,} clientes - {count/seg['total_customers']*100:.1f}%)", expanded=True):
            st.markdown(f"**Perfil:** {desc}")
            
            # Características del cluster
            st.markdown("---")
            st.markdown("**📊 Características Promedio:**")
            cluster_data = centers_df[centers_df['cluster'] == f'Cluster {cid}'].iloc[0]
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("🔄 Frecuencia", f"{cluster_data['frequency']:.1f}", help="Número promedio de compras")
            with col2:
                st.metric("🛒 Total items", f"{cluster_data['total_items']:.1f}", help="Total de productos comprados")
            with col3:
                st.metric("📦 Productos", f"{cluster_data['distinct_products']:.0f}", help="Productos únicos diferentes")
            with col4:
                st.metric("🏷️ Categorías", f"{cluster_data['distinct_categories']:.0f}", help="Categorías diferentes")
            
            # Recomendaciones de negocio
            if 'business_recommendations' in seg and str(cid) in seg['business_recommendations']:
                st.markdown("---")
                st.markdown("**💼 Recomendaciones de Negocio:**")
                recommendations = seg['business_recommendations'][str(cid)]
                for rec in recommendations:
                    st.markdown(f"- {rec}")
            elif 'business_recommendations' in seg and cid in seg['business_recommendations']:
                st.markdown("---")
                st.markdown("**💼 Recomendaciones de Negocio:**")
                recommendations = seg['business_recommendations'][cid]
                for rec in recommendations:
                    st.markdown(f"- {rec}")
except requests.exceptions.RequestException as e:
    st.error(f"❌ Error al cargar segmentación: {e}")

st.header('💡 Recomendador de Productos')
st.markdown("Sistema de recomendaciones basado en reglas de asociación (Market Basket Analysis).")

mode = st.radio('Modo de Recomendación', ['Por Cliente', 'Por Producto'])

if mode == 'Por Cliente':
    cust_id = st.text_input('Ingresa el ID del Cliente', '', placeholder='Ejemplo: 101')
    if cust_id:
        try:
            rec = requests.get(f"{API_BASE}/recommend/customer/{cust_id}", timeout=10).json()
            if rec.get('recommendations'):
                st.success(f"**Recomendaciones para el cliente {cust_id}:**")
                
                # Crear tabla con información enriquecida
                rec_data = []
                for i, r in enumerate(rec['recommendations'], 1):
                    rec_data.append({
                        '#': i,
                        'Producto': r['consequent'],
                        'Categoría': r.get('consequent_category', 'N/A'),
                        'Confianza': f"{r['confidence']:.2%}",
                        'Lift': f"{r['lift']:.2f}",
                        'Soporte': f"{r['support']:.2%}"
                    })
                
                rec_df = pd.DataFrame(rec_data)
                st.table(rec_df)
                
                st.caption("**Confianza:** Probabilidad de comprar el producto recomendado | **Lift:** Qué tan fuerte es la asociación | **Soporte:** Frecuencia de la combinación")
            else:
                st.warning(f"No hay recomendaciones disponibles para el cliente {cust_id}. El cliente puede no tener historial suficiente.")
        except Exception as e:
            st.error(f"Error: {e}")
else:
    prod_id = st.text_input('Ingresa el Código del Producto', '', placeholder='Ejemplo: 5')
    if prod_id:
        try:
            rec = requests.get(f"{API_BASE}/recommend/product/{prod_id}", timeout=10).json()
            if rec.get('recommendations'):
                st.success(f"**Productos que se compran frecuentemente con {prod_id}:**")
                
                # Crear tabla con información enriquecida
                rec_data = []
                for i, r in enumerate(rec['recommendations'], 1):
                    rec_data.append({
                        '#': i,
                        'Producto': r['consequent'],
                        'Categoría': r.get('consequent_category', 'N/A'),
                        'Confianza': f"{r['confidence']:.2%}",
                        'Lift': f"{r['lift']:.2f}",
                        'Soporte': f"{r['support']:.2%}"
                    })
                
                rec_df = pd.DataFrame(rec_data)
                st.table(rec_df)
                
                st.caption("**Confianza:** Probabilidad de compra conjunta | **Lift:** Fuerza de la asociación (>1 indica asociación positiva) | **Soporte:** Frecuencia en transacciones")
            else:
                st.warning(f"No hay recomendaciones disponibles para el producto {prod_id}. Intenta con productos más populares (ej: 5, 10, 3, 4, 6, 8, 7, 16)")
        except Exception as e:
            st.error(f"Error: {e}")

st.caption('© Proyecto de Análisis de Transacciones de Supermercado')
