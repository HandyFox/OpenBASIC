' Notepad - a texteditor with a File menu
    nomainwin
    WindowWidth = 600
    WindowHeight = 450
    menu #pad, "&File", "&New", [new], "&Open...", [open], "&Save...", [save], |, "E&xit", [quit]
    texteditor #pad.text, 0, 0, 584, 388
    open "Tiny Notepad" for window as #pad
    print #pad, "trapclose [quit]"
    print #pad.text, "!setfocus"
    wait

[new]
    print #pad.text, "!cls"
    wait

[open]
    filedialog "Open a text file", "*.txt;*.bas", f$
    if f$ = "" then wait
    open f$ for input as #f
    text$ = input$(#f, lof(#f))
    close #f
    print #pad.text, "!cls"
    print #pad.text, text$;
    wait

[save]
    filedialog "Save as", "*.txt", f$
    if f$ = "" then wait
    print #pad.text, "!contents? text$"
    open f$ for output as #f
    print #f, text$;
    close #f
    notice "Saved" + chr$(13) + "Saved to " + f$
    wait

[quit]
    close #pad
    end
