#!/usr/bin/env bash
# 리눅스 현장 소형 컴퓨터용. 서버와 현장 프로그램을 함께 띄운다.
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8
python -m uvicorn server.main:app --host 0.0.0.0 --port 8765 &
sleep 3
python -m edge.agent
