"""
Servidor Flask para el generador de fixtures.

Expone rutas REST para importar equipos desde CSV, generar un fixture
con la configuración deseada y exportar la programación a PDF.  Está
pensado como backend de una aplicación web y puede integrarse con bases de
datos externas para persistir datos.

Se añadió una ruta `/generate_parts` para obtener por separado la lista de
partidos (enfrentamientos) y la tabla de horarios disponibles.  Esto
permite que una interfaz de usuario distribuya manualmente los partidos
arrastrándolos a los horarios deseados.
"""

import os
from flask import Flask, request, jsonify, send_file

from fixture_generator import (
    read_teams_from_csv,
    generate_fixture,
    export_to_pdf,
    generate_timeslots_list,
    generate_match_list,
    Team,
    Match,
)

# Crear aplicación Flask
# Configurar Flask para servir archivos estáticos desde el directorio `templates`
app = Flask(__name__, static_folder='templates', static_url_path='')

# Variables globales simples para mantener estado entre llamadas
loaded_teams: list[Team] = []
current_schedule: list[Match] = []

# Ruta para servir la página principal y archivos estáticos
@app.route('/')
def index_page() -> any:
    """Sirve el archivo HTML principal."""
    return send_file(os.path.join(app.static_folder, 'index.html'))


@app.route('/<path:filename>')
def static_files(filename: str) -> any:
    """Sirve archivos estáticos como CSS y JS."""
    file_path = os.path.join(app.static_folder, filename)
    if os.path.isfile(file_path):
        return send_file(file_path)
    # Si no existe, devolver 404 y dejar que otras rutas manejen
    return jsonify({"error": "Archivo no encontrado"}), 404


@app.route('/import_teams', methods=['POST'])
def import_teams() -> any:
    """Importa equipos a partir de un archivo CSV enviado en el cuerpo.

    El cuerpo debe contener un archivo en multipart/form-data con el campo
    'file'.  Devuelve un JSON con la lista de equipos importados.
    """
    global loaded_teams
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "Se requiere un archivo CSV."}), 400
    # Guardar archivo temporalmente
    tmp_path = os.path.join('/tmp', file.filename)
    file.save(tmp_path)
    loaded_teams = read_teams_from_csv(tmp_path)
    # Eliminar temporal
    os.remove(tmp_path)
    return jsonify({"teams": [team.__dict__ for team in loaded_teams]})


@app.route('/generate', methods=['POST'])
def generate() -> any:
    """Genera un fixture con la configuración recibida.

    El cuerpo debe ser JSON y puede contener:
      - teams_csv: ruta a un archivo CSV (si no se han cargado equipos).
      - system: '8x3', '4x6' o 'rr'.
      - days, fields: números enteros.
      - start_time, end_time: strings HH:MM.
      - match_duration, rest: enteros (minutos).
      - midday_break: lista ["HH:MM", "HH:MM"] o null.
      - home_and_away: booleano.
      - max_matches_per_day: entero opcional.

    Devuelve un listado de partidos en JSON.
    """
    global loaded_teams, current_schedule
    data = request.get_json(force=True)
    # Si se proporciona archivo CSV, cargarlo
    if 'teams_csv' in data:
        csv_path = data['teams_csv']
        # Validar existencia
        if not os.path.exists(csv_path):
            return jsonify({"error": f"No se encontró el archivo {csv_path}."}), 400
        loaded_teams = read_teams_from_csv(csv_path)
    if not loaded_teams:
        return jsonify({"error": "No hay equipos cargados."}), 400
    system = data.get('system', 'rr')
    days = int(data.get('days', 1))
    fields = int(data.get('fields', 1))
    start_time = data.get('start_time', '09:00')
    end_time = data.get('end_time', '18:00')
    match_duration = int(data.get('match_duration', 60))
    rest = int(data.get('rest', match_duration))
    midday_break = data.get('midday_break')
    if midday_break and isinstance(midday_break, list) and len(midday_break) == 2:
        midday_break_tuple = (midday_break[0], midday_break[1])
    else:
        midday_break_tuple = None
    home_and_away = bool(data.get('home_and_away', False))
    max_per_day = data.get('max_matches_per_day')
    max_per_day_int = int(max_per_day) if max_per_day is not None else None
    # Generar fixture
    try:
        current_schedule = generate_fixture(
            teams=loaded_teams,
            system=system,
            days=days,
            fields=fields,
            start_time=start_time,
            end_time=end_time,
            match_duration=match_duration,
            rest=rest,
            midday_break=midday_break_tuple,
            home_and_away=home_and_away,
            max_matches_per_day=max_per_day_int
        )
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    # Convertir a JSON
    return jsonify({
        "schedule": [match.__dict__ for match in current_schedule]
    })


@app.route('/generate_parts', methods=['POST'])
def generate_parts() -> any:
    """Genera por separado la tabla de horarios y la lista de partidos.

    Esta ruta permite obtener dos listas: una con todos los partidos a jugar
    (sin asignación de día/cancha) y otra con todos los timeslots disponibles
    según la configuración de días, canchas y horarios.  De esta manera, una
    interfaz de usuario puede arrastrar cada partido al horario deseado y
    aplicar las restricciones correspondientes en el navegador.

    El cuerpo debe ser JSON y puede contener los mismos campos que `/generate`.

    Devuelve un objeto JSON con claves `timeslots` y `matches`.
    """
    global loaded_teams
    data = request.get_json(force=True)
    # Cargar equipos de CSV si se especifica
    if 'teams_csv' in data:
        csv_path = data['teams_csv']
        if not os.path.exists(csv_path):
            return jsonify({"error": f"No se encontró el archivo {csv_path}."}), 400
        loaded_teams = read_teams_from_csv(csv_path)
    if not loaded_teams:
        return jsonify({"error": "No hay equipos cargados."}), 400
    system = data.get('system', 'rr')
    days = int(data.get('days', 1))
    fields = int(data.get('fields', 1))
    start_time = data.get('start_time', '09:00')
    end_time = data.get('end_time', '18:00')
    match_duration = int(data.get('match_duration', 60))
    midday_break = data.get('midday_break')
    if midday_break and isinstance(midday_break, list) and len(midday_break) == 2:
        midday_break_tuple = (midday_break[0], midday_break[1])
    else:
        midday_break_tuple = None
    home_and_away = bool(data.get('home_and_away', False))
    # Generar lista de horarios disponibles y lista de enfrentamientos
    timeslots = generate_timeslots_list(days=days,
                                        fields=fields,
                                        start_time=start_time,
                                        end_time=end_time,
                                        match_duration=match_duration,
                                        midday_break=midday_break_tuple)
    matches = generate_match_list(loaded_teams, system=system, home_and_away=home_and_away)
    return jsonify({
        "timeslots": timeslots,
        "matches": matches
    })


@app.route('/export_pdf', methods=['GET'])
def export_pdf() -> any:
    """Exporta el fixture cargado a un archivo PDF y lo devuelve.

    Se puede pasar el parámetro 'filename' como query para nombrar el archivo.
    """
    global current_schedule
    if not current_schedule:
        return jsonify({"error": "No hay un fixture generado."}), 400
    filename = request.args.get('filename', 'fixture.pdf')
    output_path = os.path.join('/tmp', filename)
    # Generar PDF
    export_to_pdf(current_schedule, output_path, title='Fixture generado')
    return send_file(output_path, as_attachment=True, download_name=filename)


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 3000))  # usa 3000 por defecto si no hay PORT definido
    app.run(host='0.0.0.0', port=port, debug=True)
