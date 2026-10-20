@echo off
rem ==========================================================================
rem  Supervised Ollama launcher (ASCII only, CRLF, no chcp).
rem  Started by ..\..\启动本地模型.bat via:  start "..." /min "<this file>"
rem  Duties:  redirect ollama output to runtime\ollama-data\server.log
rem           restart ollama if it dies unexpectedly
rem           honour the STOP flag written by ..\..\停止本地模型.bat
rem  No multi-line if( ) / for( ) block may expand a %~dp0-derived path here
rem  either: the project folder name contains "(1)".
rem ==========================================================================
setlocal
set "SYS=%SystemRoot%\System32"
set "HERE=%~dp0"
set "DATA=%HERE%..\ollama-data"
if not exist "%DATA%" mkdir "%DATA%"
set "LOG=%DATA%\server.log"
set "FLAG=%DATA%\STOP"

rem 每次托管进程启动时重置日志，避免崩溃循环把文件撑大
> "%LOG%" echo [%DATE% %TIME%] supervisor start

:loop
if exist "%FLAG%" goto bye
echo [%DATE% %TIME%] starting: ollama serve >> "%LOG%"
"%HERE%ollama.exe" serve >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
if exist "%FLAG%" goto bye
echo [%DATE% %TIME%] ollama exited rc=%RC%, restarting in 5s >> "%LOG%"
ping -n 6 127.0.0.1 >nul
if exist "%FLAG%" goto bye
goto loop

:bye
echo [%DATE% %TIME%] stop flag found, supervisor exit >> "%LOG%"
exit /b 0
