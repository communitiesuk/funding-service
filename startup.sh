#!/bin/bash
python -m flask db upgrade
python -m flask run --host 0.0.0.0
