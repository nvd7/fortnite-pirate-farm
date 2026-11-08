Option Explicit

Dim fso, shell, root, pythonw, installer, command

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = root & "\.venv\Scripts\pythonw.exe"
installer = root & "\Instalar.bat"

If Not fso.FileExists(pythonw) Then
    shell.Run """" & installer & """", 1, True
End If

If fso.FileExists(pythonw) Then
    shell.CurrentDirectory = root
    command = """" & pythonw & """ """ & root & "\main.py"""
    shell.Run command, 0, False
Else
    MsgBox "Nao consegui iniciar o Pirate Farm." & vbCrLf & _
           "Execute o Instalar.bat na pasta do programa.", 16, "Pirate Farm"
End If
