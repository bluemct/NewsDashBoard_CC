' edm_agent_send_email.vbs
' Run EDM email sender on any Windows machine (requires Python 3 installed)
'
' Usage:
'   Double-click this file
'   Or: cscript edm_agent_send_email.vbs
'
' Arguments (passed through to Python):
'   --html "path/to/EDM_template.html"
'   --subject "Custom subject"
'   --body "Inline text or HTML body"

Dim objShell, scriptPath, pythonPath

' --- Create shell object FIRST ---
Set objShell = CreateObject("WScript.Shell")
scriptPath = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

' --- Find Python executable ---
pythonPath = ""

' 1) Check if python is in PATH
On Error Resume Next
Dim testResult : Set testResult = objShell.Exec("%ComSpec% /c where python 2>nul")
WScript.Sleep 500
Dim pyInPath : pyInPath = testResult.StdOut.Readall()
On Error GoTo 0

If Trim(pyInPath) <> "" Then
    pythonPath = "python"
Else
    ' 2) Try known install paths (iterate from newest to oldest)
    Dim pythonCandidates
    pythonCandidates = Array( _
        "%LOCALAPPDATA%\Programs\Python\Python313\python.exe", _
        "%ProgramFiles%\Python313\python.exe", _
        "%ProgramFiles(x86)%\Python313\python.exe", _
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe", _
        "%ProgramFiles%\Python312\python.exe", _
        "%ProgramFiles(x86)%\Python312\python.exe" _
    )

    Dim candidate
    For Each candidate In pythonCandidates
        candidate = objShell.ExpandEnvironmentStrings(candidate)
        If Len(Dir(candidate)) > 0 Then
            pythonPath = candidate
            Exit For
        End If
    Next
End If

If pythonPath = "" Then
    MsgBox "Python 找不到!" & vbCrLf & vbCrLf & _
           "Please install Python 3.12+ or ensure python is in PATH.", _
           vbCritical, "EDM Email Sender"
    WScript.Quit 1
End If

' --- Build command ---
Dim pyFile
pyFile = scriptPath & "edm_agent_send_email.py"

Dim cmd
cmd = """" & pythonPath & """ """ & pyFile & """"

' Append user arguments
Dim i
For i = 0 To WScript.Arguments.Count - 1
    cmd = cmd & " """ & WScript.Arguments(i) & """"
Next

' --- Run and wait ---
Dim execResult
Set execResult = objShell.Exec(cmd)

Do While execResult.Status = 0
    WScript.Sleep 100
Loop

Dim output : output = execResult.StdOut.Readall()
Dim errOutput : errOutput = execResult.StdErr.Readall()

Dim fullOutput : fullOutput = output
If errOutput <> "" Then fullOutput = fullOutput & vbCrLf & errOutput

MsgBox fullOutput, vbInformation, "EDM Email Sender - Result"
