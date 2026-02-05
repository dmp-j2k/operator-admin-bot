#!/bin/sh
alembic upgrade head
python start_bots.py
