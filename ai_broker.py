#!/usr/bin/env python3
"""Privilege-separated Codex broker for aggregate health summaries."""

import base64
import json
import logging
import os
import socket
import struct
import subprocess
import tempfile


SOCKET_PATH = os.environ.get("AIR_HEALTH_AI_SOCKET", "/run/air-health-ai/agent.sock")
IMAGE_TMP_DIR = os.environ.get("AIR_HEALTH_AI_IMAGE_TMP", "/var/lib/air-health-ai")
MAX_REQUEST = 6 * 1024 * 1024
MAX_RESPONSE = 262144
ALLOWED_MODELS = {"gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"}


def recv_exact(connection, size):
    data = b""
    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            raise RuntimeError("incomplete request")
        data += chunk
    return data


def respond(connection, value):
    body = json.dumps(value, ensure_ascii=False).encode("utf-8")[:MAX_RESPONSE]
    connection.sendall(struct.pack("!I", len(body)) + body)


def analyze(request):
    prompt = str(request.get("prompt") or "")
    if not prompt or len(prompt) > 120000:
        raise ValueError("invalid prompt")
    model = str(request.get("model") or "").strip().lower()
    if model and model not in ALLOWED_MODELS:
        raise ValueError("invalid model")
    timeout = max(30, min(int(request.get("timeout") or 180), 240))
    output_fd, output_path = tempfile.mkstemp(prefix="air-health-ai-", suffix=".txt", dir="/tmp")
    os.close(output_fd)
    image_paths = []
    try:
        images = request.get("images") or []
        if not isinstance(images, list) or len(images) > 1:
            raise ValueError("invalid images")
        suffixes = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
        for item in images:
            if not isinstance(item, dict) or item.get("mime_type") not in suffixes:
                raise ValueError("invalid image type")
            raw = base64.b64decode(str(item.get("data") or ""), validate=True)
            if not raw or len(raw) > 3 * 1024 * 1024:
                raise ValueError("invalid image size")
            mime_type = item["mime_type"]
            valid = (
                (mime_type == "image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n")) or
                (mime_type == "image/jpeg" and raw.startswith(b"\xff\xd8\xff")) or
                (mime_type == "image/webp" and len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP")
            )
            if not valid:
                raise ValueError("invalid image contents")
            image_fd, image_path = tempfile.mkstemp(prefix="air-health-ai-image-", suffix=suffixes[mime_type], dir=IMAGE_TMP_DIR)
            with os.fdopen(image_fd, "wb") as handle:
                handle.write(raw)
            os.chmod(image_path, 0o600)
            image_paths.append(image_path)
        command = [
            "/usr/local/libexec/air-health-codex", "exec", "--ephemeral", "--ignore-user-config", "--sandbox", "read-only",
            "--skip-git-repo-check", "-C", "/var/empty/air-health-ai", "-o", output_path,
        ]
        if model:
            command.extend(["--model", model])
        for image_path in image_paths:
            command.extend(["--image", image_path])
        command.extend(["--", prompt])
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=timeout, env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/var/lib/air-health-ai"},
            universal_newlines=True,
        )
        if result.returncode != 0:
            raise RuntimeError("Codex returned %s" % result.returncode)
        with open(output_path, "r", encoding="utf-8") as handle:
            answer = handle.read().strip()
        if not answer:
            raise RuntimeError("empty Codex response")
        return {"ok": True, "answer": answer}
    finally:
        try:
            os.remove(output_path)
        except OSError:
            pass
        for image_path in image_paths:
            try:
                os.remove(image_path)
            except OSError:
                pass


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        os.remove(SOCKET_PATH)
    except OSError:
        pass
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o660)
    server.listen(4)
    while True:
        connection, _ = server.accept()
        try:
            header = recv_exact(connection, 4)
            size = struct.unpack("!I", header)[0]
            if size > MAX_REQUEST:
                raise ValueError("request too large")
            request = json.loads(recv_exact(connection, size).decode("utf-8"))
            respond(connection, analyze(request))
        except subprocess.TimeoutExpired:
            respond(connection, {"ok": False, "error": "AI 分析超时，请稍后重试"})
        except Exception:
            logging.exception("AI broker request failed")
            respond(connection, {"ok": False, "error": "AI 分析暂不可用"})
        finally:
            connection.close()


if __name__ == "__main__":
    main()
