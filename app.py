from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import datetime, date
import os
import json
import traceback

import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'marunails_secret_2026')

SPREADSHEET_ID = '13z9C__dSAbudO_shv0K2uFgGVa51lTpWVTTkTdjYqbI'
TC_USD = 17
PCT_TARJETA = 0.0302

STAFF = [
    {'nombre': 'FLOR',            'comision': 0.4},
    {'nombre': 'FANNY',           'comision': 0.4},
    {'nombre': 'MARU',            'comision': 0.4},
    {'nombre': 'KAREN RECEPCION', 'comision': 0.3},
    {'nombre': 'KAREN',           'comision': 0.4},
    {'nombre': 'MILI',            'comision': 0.3},
]

SERVICIOS = [
    'Manos Gel', 'Pies Gel', 'Esculpidas', 'Lifting', 'Laminado',
    'Perfilado', 'Facial', 'Extension pestañas', 'Manicura Spa',
    'Kapping Gel', 'Extras', 'Acrilicas Esculpidas', 'Services Esculpidas',
    'Pedicure Spa', 'Depilacion rostro', 'Seña',
]

MEDIOS_PAGO = ['Efectivo', 'Tarjeta', 'Transferencia', 'USD cash', 'Otro']

CATEGORIAS_GASTO = [
    'Productos', 'Renta', 'Servicios', 'Sueldos/Comisiones', 'Marketing',
    'Impuestos', 'Otros', 'Gastos Operativos', 'Retiros -Mariana',
    'Inversiones nuevas', 'Prestamos',
]

MESES_ES = {
    1: 'ene', 2: 'feb', 3: 'mar', 4: 'abr', 5: 'may', 6: 'jun',
    7: 'jul', 8: 'ago', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dic',
}


def format_fecha(d):
    return f"{d.day:02d}-{MESES_ES[d.month]}-{d.year}"


def get_week_quincena(d):
    semana = d.isocalendar()[1]
    mes    = d.strftime('%Y-%m')
    q      = 'Q1' if d.day <= 15 else 'Q2'
    return semana, mes, f'{mes}-{q}'


def get_sheets_client():
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    if not creds_json:
        raise RuntimeError('Variable GOOGLE_CREDENTIALS no configurada.')
    info   = json.loads(creds_json)
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    creds  = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)


def append_after_last_data(ws, row):
    all_vals = ws.get_all_values()
    last_row = 0
    for i, r in enumerate(all_vals):
        if any(c.strip() for c in r):
            last_row = i + 1
    next_row = last_row + 1
    ws.update(f'A{next_row}', [row], value_input_option='USER_ENTERED')


# ── DASHBOARD ──────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


# ── REGISTRAR CORTE ────────────────────────────────────────────────────────────
@app.route('/corte', methods=['GET', 'POST'])
def corte():
    if request.method == 'POST':
        fecha_str     = request.form.get('fecha')
        cliente       = request.form.get('cliente', '').strip() or 'Walk in'
        staff_nombre  = request.form.get('staff')
        servicio      = request.form.get('servicio')
        moneda        = request.form.get('moneda', 'MXN')
        total_cobrado = float(request.form.get('total_cobrado') or 0)
        propina       = float(request.form.get('propina') or 0)
        medio_pago    = request.form.get('medio_pago')
        notas         = request.form.get('notas', '').strip()

        if not staff_nombre or not servicio or not medio_pago or total_cobrado <= 0:
            flash('Completá todos los campos obligatorios.', 'error')
            return redirect(url_for('corte'))

        d             = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        tc            = TC_USD if moneda == 'USD' else 1
        venta_neta    = total_cobrado - propina
        total_mxn     = round(total_cobrado * tc, 2)
        propina_mxn   = round(propina * tc, 2)
        neto_mxn      = round(venta_neta * tc, 2)
        semana, mes, quincena = get_week_quincena(d)

        row = [
            format_fecha(d), cliente, staff_nombre, servicio, moneda,
            total_cobrado, propina if propina else '', medio_pago, notas,
            venta_neta, tc, total_mxn, propina_mxn, neto_mxn,
            mes, semana, quincena,
        ]

        try:
            print(f'[CORTE] Intentando escribir fila: {row}', flush=True)
            gc = get_sheets_client()
            sh = gc.open_by_key(SPREADSHEET_ID)
            print(f'[CORTE] Sheet abierto: {sh.title}', flush=True)
            ws = sh.worksheet('INPUT_CORTES')
            print(f'[CORTE] Worksheet encontrado: {ws.title}', flush=True)
            append_after_last_data(ws, row)
            print(f'[CORTE] Fila escrita OK', flush=True)
            flash(f'Corte registrado — {staff_nombre} · {servicio} · ${total_cobrado:,.0f}', 'success')
        except Exception as e:
            print(f'[CORTE] ERROR: {e}', flush=True)
            print(traceback.format_exc(), flush=True)
            flash(f'Error al guardar en Google Sheets: {e}', 'error')

        return redirect(url_for('corte'))

    return render_template('corte.html',
                           staff=STAFF,
                           servicios=SERVICIOS,
                           medios=MEDIOS_PAGO,
                           today=date.today().isoformat())


# ── REGISTRAR GASTO ────────────────────────────────────────────────────────────
@app.route('/gasto', methods=['GET', 'POST'])
def gasto():
    if request.method == 'POST':
        fecha_str    = request.form.get('fecha')
        categoria    = request.form.get('categoria')
        subcategoria = request.form.get('subcategoria', '').strip()
        proveedor    = request.form.get('proveedor', '').strip()
        descripcion  = request.form.get('descripcion', '').strip()
        moneda       = request.form.get('moneda', 'MXN')
        importe      = float(request.form.get('importe') or 0)
        medio_pago   = request.form.get('medio_pago')
        notas        = request.form.get('notas', '').strip()

        if not categoria or not medio_pago or importe == 0:
            flash('Completá todos los campos obligatorios.', 'error')
            return redirect(url_for('gasto'))

        d           = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        tc          = TC_USD if moneda == 'USD' else 1
        importe_mxn = round(importe * tc, 2)
        semana, mes, quincena = get_week_quincena(d)

        row = [
            format_fecha(d), categoria, subcategoria, proveedor, descripcion,
            moneda, importe, medio_pago, notas,
            tc, importe_mxn, mes, semana, quincena,
        ]

        try:
            gc = get_sheets_client()
            ws = gc.open_by_key(SPREADSHEET_ID).worksheet('INPUT_GASTOS')
            append_after_last_data(ws, row)
            flash(f'Gasto registrado — {categoria} · ${importe:,.0f}', 'success')
        except Exception as e:
            flash(f'Error al guardar en Google Sheets: {e}', 'error')

        return redirect(url_for('gasto'))

    return render_template('gasto.html',
                           categorias=CATEGORIAS_GASTO,
                           medios=MEDIOS_PAGO,
                           today=date.today().isoformat())


if __name__ == '__main__':
    print('\n  MaruNails corriendo en http://localhost:5000\n')
    app.run(debug=False, host='0.0.0.0', port=5000)
