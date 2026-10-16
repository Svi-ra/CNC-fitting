Attribute VB_Name = "CutListImport"
'
' CutListImport -- Excel VBA: the JSON from gh_cutlist2json.py -> a cut list
' sheet laid out like the shop's reference workbook.
'
' Installing
' ----------
' In Excel press Alt+F11, then File > Import File... and pick this .bas. To
' have the macros in every workbook, import it into PERSONAL.XLSB (record any
' macro once with "Store macro in: Personal Macro Workbook" to create it);
' otherwise save the workbook that holds it as .xlsm.
'
' Windows Excel only: the file is read with ADODB.Stream and the JSON is kept
' in Scripting.Dictionary objects, neither of which exists on a Mac.
'
' The macros
' ----------
'   ImportCutList       asks for a .json and lays it out in a new workbook
'   ImportCutListHere   the same, on a new sheet at the end of the active
'                       workbook
'
' Both come down to ImportCutListFile, which takes a path and can be called
' from other code.
'
' What it does with the JSON
' --------------------------
' Only the "sheet" half is read; "sections" is the same data for Power
' Query. In order:
'
'   1  every row of "values" is written from column A, all text kept as text
'      -- a name such as 1/2 or 12-3 is not turned into a date or a number
'   2  the column widths and the taller rows
'   3  every entry of "formats": its style's font, fill, alignment, borders
'      and number format, over its range
'   4  every entry of "outlines": a box round its range, drawn over the
'      borders of step 3
'   5  the merges
'   6  the page: orientation, paper, fit to pages, margins
'
' A file whose "format" is not "cnc-fitting cut list", or whose version is
' newer than this module knows, is turned away rather than half laid out,
' and so is one that breaks off halfway: the sheet it was building is taken
' away again.
'
Option Explicit

Private Const DOC_FORMAT As String = "cnc-fitting cut list"
Private Const DOC_VERSION As Long = 1

' the JSON reader's state: the whole text, and where it has got to
Private mText As String
Private mPos As Long
Private mLen As Long


' ---------------------------------------------------------------------------
' the macros
' ---------------------------------------------------------------------------

Public Sub ImportCutList()
    Dim path As Variant
    path = Application.GetOpenFilename("Cut list JSON (*.json),*.json", , _
                                       "Import cut list")
    If VarType(path) = vbBoolean Then Exit Sub      ' cancelled
    RunImport CStr(path), Nothing
End Sub


Public Sub ImportCutListHere()
    Dim path As Variant
    path = Application.GetOpenFilename("Cut list JSON (*.json),*.json", , _
                                       "Import cut list")
    If VarType(path) = vbBoolean Then Exit Sub
    RunImport CStr(path), ActiveWorkbook
End Sub


Private Sub RunImport(ByVal path As String, ByVal wb As Workbook)
    On Error GoTo Failed
    ImportCutListFile path, wb
    Exit Sub
Failed:
    Application.ScreenUpdating = True
    MsgBox "The cut list could not be imported:" & vbLf & vbLf & _
           Err.Description, vbExclamation, "Import cut list"
End Sub


' Lay the file at path out on a new sheet: at the end of wb, or in a new
' workbook when wb is Nothing. Returns the sheet; raises an error, with
' nothing left behind, when the file cannot be read.
Public Function ImportCutListFile(ByVal path As String, _
                                  Optional ByVal wb As Workbook = Nothing) _
                                  As Worksheet
    Dim doc As Object, sheet As Object, ws As Worksheet, m As Variant
    Set doc = ParseJson(ReadUtf8(path))
    CheckFormat doc
    Set sheet = Member(doc, "sheet")

    Application.ScreenUpdating = False
    If wb Is Nothing Then
        Set ws = Workbooks.Add(xlWBATWorksheet).Worksheets(1)
    Else
        Set ws = wb.Worksheets.Add(After:=wb.Sheets(wb.Sheets.Count))
    End If

    On Error GoTo Failed
    NameSheet ws, CStr(Member(sheet, "name"))
    WriteValues ws, Member(sheet, "values")
    SizeGrid ws, sheet
    ApplyFormats ws, sheet
    DrawOutlines ws, Member(sheet, "outlines")
    For Each m In Member(sheet, "merges")
        ws.Range(m).Merge
    Next m
    SetUpPage ws, Member(sheet, "page")
    ws.Activate
    ws.Range("A1").Select
    Application.ScreenUpdating = True
    Set ImportCutListFile = ws
    Exit Function

Failed:
    ' Keep the error, take the half-made sheet away, then pass the error on.
    Dim num As Long, desc As String
    num = Err.Number
    desc = Err.Description
    On Error GoTo -1            ' leave the handler, or Resume Next is ignored
    On Error Resume Next
    Application.DisplayAlerts = False
    If wb Is Nothing Then
        ws.Parent.Close SaveChanges:=False
    Else
        ws.Delete
    End If
    Application.DisplayAlerts = True
    Application.ScreenUpdating = True
    On Error GoTo 0
    Err.Raise num, "CutListImport", desc
End Function


' ---------------------------------------------------------------------------
' laying the sheet out
' ---------------------------------------------------------------------------

Private Sub CheckFormat(ByVal doc As Object)
    If Not doc.Exists("format") Or Not doc.Exists("sheet") Then
        Fail "this is not a cut list from gh_cutlist2json"
    End If
    If CStr(doc("format")) <> DOC_FORMAT Then
        Fail "this is not a cut list from gh_cutlist2json (format '" & _
             doc("format") & "')"
    End If
    If doc.Exists("version") Then
        If doc("version") > DOC_VERSION Then
            Fail "the file is version " & doc("version") & _
                 "; this module reads up to version " & DOC_VERSION
        End If
    End If
End Sub


' The sheet's name, or the name with (2), (3) ... when the workbook already
' has a sheet called that. A name Excel will not take leaves Excel's own.
Private Sub NameSheet(ByVal ws As Worksheet, ByVal wanted As String)
    Dim nm As String, n As Long, tail As String
    If Len(wanted) = 0 Then Exit Sub
    wanted = Left$(wanted, 31)
    nm = wanted
    n = 1
    Do While SheetExists(ws.Parent, nm, ws)
        n = n + 1
        tail = " (" & n & ")"
        nm = Left$(wanted, 31 - Len(tail)) & tail
    Loop
    On Error Resume Next
    ws.Name = nm
    On Error GoTo 0
End Sub


Private Function SheetExists(ByVal wb As Workbook, ByVal nm As String, _
                             ByVal otherThan As Worksheet) As Boolean
    Dim sh As Object
    For Each sh In wb.Sheets
        If Not sh Is otherThan Then
            If StrComp(sh.Name, nm, vbTextCompare) = 0 Then
                SheetExists = True
                Exit Function
            End If
        End If
    Next sh
End Function


' Each row of values in one go, from column A. Text goes in behind an
' apostrophe, so Excel keeps it as typed instead of reading 1/2 as a date.
Private Sub WriteValues(ByVal ws As Worksheet, ByVal entries As Object)
    Dim entry As Object, items As Object, data() As Variant
    Dim i As Long, v As Variant
    For Each entry In entries
        Set items = Member(entry, "cells")
        If items.Count > 0 Then
            ReDim data(1 To 1, 1 To items.Count)
            i = 0
            For Each v In items
                i = i + 1
                If IsNull(v) Then
                    data(1, i) = Empty
                ElseIf VarType(v) = vbString Then
                    If Len(v) > 0 Then data(1, i) = "'" & v
                Else
                    data(1, i) = v
                End If
            Next v
            ws.Cells(entry("row"), 1).Resize(1, items.Count).Value = data
        End If
    Next entry
End Sub


Private Sub SizeGrid(ByVal ws As Worksheet, ByVal sheet As Object)
    Dim c As Object
    For Each c In Member(sheet, "columns")
        ws.Columns(CStr(c("col"))).ColumnWidth = c("width")
    Next c
    For Each c In Member(sheet, "heights")
        ws.Rows(c("row")).RowHeight = c("height")
    Next c
End Sub


Private Sub ApplyFormats(ByVal ws As Worksheet, ByVal sheet As Object)
    Dim styles As Object, f As Object, nm As String
    Set styles = Member(sheet, "styles")
    For Each f In Member(sheet, "formats")
        nm = CStr(f("style"))
        If Not styles.Exists(nm) Then Fail "no style called '" & nm & "'"
        ApplyStyle ws.Range(f("range")), styles(nm)
    Next f
End Sub


' Every key is asked after with Exists first: a Dictionary quietly adds any
' key it is read by, and a missing one would come back Empty, not Null.
Private Sub ApplyStyle(ByVal rng As Range, ByVal st As Object)
    Dim fnt As Object, al As Object, bd As Object
    If st.Exists("font") Then
        If IsObject(st("font")) Then
            Set fnt = st("font")
            If fnt.Exists("name") Then rng.Font.Name = fnt("name")
            If fnt.Exists("size") Then rng.Font.Size = fnt("size")
            If fnt.Exists("bold") Then rng.Font.Bold = fnt("bold")
        End If
    End If
    If st.Exists("fill") Then
        If IsNull(st("fill")) Then
            rng.Interior.Pattern = xlNone
        Else
            rng.Interior.Color = HexColor(st("fill"))
        End If
    End If
    If st.Exists("align") Then
        If IsObject(st("align")) Then
            Set al = st("align")
            If al.Exists("horizontal") Then _
                rng.HorizontalAlignment = HAlign(al("horizontal"))
            If al.Exists("vertical") Then _
                rng.VerticalAlignment = VAlign(al("vertical"))
        End If
    End If
    If st.Exists("border") Then
        If IsObject(st("border")) Then
            Set bd = st("border")
            ' A side's line runs between the cells of the range too: the
            ' left line becomes the inside verticals, the top line the inside
            ' horizontals, so a ruled block comes out ruled throughout.
            If bd.Exists("left") Then
                SetEdge rng, xlEdgeLeft, bd("left")
                If rng.Columns.Count > 1 Then _
                    SetEdge rng, xlInsideVertical, bd("left")
            End If
            If bd.Exists("right") Then SetEdge rng, xlEdgeRight, bd("right")
            If bd.Exists("top") Then
                SetEdge rng, xlEdgeTop, bd("top")
                If rng.Rows.Count > 1 Then _
                    SetEdge rng, xlInsideHorizontal, bd("top")
            End If
            If bd.Exists("bottom") Then SetEdge rng, xlEdgeBottom, bd("bottom")
        End If
    End If
    If st.Exists("number_format") Then
        If Not IsNull(st("number_format")) Then _
            rng.NumberFormat = st("number_format")
    End If
End Sub


Private Sub DrawOutlines(ByVal ws As Worksheet, ByVal outlines As Object)
    Dim o As Object, rng As Range
    For Each o In outlines
        Set rng = ws.Range(o("range"))
        SetEdge rng, xlEdgeLeft, o("weight")
        SetEdge rng, xlEdgeRight, o("weight")
        SetEdge rng, xlEdgeTop, o("weight")
        SetEdge rng, xlEdgeBottom, o("weight")
    Next o
End Sub


Private Sub SetUpPage(ByVal ws As Worksheet, ByVal page As Object)
    Dim margins As Object
    ' Talking to the printer for every setting is what makes PageSetup slow;
    ' Excel 2010 and later can hold it all back and send it once.
    On Error Resume Next
    Application.PrintCommunication = False
    On Error GoTo 0
    With ws.PageSetup
        If page.Exists("orientation") Then
            If LCase$(page("orientation")) = "landscape" Then
                .Orientation = xlLandscape
            Else
                .Orientation = xlPortrait
            End If
        End If
        If page.Exists("paper") Then
            Select Case UCase$(page("paper"))
                Case "A4": .PaperSize = xlPaperA4
                Case "A3": .PaperSize = xlPaperA3
                Case "LETTER": .PaperSize = xlPaperLetter
            End Select
        End If
        If page.Exists("fit_width") Or page.Exists("fit_height") Then
            .Zoom = False
            .FitToPagesWide = FitPages(page, "fit_width")
            .FitToPagesTall = FitPages(page, "fit_height")
        End If
        If page.Exists("margins_in") Then
            Set margins = page("margins_in")
            If margins.Exists("left") Then _
                .LeftMargin = Application.InchesToPoints(margins("left"))
            If margins.Exists("right") Then _
                .RightMargin = Application.InchesToPoints(margins("right"))
            If margins.Exists("top") Then _
                .TopMargin = Application.InchesToPoints(margins("top"))
            If margins.Exists("bottom") Then _
                .BottomMargin = Application.InchesToPoints(margins("bottom"))
            If margins.Exists("header") Then _
                .HeaderMargin = Application.InchesToPoints(margins("header"))
            If margins.Exists("footer") Then _
                .FooterMargin = Application.InchesToPoints(margins("footer"))
        End If
    End With
    On Error Resume Next
    Application.PrintCommunication = True
    On Error GoTo 0
End Sub


' 0 or missing is "as many pages as it takes", which Excel spells False.
Private Function FitPages(ByVal page As Object, ByVal key As String) As Variant
    FitPages = False
    If page.Exists(key) Then
        If Not IsNull(page(key)) Then
            If page(key) > 0 Then FitPages = CLng(page(key))
        End If
    End If
End Function


' ---------------------------------------------------------------------------
' style values -> Excel's
' ---------------------------------------------------------------------------

Private Sub SetEdge(ByVal rng As Range, ByVal edge As XlBordersIndex, _
                    ByVal wt As Variant)
    With rng.Borders(edge)
        If IsNull(wt) Then
            .LineStyle = xlNone
        ElseIf Len(wt) = 0 Or LCase$(wt) = "none" Then
            .LineStyle = xlNone
        Else
            .LineStyle = xlContinuous
            Select Case LCase$(wt)
                Case "hair": .Weight = xlHairline
                Case "thin": .Weight = xlThin
                Case "medium": .Weight = xlMedium
                Case "thick": .Weight = xlThick
                Case Else: Fail "unknown border weight '" & wt & "'"
            End Select
        End If
    End With
End Sub


Private Function HAlign(ByVal v As Variant) As Long
    HAlign = xlGeneral
    If IsNull(v) Then Exit Function
    Select Case LCase$(v)
        Case "left": HAlign = xlLeft
        Case "center": HAlign = xlCenter
        Case "right": HAlign = xlRight
    End Select
End Function


Private Function VAlign(ByVal v As Variant) As Long
    VAlign = xlBottom
    If IsNull(v) Then Exit Function
    Select Case LCase$(v)
        Case "top": VAlign = xlTop
        Case "center": VAlign = xlCenter
    End Select
End Function


' "B7DEE8" -> the colour Excel stores, which runs blue-green-red.
Private Function HexColor(ByVal rgbText As String) As Long
    rgbText = Replace(rgbText, "#", "")
    If Len(rgbText) <> 6 Then _
        Fail "a colour should be six hex digits: '" & rgbText & "'"
    HexColor = RGB(CLng("&H" & Mid$(rgbText, 1, 2)), _
                   CLng("&H" & Mid$(rgbText, 3, 2)), _
                   CLng("&H" & Mid$(rgbText, 5, 2)))
End Function


' ---------------------------------------------------------------------------
' reading the file
' ---------------------------------------------------------------------------

' The file as text. gh_cutlist2json writes UTF-8, which VBA's own Open
' would read in the system code page and spoil every diacritic.
Private Function ReadUtf8(ByVal path As String) As String
    Dim st As Object
    Set st = CreateObject("ADODB.Stream")
    st.Type = 2                 ' adTypeText
    st.Charset = "utf-8"
    st.Open
    st.LoadFromFile path
    ReadUtf8 = st.ReadText(-1)  ' adReadAll; a byte order mark is dropped
    st.Close
End Function


' A key of a JSON object, which must be there.
Private Function Member(ByVal obj As Object, ByVal key As String) As Variant
    If Not obj.Exists(key) Then Fail "'" & key & "' is missing from the file"
    If IsObject(obj(key)) Then
        Set Member = obj(key)
    Else
        Member = obj(key)
    End If
End Function


Private Sub Fail(ByVal message As String)
    Err.Raise vbObjectError + 513, "CutListImport", message
End Sub


' ---------------------------------------------------------------------------
' JSON
' ---------------------------------------------------------------------------
'
' A small reader for what gh_cutlist2json writes, and any other plain JSON:
'
'   object  -> Scripting.Dictionary, keys case-sensitive
'   array   -> Collection
'   string  -> String, every escape undone
'   number  -> Double, read with Val, so a decimal point is a point whatever
'              the regional settings say
'   true, false -> Boolean      null -> Null

Private Function ParseJson(ByVal text As String) As Object
    mText = text
    mLen = Len(text)
    mPos = 1
    SkipSpace
    If Peek() <> "{" Then Fail "the file does not hold a JSON object"
    Set ParseJson = ParseObject()
    SkipSpace
    ' A second document straight after the first is what gh_cutlist2json
    ' gives when it was run once per line -- name the cause, not the symptom.
    If Peek() = "{" Then
        Fail "the file holds more than one cut list, one after another. " & _
             "In Grasshopper, gh_cutlist2json ran once per line: set its " & _
             "TABLE, CAT and MATERIAL inputs to Tree Access and save the " & _
             "JSON again."
    End If
    If mPos <= mLen Then JsonFail "text after the end of the document"
End Function


' Returns its value straight into the caller's expression, never through a
' variable: a Variant that once held an object takes a later plain value
' badly.
Private Function ParseAny() As Variant
    SkipSpace
    Select Case Peek()
        Case "{": Set ParseAny = ParseObject()
        Case "[": Set ParseAny = ParseArray()
        Case """": ParseAny = ParseString()
        Case "t": Expect "true": ParseAny = True
        Case "f": Expect "false": ParseAny = False
        Case "n": Expect "null": ParseAny = Null
        Case "-", "0" To "9": ParseAny = ParseNumber()
        Case "": JsonFail "the file ends too soon"
        Case Else: JsonFail "unexpected '" & Peek() & "'"
    End Select
End Function


Private Function ParseObject() As Object
    Dim d As Object, key As String
    Set d = CreateObject("Scripting.Dictionary")
    d.CompareMode = vbBinaryCompare
    mPos = mPos + 1                     ' {
    SkipSpace
    If Peek() = "}" Then
        mPos = mPos + 1
        Set ParseObject = d
        Exit Function
    End If
    Do
        SkipSpace
        If Peek() <> """" Then JsonFail "expected a key in quotes"
        key = ParseString()
        SkipSpace
        If Peek() <> ":" Then JsonFail "expected ':' after '" & key & "'"
        mPos = mPos + 1
        If d.Exists(key) Then d.Remove key  ' the last one wins, as in Python
        d.Add key, ParseAny()
        SkipSpace
        Select Case Peek()
            Case ",": mPos = mPos + 1
            Case "}": mPos = mPos + 1: Exit Do
            Case Else: JsonFail "expected ',' or '}'"
        End Select
    Loop
    Set ParseObject = d
End Function


Private Function ParseArray() As Object
    Dim c As Collection
    Set c = New Collection
    mPos = mPos + 1                     ' [
    SkipSpace
    If Peek() = "]" Then
        mPos = mPos + 1
        Set ParseArray = c
        Exit Function
    End If
    Do
        c.Add ParseAny()
        SkipSpace
        Select Case Peek()
            Case ",": mPos = mPos + 1
            Case "]": mPos = mPos + 1: Exit Do
            Case Else: JsonFail "expected ',' or ']'"
        End Select
    Loop
    Set ParseArray = c
End Function


' Runs of plain characters are copied whole; only the escapes are taken a
' character at a time.
Private Function ParseString() As String
    Dim out As String, start As Long, ch As String
    mPos = mPos + 1                     ' opening quote
    start = mPos
    Do
        If mPos > mLen Then JsonFail "a string is not closed"
        ch = Mid$(mText, mPos, 1)
        If ch = """" Then
            out = out & Mid$(mText, start, mPos - start)
            mPos = mPos + 1
            Exit Do
        ElseIf ch = "\" Then
            out = out & Mid$(mText, start, mPos - start)
            ch = Mid$(mText, mPos + 1, 1)
            Select Case ch
                Case """", "\", "/": out = out & ch
                Case "b": out = out & Chr$(8)
                Case "f": out = out & Chr$(12)
                Case "n": out = out & vbLf
                Case "r": out = out & vbCr
                Case "t": out = out & vbTab
                Case "u"
                    out = out & ChrW$(HexCode(Mid$(mText, mPos + 2, 4)))
                    mPos = mPos + 4
                Case Else: JsonFail "unknown escape '\" & ch & "'"
            End Select
            mPos = mPos + 2
            start = mPos
        Else
            mPos = mPos + 1
        End If
    Loop
    ParseString = out
End Function


' Four hex digits -> 0..65535. CLng reads "&HFFFF" as the Integer -1, so the
' And takes the sign back off.
Private Function HexCode(ByVal digits As String) As Long
    Dim i As Long
    If Len(digits) <> 4 Then JsonFail "a \u escape needs four hex digits"
    For i = 1 To 4
        If InStr(1, "0123456789abcdefABCDEF", Mid$(digits, i, 1)) = 0 Then _
            JsonFail "a \u escape needs four hex digits"
    Next i
    HexCode = CLng("&H" & digits) And &HFFFF&
End Function


Private Function ParseNumber() As Double
    Dim start As Long
    start = mPos
    Do While mPos <= mLen
        If InStr(1, "+-0123456789.eE", Mid$(mText, mPos, 1)) = 0 Then Exit Do
        mPos = mPos + 1
    Loop
    ParseNumber = Val(Mid$(mText, start, mPos - start))
End Function


Private Sub Expect(ByVal word As String)
    If Mid$(mText, mPos, Len(word)) <> word Then JsonFail "expected " & word
    mPos = mPos + Len(word)
End Sub


Private Sub SkipSpace()
    Do While mPos <= mLen
        Select Case Mid$(mText, mPos, 1)
            Case " ", vbTab, vbCr, vbLf: mPos = mPos + 1
            Case Else: Exit Do
        End Select
    Loop
End Sub


' The next character, or "" at the end.
Private Function Peek() As String
    If mPos <= mLen Then Peek = Mid$(mText, mPos, 1)
End Function


Private Sub JsonFail(ByVal message As String)
    Fail "the JSON is broken at character " & mPos & ": " & message
End Sub
