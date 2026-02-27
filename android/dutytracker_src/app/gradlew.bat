@echo off
setlocal EnableExtensions EnableDelayedExpansion

set DIR=%~dp0
set WRAPPER_PROPS=%DIR%gradle\wrapper\gradle-wrapper.properties

if not exist "%WRAPPER_PROPS%" (
  echo [gradlew] Missing %WRAPPER_PROPS%
  exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /c:"distributionUrl=" "%WRAPPER_PROPS%"`) do (
  set DIST_URL=%%B
)

if "%DIST_URL%"=="" (
  echo [gradlew] Could not read distributionUrl from %WRAPPER_PROPS%
  exit /b 1
)

rem Unescape https\://
set DIST_URL=%DIST_URL:\=%
for %%F in ("%DIST_URL%") do set DIST_FILE=%%~nxF

rem e.g. gradle-8.7-bin.zip -> gradle-8.7
set DIST_NAME=%DIST_FILE:-bin.zip=%
set DIST_NAME=%DIST_NAME:-all.zip=%

set GRADLE_USER_HOME=%USERPROFILE%\.gradle
if not "%GRADLE_USER_HOME_ENV%"=="" set GRADLE_USER_HOME=%GRADLE_USER_HOME_ENV%

set DISTS_DIR=%GRADLE_USER_HOME%\wrapper\dists
set TARGET_DIR=%DISTS_DIR%\%DIST_NAME%
set GRADLE_HOME=%TARGET_DIR%\%DIST_NAME%

if exist "%GRADLE_HOME%\bin\gradle.bat" goto JAVA_CHECK

echo [gradlew] Downloading %DIST_URL%
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%" >nul 2>&1

set ZIP_PATH=%TARGET_DIR%\%DIST_FILE%

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue';" ^
  "Invoke-WebRequest -Uri '%DIST_URL%' -OutFile '%ZIP_PATH%';" ^
  "Expand-Archive -Path '%ZIP_PATH%' -DestinationPath '%TARGET_DIR%' -Force;" ^
  "Remove-Item -Force '%ZIP_PATH%';"
if errorlevel 1 (
  echo [gradlew] Failed to download or extract Gradle distribution.
  echo [gradlew] Check internet / proxy access to services.gradle.org
  exit /b 1
)

:JAVA_CHECK
if exist "%JAVA_HOME%\bin\java.exe" goto RUN

where java >nul 2>&1
if %ERRORLEVEL%==0 goto RUN

rem Try to auto-detect Android Studio JBR (common locations, incl. drive D:)
for %%P in (
  "D:\Program Files\Android\Android Studio\jbr"
  "D:\Android Studio\jbr"
  "D:\Android\Android Studio\jbr"
  "C:\Program Files\Android\Android Studio\jbr"
  "C:\Program Files\JetBrains\Android Studio\jbr"
) do (
  if exist "%%~P\bin\java.exe" (
    set JAVA_HOME=%%~P
    goto RUN
  )
)

echo ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.
echo Set JAVA_HOME to JDK 17. If Android Studio is installed, you can use its JBR folder (jbr).
echo Example (PowerShell):
echo   setx JAVA_HOME "D:\Program Files\Android\Android Studio\jbr"
exit /b 1

:RUN
call "%GRADLE_HOME%\bin\gradle.bat" %*
endlocal
