#!/usr/bin/env python3
"""Create gateway credentials interactively, without printing or overwriting secrets."""
import getpass
import hashlib
import os
import secrets
from pathlib import Path

target=Path('/etc/air-health-web.env')
if os.geteuid()!=0:raise SystemExit('Run with sudo python3 configure-web.py')
if target.exists():raise SystemExit('Existing gateway configuration: refusing overwrite')
password=getpass.getpass('Choose a UNIQUE random password (at least 24 characters): ')
if len(password)<24:raise SystemExit('Use at least 24 characters from a password manager')
if password!=getpass.getpass('Confirm password: '):raise SystemExit('Passwords do not match')
payload='\n'.join([
    'AIR_HEALTH_WEB_USER=healthdemo',
    'AIR_HEALTH_WEB_PASSWORD_SHA256='+hashlib.sha256(password.encode()).hexdigest(),
    'AIR_HEALTH_WEB_SESSION_SECRET='+secrets.token_hex(32),
    'AIR_HEALTH_WEB_SESSION_TTL=43200',
    'AIR_HEALTH_GATEWAY_HOST=127.0.0.1',
    'AIR_HEALTH_GATEWAY_PORT=8766',
    'AIR_HEALTH_UPSTREAM_HOST=127.0.0.1',
    'AIR_HEALTH_UPSTREAM_PORT=8765',''])
fd=os.open(str(target),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w',encoding='utf-8') as handle:handle.write(payload)
print('Gateway config created, owner root, mode 0600. No secrets printed.')
