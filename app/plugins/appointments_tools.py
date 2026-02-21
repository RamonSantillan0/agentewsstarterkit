from __future__ import annotations

from typing import Any, Dict, List, Optional, Type
from datetime import datetime, date, time, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.infra.db import engine  # ✅ usar el engine global




SLOT_MIN = 15


class GetAvailabilityInput(BaseModel):
    service: str = Field(..., description="Servicio: limpieza|consulta|urgencia|extraccion")
    date: str = Field(..., description="Fecha YYYY-MM-DD")
    staff: Optional[str] = Field(None, description="Profesional (opcional), ej: Dra. Pérez")


class CreateAppointmentInput(BaseModel):
    service: str = Field(..., description="Servicio")
    start: str = Field(..., description="Inicio ISO: YYYY-MM-DDTHH:MM")
    staff: Optional[str] = Field(None, description="Profesional (opcional)")
    patient_name: Optional[str] = Field(None, description="Nombre del paciente (opcional)")
    notes: Optional[str] = Field(None, description="Notas (opcional)")

class ListAppointmentsInput(BaseModel):
    limit: int = Field(5, ge=1, le=20, description="Cantidad máxima de turnos a listar")
    status: Optional[str] = Field("booked", description="booked|cancelled|completed|all")


class CancelAppointmentInput(BaseModel):
    appointment_id: Optional[int] = Field(None, description="ID del turno a cancelar")
    cancel_next: bool = Field(False, description="Si true, cancela el próximo turno booked del paciente")
    reason: Optional[str] = Field(None, description="Motivo (opcional)")


class RescheduleAppointmentInput(BaseModel):
    appointment_id: int = Field(..., description="ID del turno a reprogramar")
    new_start: str = Field(..., description="Nuevo inicio ISO: YYYY-MM-DDTHH:MM")
    staff: Optional[str] = Field(None, description="Nuevo profesional (opcional)")


def _parse_date(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()

def _parse_time(t: str) -> time:
    return datetime.strptime(t, "%H:%M").time()

def _dt(d: date, t: time) -> datetime:
    return datetime.combine(d, t)

def _business_windows(day: date):
    dow = day.weekday()  # 0=Mon
    if dow == 6:  # Domingo
        return []
    if dow == 5:  # Sábado
        return [(_dt(day, _parse_time("09:00")), _dt(day, _parse_time("12:00")))]
    return [
        (_dt(day, _parse_time("09:00")), _dt(day, _parse_time("13:00"))),
        (_dt(day, _parse_time("16:00")), _dt(day, _parse_time("20:00"))),
    ]

def _service_duration_min(service_code: str) -> int:
    q = text("SELECT duration_min FROM services WHERE code=:code AND active=1 LIMIT 1")
    with engine.begin() as conn:
        row = conn.execute(q, {"code": service_code}).fetchone()
    if not row:
        raise ValueError(f"Servicio inválido o inactivo: {service_code}")
    return int(row[0])

def _staff_id_by_name(staff_name: str) -> Optional[int]:
    q = text("SELECT id FROM staff WHERE name=:name AND active=1 LIMIT 1")
    with engine.begin() as conn:
        row = conn.execute(q, {"name": staff_name}).fetchone()
    return int(row[0]) if row else None

def _busy_starts(staff_id: Optional[int], day: date) -> set[datetime]:
    if staff_id is None:
        return set()
    start_day = _dt(day, _parse_time("00:00"))
    end_day = start_day + timedelta(days=1)
    q = text("""
        SELECT start_at
        FROM appointments
        WHERE staff_id = :staff_id
          AND status = 'booked'
          AND start_at >= :start_day AND start_at < :end_day
    """)
    with engine.begin() as conn:
        rows = conn.execute(q, {"staff_id": staff_id, "start_day": start_day, "end_day": end_day}).fetchall()
    return {r[0] for r in rows}

def _insert_appointment(session_id: str, service: str, staff_id: Optional[int],
                        start_at: datetime, end_at: datetime,
                        patient_name: Optional[str], notes: Optional[str]) -> int:
    q = text("""
        INSERT INTO appointments
          (patient_session_id, patient_name, service_code, staff_id, start_at, end_at, status, notes)
        VALUES
          (:session_id, :patient_name, :service_code, :staff_id, :start_at, :end_at, 'booked', :notes)
    """)
    with engine.begin() as conn:
        res = conn.execute(q, {
            "session_id": session_id,
            "patient_name": patient_name,
            "service_code": service,
            "staff_id": staff_id,
            "start_at": start_at,
            "end_at": end_at,
            "notes": notes,
        })
        return int(res.lastrowid)


class GetAvailabilityTool:
    name = "get_availability"
    description = (
        "TURNOS ODONTOLÓGICOS (CLÍNICA DENTAL). Consultar horarios disponibles para reservar turno/cita/reserva. "
        "Usar cuando el usuario pida turno, cita, reserva, agenda, dentista/odontólogo o servicios: limpieza, consulta, urgencia, extracción. "
        "Inputs: service + date (YYYY-MM-DD); opcional staff."
    )
    input_model: Type[BaseModel] = GetAvailabilityInput
    scopes: List[str] = ["read"]

    async def run(self, args: BaseModel, ctx: Dict[str, Any]) -> Dict[str, Any]:
        a: GetAvailabilityInput = args  # type: ignore
        service = a.service.strip().lower()
        day = _parse_date(a.date.strip())
        staff_name = (a.staff or "").strip()

        duration_min = _service_duration_min(service)

        staff_id = None
        if staff_name:
            staff_id = _staff_id_by_name(staff_name)
            if staff_id is None:
                return {"ok": False, "error": f"Profesional no encontrado: {staff_name}"}

        busy = _busy_starts(staff_id, day)

        slots: List[Dict[str, Any]] = []
        for w_start, w_end in _business_windows(day):
            cursor = w_start
            while cursor + timedelta(minutes=duration_min) <= w_end:
                if (staff_id is None) or (cursor not in busy):
                    slots.append({
                        "start": cursor.isoformat(timespec="minutes"),
                        "end": (cursor + timedelta(minutes=duration_min)).isoformat(timespec="minutes"),
                        "service": service,
                        "duration_min": duration_min,
                        "staff": staff_name or None,
                    })
                cursor += timedelta(minutes=SLOT_MIN)

        return {"ok": True, "slots": slots, "count": len(slots)}


class CreateAppointmentTool:
    name = "create_appointment"
    description = (
        "RESERVAR TURNO ODONTOLÓGICO (CLÍNICA DENTAL). Crear un turno/cita en fecha y hora exactas. "
        "Usar SOLO cuando ya se conoce start (YYYY-MM-DDTHH:MM). Requiere confirmación (write)."
    )
    input_model: Type[BaseModel] = CreateAppointmentInput
    scopes: List[str] = ["write"]

    async def run(self, args: BaseModel, ctx: Dict[str, Any]) -> Dict[str, Any]:
        a: CreateAppointmentInput = args  # type: ignore
        session_id = str(ctx.get("session_id") or "unknown")

        service = a.service.strip().lower()
        start_at = datetime.fromisoformat(a.start.strip())
        duration_min = _service_duration_min(service)
        end_at = start_at + timedelta(minutes=duration_min)

        staff_id = None
        staff_name = (a.staff or "").strip()
        if staff_name:
            staff_id = _staff_id_by_name(staff_name)
            if staff_id is None:
                return {"ok": False, "error": f"Profesional no encontrado: {staff_name}"}

        appt_id = _insert_appointment(
            session_id=session_id,
            service=service,
            staff_id=staff_id,
            start_at=start_at,
            end_at=end_at,
            patient_name=a.patient_name,
            notes=a.notes,
        )
        return {"ok": True, "appointment_id": appt_id, "status": "booked"}


class ListAppointmentsTool:
    name = "list_appointments"
    description = (
        "TURNOS ODONTOLÓGICOS (CLÍNICA DENTAL). Listar próximos turnos del paciente actual. "
        "Usar cuando el usuario diga: mis turnos, ver turnos, qué turno tengo, próxima cita."
    )
    input_model: Type[BaseModel] = ListAppointmentsInput
    scopes: List[str] = ["read"]

    async def run(self, args: BaseModel, ctx: Dict[str, Any]) -> Dict[str, Any]:
        a: ListAppointmentsInput = args  # type: ignore
        session_id = str(ctx.get("session_id") or "unknown")

        status = (a.status or "booked").strip().lower()
        limit = int(a.limit)

        where_status = ""
        params: Dict[str, Any] = {"session_id": session_id, "limit": limit}

        if status != "all":
            where_status = "AND status = :status"
            params["status"] = status

        q = text(f"""
            SELECT id, service_code, start_at, end_at, status, staff_id
            FROM appointments
            WHERE patient_session_id = :session_id
              {where_status}
            ORDER BY start_at ASC
            LIMIT :limit
        """)

        with engine.begin() as conn:
            rows = conn.execute(q, params).fetchall()

        appts = []
        for r in rows:
            appts.append({
                "appointment_id": int(r[0]),
                "service": r[1],
                "start": r[2].isoformat(timespec="minutes"),
                "end": r[3].isoformat(timespec="minutes"),
                "status": r[4],
                "staff_id": r[5],
            })

        return {"ok": True, "appointments": appts, "count": len(appts)}
    
class CancelAppointmentTool:
    name = "cancel_appointment"
    description = (
        "TURNOS ODONTOLÓGICOS. Cancelar un turno existente. "
        "Usar cuando el usuario diga: cancelar turno, anular cita, no puedo ir. "
        "Inputs: appointment_id o cancel_next=true."
    )
    input_model: Type[BaseModel] = CancelAppointmentInput
    scopes: List[str] = ["write"]

    async def run(self, args: BaseModel, ctx: Dict[str, Any]) -> Dict[str, Any]:
        a: CancelAppointmentInput = args  # type: ignore
        session_id = str(ctx.get("session_id") or "unknown")

        appt_id = a.appointment_id

        # Si pide cancelar próximo
        if not appt_id and a.cancel_next:
            q = text("""
                SELECT id
                FROM appointments
                WHERE patient_session_id = :sid
                  AND status = 'booked'
                  AND start_at >= NOW()
                ORDER BY start_at ASC
                LIMIT 1
            """)
            with engine.begin() as conn:
                row = conn.execute(q, {"sid": session_id}).fetchone()
            if not row:
                return {"ok": False, "error": "No encontré un turno próximo para cancelar."}
            appt_id = int(row[0])

        if not appt_id:
            return {"ok": False, "error": "Falta appointment_id o cancel_next=true"}

        # Verificar que el turno sea del paciente y esté booked
        q_check = text("""
            SELECT id, service_code, start_at, end_at, status
            FROM appointments
            WHERE id = :id AND patient_session_id = :sid
            LIMIT 1
        """)
        with engine.begin() as conn:
            row = conn.execute(q_check, {"id": appt_id, "sid": session_id}).fetchone()

        if not row:
            return {"ok": False, "error": "Turno no encontrado para tu sesión."}
        if row[4] != "booked":
            return {"ok": False, "error": f"El turno no está activo (status={row[4]})."}

        q_upd = text("""
            UPDATE appointments
            SET status='cancelled', notes = CONCAT(IFNULL(notes,''), :note)
            WHERE id=:id AND patient_session_id=:sid
        """)
        note = ""
        if a.reason:
            note = f"\n[CANCEL] {a.reason}"
        else:
            note = "\n[CANCEL]"

        with engine.begin() as conn:
            conn.execute(q_upd, {"id": appt_id, "sid": session_id, "note": note})

        return {
            "ok": True,
            "appointment_id": appt_id,
            "status": "cancelled",
            "service": row[1],
            "start": row[2].isoformat(timespec="minutes"),
            "end": row[3].isoformat(timespec="minutes"),
        }


class RescheduleAppointmentTool:
    name = "reschedule_appointment"
    description = (
        "TURNOS ODONTOLÓGICOS. Reprogramar un turno existente a otra fecha/hora. "
        "Usar cuando el usuario diga: reprogramar, cambiar horario, mover turno. "
        "Inputs: appointment_id + new_start."
    )
    input_model: Type[BaseModel] = RescheduleAppointmentInput
    scopes: List[str] = ["write"]

    async def run(self, args: BaseModel, ctx: Dict[str, Any]) -> Dict[str, Any]:
        a: RescheduleAppointmentInput = args  # type: ignore
        session_id = str(ctx.get("session_id") or "unknown")

        new_start_at = datetime.fromisoformat(a.new_start.strip())

        # Buscar turno y validar pertenencia
        q = text("""
            SELECT id, service_code, staff_id, status
            FROM appointments
            WHERE id = :id AND patient_session_id = :sid
            LIMIT 1
        """)
        with engine.begin() as conn:
            row = conn.execute(q, {"id": a.appointment_id, "sid": session_id}).fetchone()

        if not row:
            return {"ok": False, "error": "Turno no encontrado para tu sesión."}
        if row[3] != "booked":
            return {"ok": False, "error": f"El turno no está activo (status={row[3]})."}

        service = row[1]
        current_staff_id = row[2]

        # staff opcional nuevo
        staff_id = current_staff_id
        staff_name = (a.staff or "").strip()
        if staff_name:
            sid = _staff_id_by_name(staff_name)
            if sid is None:
                return {"ok": False, "error": f"Profesional no encontrado: {staff_name}"}
            staff_id = sid

        duration_min = _service_duration_min(service)
        new_end_at = new_start_at + timedelta(minutes=duration_min)

        # Chequeo simple de choque si hay staff_id
        if staff_id is not None:
            q_conflict = text("""
                SELECT id
                FROM appointments
                WHERE staff_id = :staff_id
                  AND status='booked'
                  AND start_at = :start_at
                  AND id <> :id
                LIMIT 1
            """)
            with engine.begin() as conn:
                conflict = conn.execute(q_conflict, {
                    "staff_id": staff_id,
                    "start_at": new_start_at,
                    "id": a.appointment_id,
                }).fetchone()
            if conflict:
                return {"ok": False, "error": "Ese horario ya está ocupado para ese profesional."}

        q_upd = text("""
            UPDATE appointments
            SET staff_id=:staff_id, start_at=:start_at, end_at=:end_at
            WHERE id=:id AND patient_session_id=:sid
        """)
        with engine.begin() as conn:
            conn.execute(q_upd, {
                "staff_id": staff_id,
                "start_at": new_start_at,
                "end_at": new_end_at,
                "id": a.appointment_id,
                "sid": session_id,
            })

        return {
            "ok": True,
            "appointment_id": int(row[0]),
            "status": "booked",
            "service": service,
            "new_start": new_start_at.isoformat(timespec="minutes"),
            "new_end": new_end_at.isoformat(timespec="minutes"),
            "staff_id": staff_id,
        }

def register():
    return [
            GetAvailabilityTool(),
            CreateAppointmentTool(),
            ListAppointmentsTool(),
            CancelAppointmentTool(),
            RescheduleAppointmentTool(),
    ]