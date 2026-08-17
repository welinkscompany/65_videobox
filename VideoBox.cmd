@echo off
rem 아이콘 하나로 VideoBox를 켠다. 바탕화면 바로가기는 이 파일을 가리킨다.
rem 실제 순서는 scripts\Start-VideoBox.ps1에 있다.
title VideoBox
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-VideoBox.ps1" %*
if errorlevel 1 (
  echo.
  echo 창을 닫으려면 아무 키나 누르세요.
  pause >nul
)
