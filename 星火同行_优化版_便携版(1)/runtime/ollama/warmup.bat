@echo off
rem ==========================================================================
rem  Warm-up helper (ASCII only, CRLF, no chcp).
rem  Loads the model and pre-fills the system-prompt KV cache via the SAME
rem  OpenAI-compatible endpoint the app uses, so the first user message
rem  answers in ~1s instead of ~45s (cold CPU load).
rem  Started hidden by ..\..\启动本地模型.bat via Start-Process.
rem ==========================================================================
setlocal
set "SYS=%SystemRoot%\System32"
set "CURL=%SYS%\curl.exe"
if not exist "%CURL%" set "CURL=curl"
set "ROOT=%~dp0..\.."
if not exist "%ROOT%\runtime\warmup.json" exit /b 0
"%CURL%" -s -m 600 -X POST -H "Content-Type: application/json" --data-binary @"%ROOT%\runtime\warmup.json" http://127.0.0.1:11434/v1/chat/completions >nul 2>&1
exit /b 0
