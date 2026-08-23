Attribute VB_Name = "DuctGen"
'==========================================================================
' ductgen launcher
'
' Opens the ductgen window from inside SolidWorks. Put this macro on a
' toolbar button and the generator behaves like part of SolidWorks: press
' the button, set prop / motor / bed, press Build, and the parts appear in
' this session.
'
' It does not need editing. The macro finds the repository by asking
' SolidWorks where the macro file itself lives, then goes one folder up.
' Keep DuctGen.swp inside the repo's macro\ folder.
'
' See macro\README.md for the three-click install.
'==========================================================================
Option Explicit

Dim swApp As SldWorks.SldWorks

Private Function RepoRoot() As String
    Dim macroDir As String
    macroDir = swApp.GetCurrentMacroPathFolder            ' ...\ductgen\macro
    If Right$(macroDir, 1) = "\" Then
        macroDir = Left$(macroDir, Len(macroDir) - 1)
    End If
    RepoRoot = Left$(macroDir, InStrRev(macroDir, "\") - 1)
End Function

Private Function FindPython() As String
    ' pythonw runs the GUI without leaving a console window behind.
    Dim fso As Object, shell As Object, candidates As Variant, i As Integer
    Set fso = CreateObject("Scripting.FileSystemObject")
    Set shell = CreateObject("WScript.Shell")

    ' a virtualenv inside the repo wins if there is one
    candidates = Array( _
        RepoRoot() & "\.venv\Scripts\pythonw.exe", _
        RepoRoot() & "\venv\Scripts\pythonw.exe")
    For i = LBound(candidates) To UBound(candidates)
        If fso.FileExists(candidates(i)) Then
            FindPython = candidates(i)
            Exit Function
        End If
    Next i

    ' otherwise whatever is on PATH
    On Error Resume Next
    FindPython = shell.RegRead("HKCU\Software\Python\PythonCore\3.13\InstallPath\") & "pythonw.exe"
    On Error GoTo 0
    If Len(FindPython) > Len("pythonw.exe") Then
        If fso.FileExists(FindPython) Then Exit Function
    End If

    FindPython = "pythonw.exe"      ' let the shell resolve it
End Function

Sub main()
    Dim root As String, py As String, target As String, cmd As String
    Dim fso As Object

    Set swApp = Application.SldWorks
    Set fso = CreateObject("Scripting.FileSystemObject")

    root = RepoRoot()
    target = root & "\ductgen-gui.pyw"

    If Not fso.FileExists(target) Then
        MsgBox "Could not find ductgen-gui.pyw." & vbCrLf & vbCrLf & _
               "Looked in: " & root & vbCrLf & vbCrLf & _
               "This macro expects to live in the repository's macro\ " & _
               "folder. Move DuctGen.swp there and run it again.", _
               vbExclamation, "ductgen"
        Exit Sub
    End If

    py = FindPython()
    cmd = """" & py & """ """ & target & """"

    On Error Resume Next
    Shell cmd, vbNormalFocus
    If Err.Number <> 0 Then
        MsgBox "Could not start Python." & vbCrLf & vbCrLf & _
               "Tried: " & cmd & vbCrLf & vbCrLf & _
               "Run install.bat in " & root & " first, or install Python " & _
               "3.10+ from python.org with 'Add python.exe to PATH' ticked.", _
               vbCritical, "ductgen"
    End If
    On Error GoTo 0
End Sub
