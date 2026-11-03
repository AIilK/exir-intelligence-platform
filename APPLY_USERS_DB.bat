@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0backend"
rem Close the "Sales API 8000" and "Finance API 8010" windows first, then run this file.
netstat -ano | findstr /R /C:":8010 .*LISTENING" >nul && (
  echo Finance backend 8010 is still running. Close its window and run this again.
  pause
  exit /b 1
)
if not exist db_import\exir.db (
  echo db_import\exir.db not found.
  pause
  exit /b 1
)
if not exist db_backup mkdir db_backup
copy /y exir.db db_backup\exir.db.before_import >nul
copy /y customer_intelligence_history.db db_backup\customer_intelligence_history.db.before_import >nul
copy /y db_import\exir.db exir.db >nul || goto :err
copy /y db_import\customer_intelligence_history.db customer_intelligence_history.db >nul || goto :err
echo Users database installed (old copies in backend\db_backup).
echo Now run unified\RUN_UNIFIED.bat
pause
goto :eof

:err
echo Copy failed.
pause
