@echo off
chcp 65001 >nul
title 봉안당 시연 시작
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
