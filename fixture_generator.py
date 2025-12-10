"""Módulo de generación de calendarios (fixtures) para torneos deportivos.

Proporciona funciones para importar equipos desde CSV, dividirlos en zonas
y generar calendarios todos contra todos con asignación de fechas, horas
y canchas bajo múltiples restricciones (número de días, descanso, corte al
mediodía, etc.).  Además incluye utilidades para exportar el resultado
en formato PDF.

Este módulo se ha ampliado para ofrecer funciones que separan la
generación de la lista de partidos (enfrentamientos) de la generación
de los horarios disponibles (timeslots).  Estas funciones permiten que
una interfaz de usuario asigne manualmente cada partido a un horario
con restricciones, facilitando así la planificación manual.
"""

from __future__ import annotations

import csv
import datetime as _dt
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional, Iterable, Any

from dateutil import parser as _parser
# La biblioteca fpdf se usa solo al exportar a PDF.  Se importa dinámicamente
# en la función export_to_pdf para evitar que falte durante la generación
import pandas as pd


@dataclass
class Team:
    """Representa un equipo y su zona."""
    name: str
    zone: str


@dataclass
class Match:
    """Representa un partido programado."""
    day: int
    time: str
    field: str
    home: str
    away: str
    zone: str
    round: int = 1
    match_id: int = field(default=0)


def read_teams_from_csv(csv_path: str) -> List[Team]:
    """Lee un archivo CSV con cabecera `Zona;Equipos` y devuelve una lista de Team.

    Args:
        csv_path: Ruta al archivo CSV.

    Returns:
        Lista de Team, con nombres y zonas.
    """
    teams: List[Team] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            zone = row.get('Zona', '').strip()
            name = str(row.get('Equipos', '')).strip()
            if name:
                teams.append(Team(name=name, zone=zone))
    return teams


def assign_zones(teams: List[Team], system: str) -> List[Team]:
    """Asigna zonas a los equipos según el sistema (por ejemplo '8x3' o '4x6').

    Si los equipos ya tienen zona, no se modifica.  Si el sistema requiere
    reagrupamiento, asigna zonas secuencialmente.

    Args:
        teams: Lista de equipos.
        system: Sistema de competencia, admite '8x3' o '4x6' o 'rr' (round robin general).

    Returns:
        Lista de equipos con zona asignada.
    """
    # Si todos tienen zona asignada, no hacemos nada
    if all(team.zone for team in teams):
        return teams
    n = len(teams)
    system = system.lower()
    if system == '8x3' and n == 24:
        # ocho zonas de 3 equipos
        group_size = 3
    elif system == '4x6' and n == 24:
        group_size = 6
    else:
        # round robin general: todos en la misma zona 'A'
        for team in teams:
            team.zone = 'A'
        return teams
    zones = [chr(ord('A') + i) for i in range(n // group_size)]
    for idx, team in enumerate(teams):
        team.zone = zones[idx // group_size]
    return teams


def generate_round_robin(team_names: List[str], home_and_away: bool = False) -> List[List[Tuple[str, str]]]:
    """Genera un calendario round-robin de partidos para la lista de equipos.

    Se utiliza el algoritmo de rotación (método del círculo).  Si el número de
    equipos es impar, se agrega un "bye" (descanso).  Si `home_and_away` es
    True, se generan dos vueltas invirtiendo localías.

    Args:
        team_names: Nombres de los equipos.
        home_and_away: Si se deben jugar partidos de ida y vuelta.

    Returns:
        Lista de rondas, cada una con una lista de tuplas (local, visitante).
    """
    teams = list(team_names)
    # Añadir bye si es impar
    if len(teams) % 2 == 1:
        teams.append('BYE')
    n = len(teams)
    rounds: List[List[Tuple[str, str]]] = []
    for round_idx in range(n - 1):
        matches: List[Tuple[str, str]] = []
        for i in range(n // 2):
            home = teams[i]
            away = teams[n - 1 - i]
            # Saltar partidos contra BYE
            if home != 'BYE' and away != 'BYE':
                matches.append((home, away))
        rounds.append(matches)
        # Rotar equipos (excepto el primero)
        teams = [teams[0]] + teams[-1:] + teams[1:-1]
    if home_and_away:
        # Añadir segunda vuelta invirtiendo localía
        return rounds + [[(away, home) for (home, away) in rnd] for rnd in rounds]
    return rounds


def _time_to_minutes(time_str: str) -> int:
    """Convierte una cadena HH:MM a minutos desde medianoche."""
    h, m = map(int, time_str.split(':'))
    return h * 60 + m


def _minutes_to_time(minutes: int) -> str:
    """Convierte minutos desde medianoche en cadena HH:MM."""
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def _generate_timeslots(days: int,
                         fields: int,
                         start_time: str,
                         end_time: str,
                         match_duration: int,
                         midday_break: Optional[Tuple[str, str]] = None) -> List[Tuple[int, str, str, int]]:
    """Genera una lista de timeslots (día, hora, cancha, índice absoluto).

    Args:
        days: Número de días del torneo.
        fields: Número de canchas disponibles.
        start_time: Hora de inicio de la primera franja (HH:MM).
        end_time: Hora de finalización del último partido (HH:MM).
        match_duration: Duración del partido en minutos.
        midday_break: Tupla opcional con hora inicio y fin del descanso (HH:MM).

    Returns:
        Lista de tuplas (día, hora, cancha, index) ordenadas cronológicamente.
    """
    start_min = _time_to_minutes(start_time)
    end_min = _time_to_minutes(end_time)
    break_start = break_end = None
    if midday_break:
        break_start = _time_to_minutes(midday_break[0])
        break_end = _time_to_minutes(midday_break[1])
    timeslots = []
    index = 0
    for day in range(1, days + 1):
        current = start_min
        while current + match_duration <= end_min:
            # Comprobar si cae dentro del corte al mediodía
            if break_start is not None and break_start <= current < break_end:
                current = break_end
                continue
            time_str = _minutes_to_time(current)
            for field_num in range(1, fields + 1):
                field_name = f"c{field_num}"
                timeslots.append((day, time_str, field_name, index))
                index += 1
            current += match_duration
    return timeslots


# --- Nuevas funciones públicas para separar la generación del fixture ---

def generate_timeslots_list(days: int,
                            fields: int,
                            start_time: str = "09:00",
                            end_time: str = "18:00",
                            match_duration: int = 60,
                            midday_break: Optional[Tuple[str, str]] = None) -> List[Dict[str, Any]]:
    """Genera una lista de diccionarios con todos los espacios disponibles para jugar.

    Cada diccionario contiene el día de competencia, la hora de inicio, la cancha y
    un índice absoluto para mantener el orden cronológico.  Esta función se
    expone para generar la tabla de horarios sin asignar partidos.

    Args:
        days: Número de días de competencia.
        fields: Número de canchas disponibles por día.
        start_time: Hora de inicio de la jornada (HH:MM).
        end_time: Hora de fin de la jornada (HH:MM).
        match_duration: Duración de cada partido en minutos.
        midday_break: Pausa al mediodía como tupla (inicio, fin) en HH:MM.

    Returns:
        Lista de diccionarios con claves `day`, `time`, `field` e `index`.
    """
    raw_slots = _generate_timeslots(days, fields, start_time, end_time, match_duration, midday_break)
    slots_list: List[Dict[str, Any]] = []
    for day, time_str, field_name, index in raw_slots:
        slots_list.append({
            "day": day,
            "time": time_str,
            "field": field_name,
            "index": index
        })
    return slots_list


def generate_match_list(teams: List[Team],
                        system: str,
                        home_and_away: bool = False) -> List[Dict[str, Any]]:
    """Devuelve la lista de partidos a disputar sin asignar horario ni cancha.

    A partir de la lista de equipos y el sistema de competencia (8x3, 4x6 o rr),
    genera todas las combinaciones de partidos para cada zona según el esquema
    round robin.  No se asignan días ni campos; estos datos se dejarán para el
    usuario final que distribuya los encuentros en los horarios disponibles.

    Args:
        teams: Lista de Team con nombres y zonas (si corresponde).
        system: Sistema de competencia ('8x3', '4x6' o 'rr').
        home_and_away: Si se deben programar partidos de ida y vuelta.

    Returns:
        Lista de diccionarios con claves `zone`, `home`, `away` y `round`.
    """
    # Asignar zonas en función del sistema
    teams_with_zone = assign_zones(list(teams), system)
    # Agrupar equipos por zona
    zones: Dict[str, List[Team]] = {}
    for t in teams_with_zone:
        zones.setdefault(t.zone, []).append(t)
    match_list: List[Dict[str, Any]] = []
    for zone_name, zone_teams in zones.items():
        team_names = [t.name for t in zone_teams]
        rounds = generate_round_robin(team_names, home_and_away)
        for round_idx, pairs in enumerate(rounds, start=1):
            for home, away in pairs:
                match_list.append({
                    "zone": zone_name,
                    "home": home,
                    "away": away,
                    "round": round_idx
                })
    return match_list


def generate_fixture(teams: List[Team],
                     system: str,
                     days: int,
                     fields: int,
                     start_time: str = "09:00",
                     end_time: str = "18:00",
                     match_duration: int = 60,
                     rest: int = 60,
                     midday_break: Optional[Tuple[str, str]] = None,
                     home_and_away: bool = False,
                     max_matches_per_day: Optional[int] = None) -> List[Match]:
    """Genera un fixture completo con asignación de fechas y canchas.

    Se agrupan los equipos según el sistema indicado (por ejemplo, 8x3 crea
    ocho zonas de tres equipos) y se genera un calendario round robin para
    cada zona.  Luego se asignan los partidos a los timeslots disponibles
    respetando los descansos mínimos.

    Args:
        teams: Lista de Team.
        system: Tipo de sistema ('8x3', '4x6' o 'rr').
        days: Número de días del torneo.
        fields: Número de canchas disponibles.
        start_time: Hora de inicio de la jornada.
        end_time: Hora de cierre de la jornada.
        match_duration: Duración de cada partido en minutos.
        rest: Descanso mínimo entre partidos de un mismo equipo (minutos).
        midday_break: Descanso al mediodía (inicio, fin) como tupla de strings.
        home_and_away: Si se juegan partidos de ida y vuelta.
        max_matches_per_day: Máximo de partidos totales por día (opcional).

    Returns:
        Lista de Match con asignaciones de día, hora y cancha.
    """
    # Primero, asignar zonas si corresponde
    teams = assign_zones(teams, system)
    # Agrupar por zona
    zones: Dict[str, List[Team]] = {}
    for t in teams:
        zones.setdefault(t.zone, []).append(t)
    # Generar partidos por zona
    matches_unassigned: List[Tuple[str, str, str, int]] = []  # (zona, home, away, round)
    for zone_name, zone_teams in zones.items():
        team_names = [t.name for t in zone_teams]
        rounds = generate_round_robin(team_names, home_and_away)
        for round_index, pairs in enumerate(rounds, start=1):
            for home, away in pairs:
                matches_unassigned.append((zone_name, home, away, round_index))
    # Generar timeslots
    timeslots = _generate_timeslots(days, fields, start_time, end_time,
                                    match_duration, midday_break)
    # Ordenar timeslots por índice absoluto (precalculado)
    timeslots.sort(key=lambda x: x[3])
    # Tracking de último partido (tiempo absoluto) por equipo
    last_played: Dict[str, int] = {}
    schedule: List[Match] = []
    # Convertir rest a minutos
    rest_minutes = rest
    # Convertir timeslot a tiempo absoluto en minutos para comparaciones
    timeslot_absolute = [((day, time_str, field), ((day - 1) * 24 * 60 + _time_to_minutes(time_str)))
                         for (day, time_str, field, _) in timeslots]
    # Asignar partidos secuencialmente
    for zone, home, away, round_idx in matches_unassigned:
        assigned = False
        for idx, ((day, time_str, field), abs_time) in enumerate(timeslot_absolute):
            # Comprobar si ese timeslot está libre
            if idx in {m.match_id for m in schedule}:
                continue
            # Comprobar descanso para ambos equipos
            last_home = last_played.get(home, -1_000_000)
            last_away = last_played.get(away, -1_000_000)
            if abs_time - last_home < rest_minutes:
                continue
            if abs_time - last_away < rest_minutes:
                continue
            # Comprobar máximo partidos por día
            if max_matches_per_day is not None:
                day_matches = sum(1 for m in schedule if m.day == day)
                if day_matches >= max_matches_per_day:
                    continue
            # Asignar
            schedule.append(Match(day=day, time=time_str, field=field,
                                  home=home, away=away,
                                  zone=zone, round=round_idx, match_id=idx))
            last_played[home] = abs_time
            last_played[away] = abs_time
            assigned = True
            break
        if not assigned:
            raise RuntimeError("No se pudo asignar un horario a todos los partidos.\n"
                               "Ajuste parámetros de días, canchas o descanso.")
    # Ordenar por día, hora y cancha
    schedule.sort(key=lambda m: (m.day, _time_to_minutes(m.time), m.field))
    # Reasignar IDs secuenciales para imprimir
    for idx, match in enumerate(schedule, start=1):
        match.match_id = idx
    return schedule


def export_to_pdf(schedule: List[Match], output_path: str, title: Optional[str] = None) -> None:
    """Exporta el fixture a un PDF con una tabla ordenada por día.

    Args:
        schedule: Lista de Match ya asignados.
        output_path: Ruta del archivo PDF a generar.
        title: Título opcional para el documento.
    """
    # Importar FPDF cuando sea necesario
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise ImportError(
            "La biblioteca fpdf no está disponible. Instale fpdf2 para exportar a PDF."
        ) from exc
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    current_day = None
    for match in schedule:
        if match.day != current_day:
            current_day = match.day
            pdf.add_page()
            if title:
                pdf.set_font("Arial", 'B', 14)
                pdf.cell(0, 10, title, ln=True, align='C')
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, f"Día {match.day}", ln=True)
            # Encabezado de tabla
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(20, 7, "Fecha", border=1)
            pdf.cell(15, 7, "Hora", border=1)
            pdf.cell(15, 7, "Cancha", border=1)
            pdf.cell(25, 7, "Local", border=1)
            pdf.cell(25, 7, "Visitante", border=1)
            pdf.cell(10, 7, "Zona", border=1)
            pdf.cell(30, 7, "Fase/Ronda", border=1)
            pdf.cell(10, 7, "ID", border=1, ln=True)
        # Datos del partido
        pdf.set_font("Arial", '', 9)
        # Usar fecha ficticia: se podría mapear día a fechas reales en otra función
        fecha = f"2025-01-{match.day:02d}"
        pdf.cell(20, 6, fecha, border=1)
        pdf.cell(15, 6, match.time, border=1)
        pdf.cell(15, 6, match.field, border=1)
        pdf.cell(25, 6, str(match.home), border=1)
        pdf.cell(25, 6, str(match.away), border=1)
        pdf.cell(10, 6, match.zone, border=1)
        pdf.cell(30, 6, f"Ronda {match.round}", border=1)
        pdf.cell(10, 6, str(match.match_id), border=1, ln=True)
    pdf.output(output_path)