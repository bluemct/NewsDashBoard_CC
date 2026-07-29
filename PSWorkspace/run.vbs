' PS Workspace - VBS Silent Launch Script
' Usage: Double-click run.vbs to start in background

Dim objShell
Set objShell = CreateObject("WScript.Shell")

Dim scriptDir
scriptDir = Left(WScript.ScriptFullName, Len(WScript.ScriptFullName) - Len(WScript.ScriptName))

objShell.Run "powershell -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & scriptDir & "run.ps1""", 0, False

Set objShell = Nothing
