from fastapi import FastAPI, HTTPException
import mysql.connector
import pandas as pd
import re
import matplotlib.pyplot as plt
import io
import base64
from influxdb import InfluxDBClient
from fastapi.responses import HTMLResponse
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.arima.model import ARIMA
from sklearn.metrics import mean_squared_error
from fastapi import FastAPI, Request, Depends, HTTPException, Form
import numpy as np
from fastapi.templating import Jinja2Templates
from fastapi import FastAPI, Request
import plotly.graph_objects as go
import logging
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi import Request


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Conexión al cliente de InfluxDB
client = InfluxDBClient(host='192.168.50.83', port=8086)
client.switch_database('nagiosmetricas')
templates = Jinja2Templates(directory="C:\\Users\\cmiranda\\Desktop\\Temporal\\Universidad\\nagios_api\\templates")

@app.get("/")
def read_root(request: Request):
    # Aquí, idealmente, consultarías tu base de datos para obtener los hosts únicos.
    # Por simplicidad, supondré que tienes una lista fija. Cámbialo según sea necesario.
    available_hosts = ["Laptop", "Servidor"]
    return templates.TemplateResponse("index.html", {"request": request, "hosts": available_hosts})


####EXTRACCION PARA DISCO
def extract_disk_info(output_str):
    free_space_match = re.search(r'Free was (\d+(\.\d+)?) GiB', output_str)
    
    free_space_gib = float(free_space_match.group(1)) if free_space_match else None
    
    return free_space_gib

def safe_disk_extract(row):
    try:
        return extract_disk_info(row)
    except ValueError:
        print(f"Error processing row: {row}")
        return None

@app.get("/nagios/disk_space_processed")
def get_processed_disk_space_data():
    connection = mysql.connector.connect(
        host='192.168.50.83',
        user='nagios',
        password='Pait.2023$',
        database='nagios_data'
    )
    query = """
    SELECT o.name1 as host, o.name2 as service, s.output, s.start_time 
    FROM servicechecks s
    JOIN objects o ON s.service_object_id = o.object_id
    WHERE o.name2 = 'Root Partition' AND (s.output LIKE 'DISK OK - free space%' OR s.output LIKE '%Free%');
    """
    df = pd.read_sql(query, connection)
    print(df)
    connection.close()
    if df.empty:
        raise HTTPException(status_code=404, detail="No data found")
    df['GB_Free'] = df['output'].apply(safe_disk_extract)
    df = df.drop(columns=['output'])

    # Eliminar las filas con NaN en GB_Free
    df.dropna(subset=['GB_Free'], inplace=True)
    
    data_list = df.to_dict(orient="records")
    influx_data = []
    for data in data_list:
        influx_entry = {
            "measurement": "espaciodisco", 
            "time": data["start_time"],
            "tags": {
                "host": data["host"],
                "service": data["service"]
            },
            "fields": {
                "GB_Free": data["GB_Free"]
            }
        }
        influx_data.append(influx_entry)

    client.write_points(influx_data)

    return data_list 

###EXTRACCION PARA CPU
def extract_cpu_info(output_str):
    percent_used_match = re.search(r'was (\d+(\.\d+)?) %', output_str)
    
    percent_used = float(percent_used_match.group(1)) if percent_used_match else None
    
    return percent_used

def safe_cpu_extract(row):
    try:
        return extract_cpu_info(row)
    except ValueError:
        print(f"Error processing row: {row}")
        return None
@app.get("/nagios/cpu_usage_processed")
def get_processed_cpu_usage_data():
    connection = mysql.connector.connect(
        host='192.168.50.83',
        user='nagios',
        password='Pait.2023$',
        database='nagios_data'
    )

    query = """
    SELECT o.name1 as host, o.name2 as service, s.output, s.start_time 
    FROM servicechecks s
    JOIN objects o ON s.service_object_id = o.object_id
    WHERE o.name2 = 'CPU Usage';
    """

    df = pd.read_sql(query, connection)
    print(df)
    connection.close()

    if df.empty:
        raise HTTPException(status_code=404, detail="No data found")

    df['Percent_Used'] = df['output'].apply(safe_cpu_extract)
    df = df.drop(columns=['output'])

    #eliminar las filas con NaN en Percent_Used
    df.dropna(subset=['Percent_Used'], inplace=True)
    
    data_list = df.to_dict(orient="records")
    influx_data = []
    for data in data_list:
        influx_entry = {
            "measurement": "usocpu",
            "time": data["start_time"], #guardar en la columna definida time, el start_time del comienzo monitor nagios
            "tags": {
                "host": data["host"],
                "service": data["service"]
            },
            "fields": {
                "Percent_Used": data["Percent_Used"]
            }
        }
        influx_data.append(influx_entry)

    client.write_points(influx_data)

    return data_list


#EXTRACCION MEMORIA RAM
def extract_ram_info(output_str):
    used_match = re.search(r'Used: (\d+(\.\d+)?) GB', output_str)
    percent_used_match = re.search(r'was (\d+(\.\d+)?) %', output_str)
    
    used_gb = float(used_match.group(1)) if used_match else None
    percent_used = float(percent_used_match.group(1)) if percent_used_match else None
    
    return used_gb, percent_used

def safe_ram_extract(row):
    try:
        return extract_ram_info(row)
    except ValueError:
        print(f"Error processing row: {row}")
        return (None, None)

@app.get("/nagios/ram_usage_processed")
def get_processed_ram_usage_data():
    connection = mysql.connector.connect(
        host='192.168.50.83',
        user='nagios',
        password='Pait.2023$',
        database='nagios_data'
    )

    query = """
    SELECT o.name1 as host, o.name2 as service, s.output, s.start_time 
    FROM servicechecks s
    JOIN objects o ON s.service_object_id = o.object_id
    WHERE o.name2 = 'Memory Usage';
    """

    df = pd.read_sql(query, connection)
    print(df)
    connection.close()

    if df.empty:
        raise HTTPException(status_code=404, detail="No data found")

    df['GB_Used'], df['Percent_Used'] = zip(*df['output'].apply(safe_ram_extract))
    df = df.drop(columns=['output'])

    #eliminar las filas con NaN en GB_Used y Percent_Used
    df.dropna(subset=['GB_Used', 'Percent_Used'], inplace=True)
    
    data_list = df.to_dict(orient="records")
    influx_data = []
    for data in data_list:
        influx_entry = {
            "measurement": "usomemoria",
            "time":data["start_time"],
            "tags": {
                "host": data["host"],
                "service": data["service"]
            },
            "fields": {
                "GB_Used": data["GB_Used"],
                "Percent_Used": data["Percent_Used"]
            }
        }
        influx_data.append(influx_entry)

    client.write_points(influx_data)

    return data_list

##Grafica para visualizar uso del Disco
@app.get("/visualize_disk", response_class=HTMLResponse)
def visualize_disk(request: Request, host: str = None):
    query = 'SELECT * FROM espaciodisco'
    resultados = client.query(query)
    df = pd.DataFrame(list(resultados.get_points()))
    details_info = {}
    if host:
            details_info["Host seleccionado"] = host
            df = df[df['host'] == host] #Filtra el dataframe basado en el host.
            details_info["Eventos de monitoreo"] = str(len(df))
    else:
        details_info["Mensaje"] = "No se proporcionó información"
        details_info["Eventos de monitoreo"] = "N/A"

    df['time'] = pd.to_datetime(df['time'], format='ISO8601')  # Convierte el tiempo en formato epoch a formato datetime y asume que está en nanosegundos
    df_resampled = df.set_index('time')['GB_Free'].resample('H').mean().interpolate()
    df['time'] = df['time'].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))
   # Generar gráfico con Plotly
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_resampled.index, y=df_resampled.values, mode='lines+markers', name='Uso de CPU'))
    fig.update_layout(
        title='Espacio Libre de Disco a lo largo del Tiemp',
        xaxis_title='Tiempo',
        yaxis_title='Espacio Libre de Disco (GB)',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white')
    )
    graph_html = fig.to_html(full_html=False)
    return templates.TemplateResponse("visualization.html", {
        "request": request, 
        "graph": graph_html, 
        "details_info": details_info,
        "data": df.to_dict('records')
    })

##Grafica visualizar RAM
@app.get("/visualize_ram", response_class=HTMLResponse)
def visualize_ram(request: Request, host: str = None):
    query = 'SELECT * FROM usomemoria'
    resultados = client.query(query)
    df = pd.DataFrame(list(resultados.get_points()))
    details_info = {} #Diccionario para almacenar detalles
    if host:
        details_info["Host Seleccionado"] = host
        df = df[df['host'] == host] #Filtra el dataframe basado en el host
        details_info["Eventos de monitoreo"] = str(len(df))
    else:
        details_info["Mensaje"] = "No se proporcionó información"
        details_info["Eventos de monitoreo"] = "N/A"
    df['time'] = pd.to_datetime(df['time'], format='ISO8601')
    df_resampled = df.set_index('time')['GB_Used'].resample('H').mean().interpolate()
    df['time'] = df['time'].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))
     # Generar gráfico con Plotly
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_resampled.index, y=df_resampled.values, mode='lines+markers', name='Uso de CPU'))
    fig.update_layout(
        title='Uso de Memoria RAM a lo largo del Tiempo',
        xaxis_title='Tiempo',
        yaxis_title='Uso de Memoria RAM (GB)',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white')
    )
    graph_html = fig.to_html(full_html=False)
    return templates.TemplateResponse("visualization.html", {
        "request": request, 
        "graph": graph_html, 
        "details_info": details_info,
        "data": df.to_dict('records')
    })    



##Grafica visualizar CPU
@app.get("/visualize_cpu", response_class=HTMLResponse)
def visualize_cpu(request: Request, host: str = None):
    query = 'SELECT * FROM usocpu'
    resultados = client.query(query)
    df = pd.DataFrame(list(resultados.get_points()))

    details_info = {} # Un diccionario para almacenar detalles de la visualización.

    if host:
        details_info["Host seleccionado"] = host
        df = df[df['host'] == host] #Filtra el dataframe basado en el host.
        details_info["Eventos de monitoreo"] = str(len(df))
    else:
        details_info["Mensaje"] = "No se proporcionó información"
        details_info["Eventos de monitoreo"] = "N/A"

    df['time'] = pd.to_datetime(df['time'], format='ISO8601')
    df_resampled = df.set_index('time')['Percent_Used'].resample('H').mean().interpolate()
    df['time'] = df['time'].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))
    # Generar gráfico con Plotly
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_resampled.index, y=df_resampled.values, mode='lines+markers', name='Uso de CPU'))
    fig.update_layout(
        title='Uso de CPU a lo largo del Tiempo',
        xaxis_title='Tiempo',
        yaxis_title='Uso de CPU (%)',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white')
    )
    graph_html = fig.to_html(full_html=False)
    return templates.TemplateResponse("visualization.html", {
        "request": request, 
        "graph": graph_html, 
        "details_info": details_info,
        "data": df.to_dict('records')
    })

####ARIMA DISCO
###ARIMA Uso de Disco
def dataframe_to_json_safe(df):
    return df.applymap(lambda x: str(x) if isinstance(x, (pd.Timestamp, pd.Timedelta)) else x).to_dict(orient='records')
@app.get("/visualize_arima_disk", response_class=HTMLResponse)
def visualize_arima_disk(request: Request, host: str = None):
    query = 'SELECT * FROM usodisco'  # Asegúrate de que esta tabla tiene los datos de uso del disco
    resultados = client.query(query)
    df = pd.DataFrame(list(resultados.get_points()))
    details_info = {}  # Un diccionario para almacenar detalles de la visualización.

    if host:
        details_info["Host seleccionado"] = host
        df = df[df['host'] == host]  # Filtra el dataframe basado en el host.
        details_info["Eventos de monitoreo"] = str(len(df))
    else:
        details_info["Mensaje"] = "No se proporcionó información"
        details_info["Eventos de monitoreo"] = "N/A"
    df['time'] = pd.to_datetime(df['time'], format='ISO8601')
    df_resampled = df.set_index('time')['GB_Used'].resample('H').mean().interpolate()
    # Crear el DataFrame para visualización
    df_visualization = df_resampled.reset_index()
    df_visualization['time'] = df_visualization['time'].astype(str)
    
    # Interpolando los valores faltantes
    #df_resampled = df_resampled.interpolate()
    
    # Dividir los datos en conjuntos de entrenamiento y prueba
    train_size = int(len(df_resampled) * 0.8)
    train, test = df_resampled[0:train_size], df_resampled[train_size:]

    # Establecer el modelo ARIMA
    model = ARIMA(train, order=(5,1,0))
    model_fit = model.fit()
    forecast = model_fit.forecast(steps=len(test))

    # Cálculo de RMSE
    rmse = np.sqrt(mean_squared_error(test, forecast))
    details_info["RMSE"] = str(rmse)
    ##print('RMSE:', rmse)  # Esto imprimirá el RMSE en tu consola o terminal

        # Generar gráfico con Plotly
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=test.index, y=test.values, mode='lines+markers', name='Datos reales'))
    fig.add_trace(go.Scatter(x=test.index, y=forecast, mode='lines+markers', name='Predicciones ARIMA'))
    fig.update_layout(
        title=f'Predicción ARIMA de Uso de CPU (RMSE: {rmse:.2f})',
        xaxis_title='Tiempo',
        yaxis_title='Uso de CPU (%)',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white')
    )
    
    graph_html = fig.to_html(full_html=False)

    # Convertir dataframe a formato JSON seguro
    data_for_template = dataframe_to_json_safe(df_resampled.reset_index())
    
    return templates.TemplateResponse("visualization.html", {
        "request": request,
        "graph": graph_html,
        "details_info": details_info,
        "data": data_for_template,
        "is_arima": True
    })
    # Gráfica de los datos reales vs las predicciones
    #plt.figure(figsize=(10, 6))
    #plt.plot(test.index, test.values, label='Uso Real del Disco', color='blue')
    #plt.plot(test.index, forecast, label='Predicciones ARIMA', color='red', alpha=0.7)
    #plt.title(f'Predicción ARIMA vs Uso Real del Disco (RMSE: {rmse:.2f})')  # Añadido RMSE al título
    #plt.xlabel('Tiempo')
    #plt.ylabel('Uso de Disco (GB)')
    #plt.legend()

    #buf = io.BytesIO()
    #plt.savefig(buf, format="png")
    #plt.close()
    #data = base64.b64encode(buf.getbuffer()).decode("utf8")
    #buf.close()

    #return f"""
    #    <html>
    #        <head>
    #            <title>Predicción ARIMA de Uso de Disco</title>
    #        </head>
    #        <body>
    #            <img src="data:image/png;base64,{data}" />
    #        </body>
    #    </html>"""

###ARIMA RAM
def dataframe_to_json_safe(df):
    return df.applymap(lambda x: str(x) if isinstance(x, (pd.Timestamp, pd.Timedelta)) else x).to_dict(orient='records')
@app.get("/visualize_arima_ram", response_class=HTMLResponse)
def visualize_arima_ram(request: Request, host: str = None):
    query = 'SELECT * FROM usomemoria'
    resultados = client.query(query)
    df = pd.DataFrame(list(resultados.get_points()))
    details_info = {}  # Un diccionario para almacenar detalles de la visualización.
    if host:
        details_info["Host seleccionado"] = host
        df = df[df['host'] == host]  # Filtra el dataframe basado en el host.
        details_info["Eventos de monitoreo"] = str(len(df))
    else:
        details_info["Mensaje"] = "No se proporcionó información"
        details_info["Eventos de monitoreo"] = "N/A"
    df['time'] = pd.to_datetime(df['time'], format='ISO8601')
    df_resampled = df.set_index('time')['GB_Used'].resample('H').mean().interpolate()
    
    train_size = int(len(df_resampled) * 0.8)
    train, test = df_resampled[0:train_size], df_resampled[train_size:]

    model = ARIMA(train, order=(5,1,0))
    model_fit = model.fit()
    forecast = model_fit.forecast(steps=len(test))

    rmse = np.sqrt(mean_squared_error(test, forecast))
    details_info["RMSE"] = str(rmse)

    #plt.figure(figsize=(10, 6))
    #plt.plot(test.index, test.values, label='Datos reales', color='blue')
    #plt.plot(test.index, forecast, label='Predicciones ARIMA', color='red', alpha=0.7)
    #plt.title(f'Predicción ARIMA vs Datos Reales (Uso de Memoria RAM - RMSE: {rmse:.2f})')
    #plt.xlabel('Tiempo')
    #plt.ylabel('Uso de Memoria RAM (GB)')
    #plt.legend()

    #buf = io.BytesIO()
    #plt.savefig(buf, format="png")
    #plt.close()
    #data = base64.b64encode(buf.getbuffer()).decode("utf8")
    #buf.close()

    #return f"""
    #    <html>
    #        <head>
    #            <title>Predicción ARIMA de Uso de Memoria RAM</title>
    #        </head>
    #        <body>
    #            <img src="data:image/png;base64,{data}" />
    #            <pre>{df.head()}</pre>
    #        </body>
    #    </html>"""
# Generar gráfico con Plotly
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=test.index, y=test.values, mode='lines+markers', name='Datos reales'))
    fig.add_trace(go.Scatter(x=test.index, y=forecast, mode='lines+markers', name='Predicciones ARIMA'))
    fig.update_layout(
        title=f'Predicción ARIMA de Uso de Memoria RAM (RMSE: {rmse:.2f})',
        xaxis_title='Tiempo',
        yaxis_title='Uso de Memoria RAM GB',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white')
    )
    
    graph_html = fig.to_html(full_html=False)

    # Convertir dataframe a formato JSON seguro
    data_for_template = dataframe_to_json_safe(df_resampled.reset_index())
    
    return templates.TemplateResponse("visualization.html", {
        "request": request,
        "graph": graph_html,
        "details_info": details_info,
        "data": data_for_template,
        "is_arima": True
    })
def dataframe_to_json_safe(df):
    return df.applymap(lambda x: str(x) if isinstance(x, (pd.Timestamp, pd.Timedelta)) else x).to_dict(orient='records')

@app.get("/visualize_arima_cpu", response_class=HTMLResponse)
def visualize_arima_cpu(request: Request, host: str = None):
    query = 'SELECT * FROM usocpu'
    resultados = client.query(query)
    df = pd.DataFrame(list(resultados.get_points()))

    details_info = {}  # Un diccionario para almacenar detalles de la visualización.

    if host:
        details_info["Host seleccionado"] = host
        df = df[df['host'] == host]  # Filtra el dataframe basado en el host.
        details_info["Eventos de monitoreo"] = str(len(df))
    else:
        details_info["Mensaje"] = "No se proporcionó información"
        details_info["Eventos de monitoreo"] = "N/A"

    df['time'] = pd.to_datetime(df['time'], format='ISO8601')
    df_resampled = df.set_index('time')['Percent_Used'].resample('H').mean().interpolate()
    print(df.dtypes)
    # Crear el DataFrame para visualización
    df_visualization = df_resampled.reset_index()
    df_visualization['time'] = df_visualization['time'].astype(str)
    
    # División de datos para ARIMA
    train_size = int(len(df_resampled) * 0.8)
    train, test = df_resampled[0:train_size], df_resampled[train_size:]

    model = ARIMA(train, order=(5,1,0))
    model_fit = model.fit()
    forecast = model_fit.forecast(steps=len(test))
    
    rmse = np.sqrt(mean_squared_error(test, forecast))
  

    # Generar gráfico con Plotly
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=test.index, y=test.values, mode='lines+markers', name='Datos reales'))
    fig.add_trace(go.Scatter(x=test.index, y=forecast, mode='lines+markers', name='Predicciones ARIMA'))
    fig.update_layout(
        title=f'Predicción ARIMA de Uso de CPU (RMSE: {rmse:.2f})',
        xaxis_title='Tiempo',
        yaxis_title='Uso de CPU (%)',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white')
    )
    
    graph_html = fig.to_html(full_html=False)

    # Convertir dataframe a formato JSON seguro
    data_for_template = dataframe_to_json_safe(df_resampled.reset_index())
    
    return templates.TemplateResponse("visualization.html", {
        "request": request,
        "graph": graph_html,
        "details_info": details_info,
        "data": data_for_template,
        "is_arima": True
    })
###ARIMA CPU
#@app.get("/visualize_arima_cpu", response_class=HTMLResponse)
#def visualize_arima_cpu(host: str = None):
#    query = 'SELECT * FROM usocpu'
#    resultados = client.query(query)
#    df = pd.DataFrame(list(resultados.get_points()))
#    if host:
#        df = df[df['host'] == host]
#    if 'time' in df.columns:
#        df['time'] = pd.to_datetime(df['time'], format='ISO8601')
#    else:
#        print("Columna 'time' no encontrada en el DataFrame.")
#    df_resampled = df.set_index('time')['Percent_Used'].resample('H').mean().interpolate()
    

#    train_size = int(len(df_resampled) * 0.8)
#    train, test = df_resampled[0:train_size], df_resampled[train_size:]
#
#    model = ARIMA(train, order=(5,1,0))
#    model_fit = model.fit()
#    forecast = model_fit.forecast(steps=len(test))

#    rmse = np.sqrt(mean_squared_error(test, forecast))
#    print('RMSE:', rmse)

#    plt.figure(figsize=(10, 6))
#    plt.plot(test.index, test.values, label='Datos reales', color='blue')
#    plt.plot(test.index, forecast, label='Predicciones ARIMA', color='red', alpha=0.7)
#    plt.title(f'Predicción ARIMA de Uso de CPU (RMSE: {rmse:.2f})')
#    plt.xlabel('Tiempo')
#    plt.ylabel('Uso de CPU (%)')
#    plt.legend()

#    buf = io.BytesIO()
#    plt.savefig(buf, format="png")
#    plt.close()
#    data = base64.b64encode(buf.getbuffer()).decode("utf8")
#    buf.close()

#    return f"""
#        <html>
#            <head>
#                <title>Predicción ARIMA de Uso de CPU</title>
#            </head>
#            <body>
#                <img src="data:image/png;base64,{data}" />
#            </body>
#        </html>"""

   
from statsmodels.tsa.statespace.sarimax import SARIMAX
import numpy as np
from pmdarima import auto_arima
def get_all_hosts():
    query = 'SHOW TAG VALUES FROM "espaciodisco" WITH KEY = "host"'
    resultados = client.query(query)
    return [host_value['value'] for host_value in resultados.get_points()]
@app.get("/predict_system_page", response_class=HTMLResponse)
async def show_predict_system_form(request: Request):
    hosts = get_all_hosts()
    return templates.TemplateResponse("prediction.html", {"request": request, "hosts": hosts})
    # Consulta a la base de datos para obtener todos los hosts únicos
    #query = 'SHOW TAG VALUES FROM "espaciodisco" WITH KEY = "host"' # Puedes cambiar 'espaciodisco' por la tabla correcta si es diferente
    #resultados = client.query(query)
# Extrayendo los valores de los hosts de los resultados
    #hosts = [host_value['value'] for host_value in resultados.get_points()]
    #hosts = get_all_hosts()
    #graph_html = fig.to_html(full_html=False)
    #return templates.TemplateResponse("prediction.html", {"request": request, "hosts": hosts})

@app.post("/predict_system", response_class=HTMLResponse)
def predict_system(request: Request, metric: str = Form(...), hours_ahead: int = Form(...), host: str = Form(...)):
    if metric not in ["disk", "cpu", "ram"]:
        error_msg = "Invalid metric selected"
        return templates.TemplateResponse("error.html", {"request": request, "error": error_msg})

    # Seleccionamos la métrica desde la base de datos
    if metric == "disk":
        query = 'SELECT * FROM espaciodisco'
        column_to_predict = 'MB_Free'
        yaxis_title = "MB Free"
    elif metric == "cpu":
        query = 'SELECT * FROM usocpu'
        column_to_predict = 'Percent_Used'
        yaxis_title = "Uso de CPU (%)" 
    else:  # RAM
        query = 'SELECT * FROM usomemoria'
        column_to_predict = 'GB_Used'
        yaxis_title = "Uso de Memoria RAM (GB)"

    resultados = client.query(query)
    df = pd.DataFrame(list(resultados.get_points()))
    print(df.head())
    if host not in df['host'].unique():
        error_msg = f"El host {host} no se encontró en la base de datos."
        return templates.TemplateResponse("error.html", {"request": request, "error": error_msg})
        print(df['host'].unique())
        df = df[df['host'] == host]
        print(df.shape)
    else:
     df = df[df['host'] == host]
     print(df.shape)
   
    if host:
        df = df[df['host'] == host]
        print(df)
    df['time'] = pd.to_datetime(df['time'], unit='ns')
    print(f"NaN values before interpolation: {df[column_to_predict].isna().sum()}")
    df_resampled = df.set_index('time')[column_to_predict].resample('H').mean().interpolate()
    print(f"NaN values after interpolation: {df_resampled.isna().sum()}")
    
    # Comprobar si todos los datos interpolados son NaN
    if df_resampled.isna().all():
        error_msg = "Todos los datos interpolados son NaN."
        return templates.TemplateResponse("error.html", {"request": request, "error": error_msg})

    # Transformación logarítmica de los datos
    df_resampled_log = np.log(df_resampled.replace(0, np.nan).fillna(method='bfill'))

    try:
        # Determinar los mejores parámetros con auto_arima
        best_sarima_model = auto_arima(df_resampled_log, seasonal=True, stepwise=True,
                                       suppress_warnings=True, D=1, max_P=3, max_order=None, trace=True,
                                       error_action='ignore', approximations=False)
        
        # Usar un modelo SARIMA
        model = SARIMAX(df_resampled_log, order=best_sarima_model.order, seasonal_order=best_sarima_model.seasonal_order)
        model_fit = model.fit(disp=False)

        forecast = model_fit.forecast(steps=hours_ahead)
        prediction = np.exp(forecast[-hours_ahead:].tolist())  # Revertir la transformación logarítmica

    except Exception as e:
        error_msg = f"Error al ajustar el modelo: {str(e)}"
        return templates.TemplateResponse("error.html", {"request": request, "error": error_msg})

    # Generar gráfico
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=prediction, mode='lines+markers', name='Predicción'))
    fig.update_layout(
        title=f"Predicción del {yaxis_title} para las próximas {hours_ahead} horas",
        xaxis_title="Horas en el futuro",
        yaxis_title=yaxis_title,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white')
    )

    hosts = get_all_hosts()
    graph_html = fig.to_html(full_html=False)
    return templates.TemplateResponse("prediction.html", {"request": request, "graph": graph_html, "hosts": hosts})
