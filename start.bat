@echo off
set ROOT=%~dp0
set PYTHONPATH=%ROOT%src;%PYTHONPATH%
cd /d "%ROOT%"
python -m odwolania2json process-input --input "%ROOT%input" --output "%ROOT%output"
