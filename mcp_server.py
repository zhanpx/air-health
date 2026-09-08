#!/usr/bin/env python3
"""Read-only MCP server for the local Air Health database."""

import datetime as dt
import json
import os
import sqlite3
import sys
import traceback


APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("HEALTH_DATA_DIR", "/var/lib/air-health")
DB_PATH = os.path.join(DATA_DIR, "health.db")
sys.path.insert(0, APP_DIR)
import app as health_app


INSTRUCTIONS = (
    "Read-only access to the user's private Google Health/Fitbit data stored on health-server. "
    "Use aggregated metrics by default, state the actual data dates and freshness, and never "
    "present recovery scores, correlations, or anomalies as medical diagnoses. Do not infer "
    "causation from correlation. Exact GPS and OAuth credentials are intentionally unavailable."
)


TOOLS = [
    {
        "name": "get_health_summary",
        "description": "Get current status, recent health metrics, recovery, training load, correlations, and data freshness.",
        "inputSchema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 7, "maximum": 365, "default": 30}},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
    },
    {
        "name": "get_metric_series",
        "description": "Query one or more daily metric time series, such as steps, sleep_minutes, hrv, resting_heart_rate, spo2_avg, respiratory_rate, active_calories, distance_km, or vo2_max.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "metrics": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 20},
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive"},
                "days": {"type": "integer", "minimum": 1, "maximum": 1095, "default": 30},
            },
            "required": ["metrics"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
    },
    {
        "name": "get_sleep_history",
        "description": "Get sleep duration, stages, HRV, resting heart rate, respiratory rate, and oxygen saturation by night.",
        "inputSchema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 7, "maximum": 365, "default": 30}},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
    },
    {
        "name": "get_workouts",
        "description": "Get workout sessions and summaries without exact GPS coordinates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
    },
    {
        "name": "analyze_health",
        "description": "Run transparent personal-baseline recovery, training-load, correlation, and data-quality analyses.",
        "inputSchema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 30, "maximum": 365, "default": 90}},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
    },
    {
        "name": "list_health_metrics",
        "description": "List available normalized metrics with coverage dates and sample counts.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
    },
]


def connect():
    return sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True)


def parse_date(value, name):
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError("%s must use YYYY-MM-DD" % name)


def range_dates(arguments, default_days=30, maximum=1095):
    if arguments.get("end_date"):
        end = parse_date(arguments["end_date"], "end_date")
    else:
        end = dt.date.today()
    if arguments.get("start_date"):
        start = parse_date(arguments["start_date"], "start_date")
    else:
        days = max(1, min(int(arguments.get("days", default_days)), maximum))
        start = end - dt.timedelta(days=days - 1)
    if start > end:
        raise ValueError("start_date must not be after end_date")
    if (end - start).days + 1 > maximum:
        raise ValueError("date range exceeds %d days" % maximum)
    return start, end


def series_between(start, end, metrics=None):
    query = "SELECT day,metric,value FROM metrics WHERE day>=? AND day<=?"
    params = [start.isoformat(), end.isoformat()]
    if metrics:
        placeholders = ",".join("?" for _ in metrics)
        query += " AND metric IN (%s)" % placeholders
        params.extend(metrics)
    query += " ORDER BY day,metric"
    rows = {}
    conn = connect()
    try:
        for day, metric, value in conn.execute(query, params):
            rows.setdefault(day, {"day": day})[metric] = value
    finally:
        conn.close()
    cursor = start
    result = []
    while cursor <= end:
        result.append(rows.get(cursor.isoformat(), {"day": cursor.isoformat()}))
        cursor += dt.timedelta(days=1)
    return result


def state_value(key, default=None):
    conn = connect()
    try:
        row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    finally:
        conn.close()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except ValueError:
        return default


def analytics(days):
    end = dt.date.today()
    start = end - dt.timedelta(days=max(30, min(int(days), 365)) - 1)
    series = series_between(start, end)
    devices = state_value("devices", []) or []
    last_sync = state_value("last_sync")
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "recovery": health_app.recovery_analysis(series),
        "training": health_app.training_analysis(series),
        "correlations": health_app.correlation_analysis(series),
        "data_quality": health_app.data_quality_analysis(series, devices, last_sync),
    }


def call_tool(name, arguments):
    arguments = arguments or {}
    if name == "get_metric_series":
        metrics = [str(value) for value in arguments.get("metrics", [])]
        if not metrics:
            raise ValueError("metrics is required")
        start, end = range_dates(arguments)
        return {"start": start.isoformat(), "end": end.isoformat(), "metrics": metrics, "series": series_between(start, end, metrics)}
    if name == "get_sleep_history":
        days = max(7, min(int(arguments.get("days", 30)), 365))
        end = dt.date.today()
        start = end - dt.timedelta(days=days - 1)
        metrics = ["sleep_minutes", "sleep_period_minutes", "sleep_deep", "sleep_rem", "sleep_light", "sleep_awake", "hrv", "resting_heart_rate", "respiratory_rate", "sleep_respiratory_rate", "spo2_avg", "skin_temperature_delta"]
        return {"start": start.isoformat(), "end": end.isoformat(), "nights": [row for row in series_between(start, end, metrics) if any(key != "day" for key in row)]}
    if name == "get_workouts":
        start, end = range_dates(arguments, default_days=30, maximum=3650)
        limit = max(1, min(int(arguments.get("limit", 20)), 100))
        conn = connect()
        try:
            rows = conn.execute("SELECT day,payload FROM records WHERE data_type='exercise' AND day>=? AND day<=? ORDER BY day DESC LIMIT ?", (start.isoformat(), end.isoformat(), limit)).fetchall()
        finally:
            conn.close()
        workouts = []
        for day, payload in rows:
            exercise = json.loads(payload).get("exercise", {})
            workouts.append({
                "day": day,
                "type": exercise.get("exerciseType"),
                "name": exercise.get("displayName") or exercise.get("exerciseType"),
                "active_duration": exercise.get("activeDuration"),
                "started_at": (exercise.get("interval") or {}).get("startTime"),
                "summary": exercise.get("metricsSummary", {}),
                "has_gps": bool((exercise.get("exerciseMetadata") or {}).get("hasGps")),
            })
        return {"start": start.isoformat(), "end": end.isoformat(), "count": len(workouts), "workouts": workouts, "gps_coordinates_included": False}
    if name == "analyze_health":
        return analytics(arguments.get("days", 90))
    if name == "list_health_metrics":
        conn = connect()
        try:
            rows = conn.execute("SELECT metric,COUNT(*),MIN(day),MAX(day) FROM metrics WHERE value IS NOT NULL GROUP BY metric ORDER BY metric").fetchall()
        finally:
            conn.close()
        return {"metrics": [{"metric": row[0], "samples": row[1], "first_day": row[2], "last_day": row[3]} for row in rows]}
    if name == "get_health_summary":
        days = max(7, min(int(arguments.get("days", 30)), 365))
        end = dt.date.today()
        start = end - dt.timedelta(days=days - 1)
        metrics = ["steps", "sleep_minutes", "resting_heart_rate", "hrv", "heart_rate_avg", "spo2_avg", "respiratory_rate", "skin_temperature_delta", "active_calories", "distance_km", "heart_zone_minutes", "exercise_minutes", "exercise_count", "vo2_max", "weight_kg"]
        series = series_between(start, end, metrics)
        latest = {}
        for metric in metrics:
            for row in reversed(series):
                if row.get(metric) is not None:
                    latest[metric] = {"value": row[metric], "day": row["day"]}
                    break
        return {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "last_sync": state_value("last_sync"),
            "today_snapshot": state_value("today_snapshot", {}),
            "latest_metrics": latest,
            "analytics": analytics(max(days, 90)),
        }
    raise ValueError("Unknown tool: %s" % name)


def response(message_id, result=None, error=None):
    value = {"jsonrpc": "2.0", "id": message_id}
    if error is not None:
        value["error"] = error
    else:
        value["result"] = result
    sys.stdout.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main():
    for raw in sys.stdin:
        try:
            message = json.loads(raw)
            method = message.get("method")
            message_id = message.get("id")
            if method == "initialize":
                requested = (message.get("params") or {}).get("protocolVersion", "2025-06-18")
                response(message_id, {"protocolVersion": requested, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "google-health", "version": "1.0.0"}, "instructions": INSTRUCTIONS})
            elif method == "ping":
                response(message_id, {})
            elif method == "tools/list":
                response(message_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = message.get("params") or {}
                try:
                    value = call_tool(params.get("name"), params.get("arguments") or {})
                    response(message_id, {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=2)}], "structuredContent": value, "isError": False})
                except Exception as exc:
                    response(message_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
            elif message_id is not None:
                response(message_id, error={"code": -32601, "message": "Method not found"})
        except Exception as exc:
            sys.stderr.write("MCP error: %s\n" % exc)
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()


if __name__ == "__main__":
    main()
