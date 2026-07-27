Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = scriptDir & "\"
q = """"
cmd = "python -X utf8 " & q & scriptDir & "\edm_dashboard.py" & q & " --port 8765 --json-file " & q & scriptDir & "\edmmailanalyzer.json" & q
WshShell.Run cmd, 0