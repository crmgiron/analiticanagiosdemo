@app.get("/nagios/disk_space")
def get_disk_space_data():
    connection = mysql.connector.connect(
        host='192.168.87.18',
        user='nagios',
        password='Pait.2023$',
        database='nagios_data'
    )
    
    query = "SELECT output, perfdata FROM servicechecks WHERE output = 'Root Partition'"
    df = pd.read_sql(query, connection)
    connection.close()

    return df.to_dict(orient="records")
