' GUI Form - a window with controls, made the FreeForm way
    nomainwin
    dim fruit$(10)
    fruit$(1) = "Apples" : fruit$(2) = "Bananas" : fruit$(3) = "Cherries"
    WindowWidth = 420
    WindowHeight = 330
    UpperLeftX = int((DisplayWidth-WindowWidth)/2)
    UpperLeftY = int((DisplayHeight-WindowHeight)/2)

    groupbox #main.group, "Add a fruit", 10, 10, 385, 70
    textbox #main.newFruit, 25, 35, 240, 25
    button #main.add, "Add", [addFruit], UL, 280, 35, 100, 25
    statictext #main.label, "Double-click a fruit to pick it:", 10, 95, 260, 20
    listbox #main.list, fruit$(), [pick], 10, 118, 250, 150
    checkbox #main.loud, "Shout it", [nothing], [nothing], 275, 118, 120, 20
    button #main.quit, "Quit", [quit], UL, 295, 240, 100, 28
    open "Fruit Picker" for window_nf as #main
    print #main, "font ms_sans_serif 10"
    print #main, "trapclose [quit]"
    print #main.newFruit, "!setfocus"
    count = 3
    wait

[addFruit]
    print #main.newFruit, "!contents? f$"
    if trim$(f$) = "" then notice "Type a fruit first" : wait
    if count >= 10 then notice "The list is full" : wait
    count = count + 1
    fruit$(count) = trim$(f$)
    print #main.list, "reload"
    print #main.newFruit, ""
    wait

[pick]
    print #main.list, "selection? choice$"
    print #main.loud, "value? loud$"
    if loud$ = "set" then choice$ = upper$(choice$) + "!!!"
    notice "Fruit Picker" + chr$(13) + "You picked " + choice$
    wait

[nothing]
    wait

[quit]
    close #main
    end
