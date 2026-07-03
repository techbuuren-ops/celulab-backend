from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import os
import shutil
import psycopg2

app = FastAPI(title="SaaS Control de Reparaciones - API en la Nube")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite que tu Live Server local se conecte sin restricciones
    allow_credentials=False,
    allow_methods=["*"],  # Permite GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],  # Permite todos los encabezados
)

# Cadena de conexión oficial a tu Supabase
DB_URI = "postgresql://postgres:Buuren2708@db.sohavacqphahseoezale.supabase.co:5432/postgres"
CARPETA_UPLOADS = "uploads"

if not os.path.exists(CARPETA_UPLOADS):
    os.makedirs(CARPETA_UPLOADS)

def obtener_conexion():
    return psycopg2.connect(DB_URI)

def inicializar_base_de_datos():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS equipos_reparacion (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL,
            cliente_nombre TEXT NOT NULL,
            cliente_telefono TEXT NOT NULL,
            tipo_equipo TEXT NOT NULL,
            marca_modelo TEXT NOT NULL,
            numero_serie TEXT,
            accesorios TEXT,
            falla_reportada TEXT NOT NULL,
            costo_estimado REAL DEFAULT 0.0,
            costo_final REAL DEFAULT 0.0,
            ruta_foto_local TEXT,
            estado TEXT DEFAULT 'recibido',
            tecnico_receptor TEXT, 
            fecha_ingreso TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Intento de migración limpia para PostgreSQL
    try:
        cursor.execute("ALTER TABLE equipos_reparacion ADD COLUMN costo_final REAL DEFAULT 0.0")
    except Exception:
        conexion.rollback() # Si la columna ya existe, cancelamos el error limpiamente
    else:
        conexion.commit()

    conexion.commit()
    conexion.close()

def inicializar_inventario():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventario (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER DEFAULT 1,
            nombre TEXT NOT NULL,
            categoria TEXT NOT NULL,
            stock INTEGER DEFAULT 0,
            precio_costo REAL DEFAULT 0.0,
            precio_venta REAL DEFAULT 0.0,
            estado_fisico TEXT DEFAULT 'Buen Estado',
            observaciones TEXT DEFAULT ''             
        )
    """)
    conexion.commit()
    conexion.close()

# Inicializamos ambas estructuras en Supabase
inicializar_base_de_datos()
inicializar_inventario()

@app.get("/api/equipos")
def obtener_equipos(tenant_id: int = 1):
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        cursor.execute("""
            SELECT id, cliente_nombre, cliente_telefono, tipo_equipo, 
                   marca_modelo, numero_serie, accesorios, falla_reportada, 
                   costo_estimado, costo_final, ruta_foto_local, estado, tecnico_receptor, fecha_ingreso 
            FROM equipos_reparacion 
            WHERE tenant_id = %s 
            ORDER BY id DESC
        """, (tenant_id,))
        
        filas = cursor.fetchall()
        
        # Mapeo manual de columnas ya que PostgreSQL no cuenta con row_factory de forma nativa
        columnas = [
            "id", "cliente_nombre", "cliente_telefono", "tipo_equipo", 
            "marca_modelo", "numero_serie", "accesorios", "falla_reportada", 
            "costo_estimado", "costo_final", "ruta_foto_local", "estado", "tecnico_receptor", "fecha_ingreso"
        ]
        
        equipos = [dict(zip(columnas, fila)) for fila in filas]
        conexion.close()
        return {"success": True, "equipos": equipos}
    except Exception as e:
        return {"success": False, "mensaje": f"Error: {str(e)}"}

@app.post("/api/equipos")
async def registrar_equipo(
    tenant_id: int = Form(...),
    cliente_nombre: str = Form(...),
    cliente_telefono: str = Form(...),
    tipo_equipo: str = Form(...),
    marca_modelo: str = Form(...),
    falla_reportada: str = Form(...),
    tecnico_receptor: str = Form(...),
    numero_serie: Optional[str] = Form(None),
    accesorios: Optional[str] = Form(None),
    costo_estimado: float = Form(0.0),
    foto: Optional[UploadFile] = File(None)
):
    ruta_foto_guardada = None
    if foto:
        ruta_foto_guardada = os.path.join(CARPETA_UPLOADS, foto.filename)
        with open(ruta_foto_guardada, "wb") as buffer:
            shutil.copyfileobj(foto.file, buffer)

    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        query = """
            INSERT INTO equipos_reparacion 
            (tenant_id, cliente_nombre, cliente_telefono, tipo_equipo, marca_modelo, numero_serie, accesorios, falla_reportada, costo_estimado, costo_final, ruta_foto_local, tecnico_receptor)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """
        
        cursor.execute(query, (
            tenant_id, cliente_nombre, cliente_telefono, tipo_equipo, 
            marca_modelo, numero_serie, accesorios, falla_reportada, 
            costo_estimado, costo_estimado, ruta_foto_guardada, tecnico_receptor
        ))
        
        id_generado = cursor.fetchone()[0]
        conexion.commit()
        conexion.close()
        return {"success": True, "mensaje": f"Orden #{id_generado} creada."}
    except Exception as e:
        return {"success": False, "mensaje": f"Error: {str(e)}"}

@app.post("/api/equipos/actualizar-estado")
def actualizar_estado(
    id: int = Form(...), 
    nuevo_estado: str = Form(...),
    costo_final: Optional[float] = Form(None)
):
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        if nuevo_estado == 'terminado' and costo_final is not None:
            cursor.execute("""
                UPDATE equipos_reparacion 
                SET estado = %s, costo_final = %s 
                WHERE id = %s
            """, (nuevo_estado, costo_final, id))
        else:
            cursor.execute("""
                UPDATE equipos_reparacion 
                SET estado = %s 
                WHERE id = %s
            """, (nuevo_estado, id))
            
        conexion.commit()
        conexion.close()
        return {"success": True, "mensaje": "Orden actualizada correctamente."}
    except Exception as e:
        return {"success": False, "mensaje": f"Error: {str(e)}"}

@app.post("/api/equipos/editar-orden")
def editar_orden(
    id: int = Form(...),
    cliente_nombre: str = Form(...),
    marca_modelo: str = Form(...),
    falla_reportada: str = Form(...),
    accesorios: str = Form(...)
):
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        cursor.execute("""
            UPDATE equipos_reparacion 
            SET cliente_nombre = %s, marca_modelo = %s, falla_reportada = %s, accesorios = %s
            WHERE id = %s
        """, (cliente_nombre, marca_modelo, falla_reportada, accesorios, id))
        
        conexion.commit()
        conexion.close()
        return {"success": True, "mensaje": "Orden editada correctamente."}
    except Exception as e:
        return {"success": False, "mensaje": f"Error al editar: {str(e)}"}

@app.post("/api/equipos/eliminar-orden")
def eliminar_orden(id: int = Form(...)):
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        cursor.execute("SELECT id FROM equipos_reparacion WHERE id = %s", (id,))
        existe = cursor.fetchone()
        
        if not existe:
            conexion.close()
            return {"success": False, "mensaje": "La orden no existe."}
            
        cursor.execute("DELETE FROM equipos_reparacion WHERE id = %s", (id,))
        conexion.commit()
        conexion.close()
        return {"success": True, "mensaje": "Orden eliminada correctamente."}
    except Exception as e:
        return {"success": False, "mensaje": f"Error: {str(e)}"}

@app.get("/api/inventario")
def obtener_inventario():
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("SELECT id, nombre, categoria, stock, precio_costo, precio_venta, estado_fisico, observaciones FROM inventario ORDER BY categoria ASC, nombre ASC")
        productos = cursor.fetchall()
        conexion.close()
        
        lista_productos = []
        for p in productos:
            lista_productos.append({
                "id": p[0], "nombre": p[1], "categoria": p[2],
                "stock": p[3], "precio_costo": p[4], "precio_venta": p[5],
                "estado_fisico": p[6], "observaciones": p[7]
            })
        return {"success": True, "productos": lista_productos}
    except Exception as e:
        return {"success": False, "mensaje": str(e)}

@app.post("/api/inventario/agregar")
def agregar_producto(
    nombre: str = Form(...),
    categoria: str = Form(...),
    stock: int = Form(...),
    precio_costo: float = Form(...),
    precio_venta: float = Form(...),
    estado_fisico: str = Form("Buen Estado"),
    observaciones: str = Form("")
):
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("""
            INSERT INTO inventario (nombre, categoria, stock, precio_costo, precio_venta, estado_fisico, observaciones)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (nombre, categoria, stock, precio_costo, precio_venta, estado_fisico, observaciones))
        conexion.commit()
        conexion.close()
        return {"success": True, "mensaje": "Elemento registrado con éxito."}
    except Exception as e:
        return {"success": False, "mensaje": str(e)}

@app.post("/api/inventario/actualizar-stock")
def actualizar_stock(id: int = Form(...), nuevo_stock: int = Form(...)):
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("UPDATE inventario SET stock = %s WHERE id = %s", (nuevo_stock, id))
        conexion.commit()
        conexion.close()
        return {"success": True, "mensaje": "Cantidad actualizada."}
    except Exception as e:
        return {"success": False, "mensaje": str(e)}

@app.post("/api/inventario/eliminar")
def eliminar_producto(id: int = Form(...)):
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("DELETE FROM inventario WHERE id = %s", (id,))
        conexion.commit()
        conexion.close()
        return {"success": True, "mensaje": "Eliminado correctamente."}
    except Exception as e:
        return {"success": False, "mensaje": str(e)}
