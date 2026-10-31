open "info.inf" for input as #inf
input #inf, openbefore$
close #inf

if openbefore$ = "false" then
confirm "In order for the following program to work you will need to set your environment variable. Open in help now?"; sysvaryes$
end if
if sysvaryes$ = "yes" then
open "info.inf" for output as #out
print #out, "true"
close #out
gosub [help]
end if

    nomainwin
protected$ = "false"
out$ = "closed"
i = 0
    WindowWidth = 352
    WindowHeight = 390
    menu #main, "&File", "Resend &Profile    Alt+P", [send], |, "&Review Profile", [review], |, "&Environment Variable Help", [h], |, "Command Prompt", [cmd]
    groupbox #main.groupbox1, "Information", 14, 206, 312, 120
    groupbox #main.groupbox2, "Ponderosa Installation Guide", 14, 11, 312, 190
    statictext #main.statictext4, "First click on Step 1. In the command prompt", 30, 46, 280, 20
    statictext #main.statictext5, "window that appears do a right click, next click", 30, 71, 288, 20
    statictext #main.statictext6, "select all, then press enter (to copy). Now click", 30, 96, 280, 20
    statictext #main.statictext7, "Step 2.", 30, 121, 48, 20
    button #main.button8, "Step 1", [step1], UL, 54, 151, 75, 35
    button #main.button9, "Step 2", [saveasphonelog.txt], UL, 190, 151, 75, 35
    statictext #main.Info, "", 35, 230, 225, 150
    open "Ponderosa Helper" for window_nf as #main
    print #main, "font ms_sans_serif 0 16"
    print #main, "trapclose [closemain]"

wait
[cmd]
run "cmd.exe"
wait
[h]
gosub [help]
wait

[step1]   'Perform action for the button named 'button8'
 gosub [Install]
 goto [listpackage]   'Insert your own code here
    wait


[printno]
timer 0
print #main.Info, ""
wait

[Install]   'Perform action for the button named 'button4'
 run "cmd.exe /k adb install ponderosa.apk", showminimized  'Insert your own code here
 print #main.Info, "Check your device to verify ponderosa's installation."
 timer 5000, [printno]
 return
    wait


[listpackage]   'Perform action for the button named 'button11'
 run "cmd.exe /k adb shell pm list packages"  'Insert your own code here
    wait


[saveasphonelog.txt]   'Perform action for the button named 'button12'
if protected$ = "false" then
confirm "It is highly recommened that you password protect your profile. If your profile is not password protected the user can remove it at any time. Do you want to protect it now?";response$
if response$ = "yes" then
gosub [protect]
end if
end if
open "temp" for text as #temp
print #temp, "!paste"
print #temp, "!contents? string$"
close #temp
open "PHONELOG.txt" for output as #out
print #out, string$
close #out
goto [create]
wait



[SendProfile]   'Perform action for the button named 'button25'
run "cmd.exe /k adb shell dpm set-device-owner io.compassfoundation.ponderosa/.DeviceOwnerReceiver", showminimized
[send]
run "cmd.exe /k adb push profile.json /sdcard/profile.json", showminimized

print #main.Info, "On your device open Ponderosa,load your profile, and your done!"
timer 5000, [printno]
   'Insert your own code here
    wait












[create]


    nomainwin

    WindowWidth = 470
    WindowHeight = 520

    textbox #results.line1, 86, 151, 344, 25
    bmpbutton #results.bmpbutton2, "bmp\CHECK.BMP", [line1accept], UL, 38, 146
    textbox #results.line2, 86, 196, 344, 25
    bmpbutton #results.bmpbutton4, "bmp\CHECK.BMP", [line2accept], UL, 38, 191
    textbox #results.line3, 86, 241, 344, 25
    bmpbutton #results.bmpbutton6, "bmp\CHECK.BMP", [line3accept], UL, 38, 236
    textbox #results.line4, 86, 286, 344, 25
    bmpbutton #results.bmpbutton8, "bmp\CHECK.BMP", [line4], UL, 38, 276
    textbox #results.line5, 86, 326, 344, 25
    bmpbutton #results.bmpbutton10, "bmp\CHECK.BMP", [line5accept], UL, 38, 316
    textbox #results.line6, 86, 366, 344, 25
    bmpbutton #results.bmpbutton12, "bmp\CHECK.BMP", [line6accept], UL, 38, 361
    textbox #results.line7, 86, 406, 344, 25
    bmpbutton #results.bmpbutton14, "bmp\CHECK.BMP", [line7accept], UL, 38, 401
    textbox #results.line8, 86, 446, 344, 25
    bmpbutton #results.bmpbutton16, "bmp\CHECK.BMP", [line8accept], UL, 38, 441
    textbox #results.Search, 230, 61, 168, 25
    statictext #results.statictext20, "Enter Your Search in Here", 60, 66, 200, 20
    button #results.button21, "Search", [Search], UL, 230, 106, 70, 30
    button #results.button22, "Name and Protect", [protectfromsearch], UL, 38, 106, 138, 25
    button #results.button23, "Open Profile", [openprofile], UL, 158, 16, 106, 25
    button #results.button24, "Save Profile", [saveprofilefromsearch], UL, 14, 16, 106, 25
    button #results.done, "Done", [done], UL, 350, 106, 70, 30
    open "Create a Profile (Ponderosa Helper)" for dialog as #results
    print #results, "trapclose [done]"
    print #results, "font ms_sans_serif 0 16"
    print #results.Search, "!setfocus"
    if protected$ = "true" then
     print #results.button22, "!disable"
     print #results.button22, "Profile Protected"
    end if
wait
[protectfromsearch]
print #results.button22, "!disable"
print #results.button22, "Profile Protected"
gosub [protect]
wait

[saveprofilefromsearch]
gosub [saveprofile]
wait

[done]
r = 0
in$ = "closed"
if one$ > "" then
confirm "Save Profile";profilesave$
if profilesave$ = "yes" then
gosub [saveprofile]
end if
end if
close #results
goto [profile]
wait

[line1accept]   'Perform action for the bmpbutton named 'bmpbutton2'
print #results.line1, "!contents? temp$"
 goto [extractemps]    'Insert your own code here
    wait


[line2accept]   'Perform action for the bmpbutton named 'bmpbutton4'
  print #results.line2, "!contents? temp$"
 goto [extractemps]  'Insert your own code here
    wait


[line3accept]   'Perform action for the bmpbutton named 'bmpbutton6'
 print #results.line3, "!contents? temp$"
 goto [extractemps]   'Insert your own code here
    wait


[line4]   'Perform action for the bmpbutton named 'bmpbutton8'
 print #results.line4, "!contents? temp$"
 goto [extractemps]   'Insert your own code here
    wait


[line5accept]   'Perform action for the bmpbutton named 'bmpbutton10'
 print #results.line5, "!contents? temp$"
 goto [extractemps]   'Insert your own code here
    wait


[line6accept]   'Perform action for the bmpbutton named 'bmpbutton12'
  print #results.line6, "!contents? temp$"
 goto [extractemps]  'Insert your own code here
    wait


[line7accept]   'Perform action for the bmpbutton named 'bmpbutton14'
 print #results.line7, "!contents? temp$"
 goto [extractemps]   'Insert your own code here
    wait


[line8accept]   'Perform action for the bmpbutton named 'bmpbutton16'
 print #results.line8, "!contents? temp$"
 goto [extractemps]   'Insert your own code here
    wait


[matched]   'Perform action for the button named 'button21'


     r = r + 1
    if r = 1 then
      matches = 1
      l = len(line$) - 8
      print #results.line1, right$(line$, l)
    end if
    if r = 2 then
     l = len(line$) - 8
     print #results.line2, right$(line$, l)
    end if
    if r = 3 then
     l = len(line$) - 8
     print #results.line3, right$(line$, l)
    end if
    if r = 4 then
     l = len(line$) - 8
     print #results.line4, right$(line$, l)
    end if
    if r = 5 then
     l = len(line$) - 8
     print #results.line5, right$(line$, l)
    end if
    if r = 6 then
     l = len(line$) - 8
     print #results.line6, right$(line$, l)
    end if
    if r = 7 then
     l = len(line$) - 8
     print #results.line7, right$(line$, l)
    end if
    if r = 8 then
     l = len(line$) - 8
     print #results.line8, right$(line$, l)
    end if


    foundFlag = 1


    'only check for quit response


    return   'Insert your own code here
    wait


[Search]   'Perform action for the button named 'button3'
 r = 0
 print #results.line1, ""
 print #results.line2, ""
 print #results.line3, ""
 print #results.line4, ""
 print #results.line5, ""
 print #results.line6, ""
 print #results.line7, ""
 print #results.line8, ""

 print #results.Search, "!contents? searchCalled$"   'Insert your own code here





[searchByPersonCalled]  'look for a phone log entry by person called


    if searchCalled$ = "" then
     notice "You entered nothing to search"
     wait
    end if  'nothing entered, abort search

    searchCalled$ = upper$(searchCalled$)'convert to uppercase for search

    open "PHONELOG.TXT" for input as #in

    foundFlag = 0
    quitFlag = 0
    if eof(#in) = -1 then [endOfCalledSearch]


[searchByCalledLoop]

    gosub [readEntry]  'get next entry from PHONELOG.TXT
    if instr(upper$(line$), searchCalled$) > 0 then gosub [matched]
    l = 0
    if eof(#in) = 0 and quitFlag = 0 then goto [searchByCalledLoop]

[endOfCalledSearch]
    close #in
   wait


[readEntry]  'read the next entry from PHONELOG.TXT

    line input #in, line$
    if line$ = "" then
    if matches < 1 then
    notice "No matches found"
    end if
    close #in
    wait
    end if


    return




[extractemps]
print #results.Search, ""
print #results.Search, "!setfocus"
i = i + 1
if i = 1 then one$ = temp$
if i = 2 then two$ = temp$
if i = 3 then three$ = temp$
if i = 4 then four$ = temp$
if i = 5 then five$ = temp$
if i = 6 then six$ = temp$
if i = 7 then seven$ = temp$
if i = 8 then eight$ = temp$
if i = 9 then nine$ = temp$
if i = 10 then ten$ = temp$
if i = 11 then eleven$ = temp$
if i = 12 then twelve$ = temp$
if i = 13 then thirteen$ = temp$
if i = 14 then fourteen$ = temp$
if i = 15 then fifteen$ = temp$
if i = 16 then sixteen$ = temp$
if i = 17 then seventeen$ = temp$
if i = 18 then eighteen$ = temp$
if i = 19 then nineteen$ = temp$
if i = 20 then twenty$ = temp$
if i = 21 then twentyone$ = temp$
if i = 22 then twentytwo$ = temp$
if i = 23 then twentythree$ = temp$
if i = 24 then twentyfour$ = temp$
if i = 25 then twenyfive$ = temp$
if i = 26 then twentysix$ = temp$
if i = 27 then twentyseven$ = temp$
if i = 28 then twentyeight$ = temp$
if i = 29 then twentynine$ = temp$
if i = 30 then thirty$ = temp$
wait

[profile]
if profile$ = "open" then
close #profile
profile$ = "closed"
end if
open "profile.json" for output as #profile
print #profile,"{"
print #profile, "         "+chr$(34)+"enabled apps"+chr$(34)+": ["
if i > 1 then print #profile, "               "+chr$(34)+ one$+ chr$(34) + ","
if i = 1 then print #profile, "               "+chr$(34)+ one$+ chr$(34) + ""
if i > 2 then print #profile, "               "+chr$(34)+ two$+ chr$(34) + ","
if i = 2 then print #profile, "               "+chr$(34)+ two$+ chr$(34) + ""
if i > 3 then print #profile, "               "+chr$(34)+ three$+ chr$(34) + ","
if i = 3 then print #profile, "               "+chr$(34)+ three$+ chr$(34) + ""
if i > 4 then print #profile, "               "+chr$(34)+ four$+ chr$(34) + ","
if i = 4 then print #profile, "               "+chr$(34)+ four$+ chr$(34) + ""
if i > 5 then print #profile, "               "+chr$(34)+ five$+ chr$(34) + ","
if i = 5 then print #profile, "               "+chr$(34)+ five$+ chr$(34) + ""
if i > 6 then print #profile, "               "+chr$(34)+ six$+ chr$(34) + ","
if i = 6 then print #profile, "               "+chr$(34)+ six$+ chr$(34) + ""
if i > 7 then print #profile, "               "+chr$(34)+ seven$+ chr$(34) + ","
if i = 7 then print #profile, "               "+chr$(34)+ seven$+ chr$(34) + ""
if i > 8 then print #profile, "               "+chr$(34)+ eight$+ chr$(34) + ","
if i = 8 then print #profile, "               "+chr$(34)+ eight$+ chr$(34) + ""
if i > 9 then print #profile, "               "+chr$(34)+ nine$+ chr$(34) + ","
if i = 9 then print #profile, "               "+chr$(34)+ nine$+ chr$(34) + ""
if i > 10 then print #profile, "               "+chr$(34)+ ten$+ chr$(34) + ","
if i = 10 then print #profile, "               "+chr$(34)+ ten$+ chr$(34) + ""
if i > 11 then print #profile, "               "+chr$(34)+ eleven$+ chr$(34) + ","
if i = 11 then print #profile, "               "+chr$(34)+ eleven$+ chr$(34) + ""
if i > 12 then print #profile, "               "+chr$(34)+ twelve$+ chr$(34) + ","
if i = 12 then print #profile, "               "+chr$(34)+ twelve$+ chr$(34) + ""
if i > 13 then print #profile, "               "+chr$(34)+ thirteen$+ chr$(34) + ","
if i = 13 then print #profile, "               "+chr$(34)+ thirteen$+ chr$(34) + ""
if i > 14 then print #profile, "               "+chr$(34)+ fourteen$+ chr$(34) + ","
if i = 14 then print #profile, "               "+chr$(34)+ fourteen$+ chr$(34) + ""
if i > 15 then print #profile, "               "+chr$(34)+ fifteen$+ chr$(34) + ","
if i = 15 then print #profile, "               "+chr$(34)+ fifteen$+ chr$(34) + ""
if i > 16 then print #profile, "               "+chr$(34)+ sixteen$+ chr$(34) + ","
if i = 16 then print #profile, "               "+chr$(34)+ sixteen$+ chr$(34) + ""
if i > 17 then print #profile, "               "+chr$(34)+ seventeen$+ chr$(34) + ","
if i = 17 then print #profile, "               "+chr$(34)+ seventeen$+ chr$(34) + ""
if i > 18 then print #profile, "               "+chr$(34)+ eighteen$+ chr$(34) + ","
if i = 18 then print #profile, "               "+chr$(34)+ eighteen$+ chr$(34) + ""
if i > 19 then print #profile, "               "+chr$(34)+ nineteen$+ chr$(34) + ","
if i = 19 then print #profile, "               "+chr$(34)+ nineteen$+ chr$(34) + ""
if i > 20 then print #profile, "               "+chr$(34)+ twenty$+ chr$(34) + ","
if i = 20 then print #profile, "               "+chr$(34)+ twenty$+ chr$(34) + ""
if i > 21 then print #profile, "               "+chr$(34)+ twentyone$+ chr$(34) + ","
if i = 21 then print #profile, "               "+chr$(34)+ twentyone$+ chr$(34) + ""
if i > 22 then print #profile, "               "+chr$(34)+ twentytwo$+ chr$(34) + ","
if i = 22 then print #profile, "               "+chr$(34)+ twentyone$+ chr$(34) + ""
if i > 23 then print #profile, "               "+chr$(34)+ twentythree$+ chr$(34) + ","
if i = 23 then print #profile, "               "+chr$(34)+ twentythree$+ chr$(34) + ""
if i > 24 then print #profile, "               "+chr$(34)+ twentyfour$+ chr$(34) + ","
if i = 24 then print #profile, "               "+chr$(34)+ twentyfour$+ chr$(34) + ""
if i > 25 then print #profile, "               "+chr$(34)+ twentyfive$+ chr$(34) + ","
if i = 25 then print #profile, "               "+chr$(34)+ twentyfive$+ chr$(34) + ""
if i > 26 then print #profile, "               "+chr$(34)+ twentysix$+ chr$(34) + ","
if i = 26 then print #profile, "               "+chr$(34)+ twentysix$+ chr$(34) + ""
if i > 27 then print #profile, "               "+chr$(34)+ twentyseven$+ chr$(34) + ","
if i = 27 then print #profile, "               "+chr$(34)+ twentyseven$+ chr$(34) + ""
if i > 28 then print #profile, "               "+chr$(34)+ twentyeight$+ chr$(34) + ","
if i = 28 then print #profile, "               "+chr$(34)+ twentyeight$+ chr$(34) + ""
if i > 29 then print #profile, "               "+chr$(34)+ twentynine$+ chr$(34) + ","
if i = 29 then print #profile, "               "+chr$(34)+ twentynine$+ chr$(34) + ""
if i > 30 then print #profile, "               "+chr$(34)+ thirty$+ chr$(34) + ","
if i = 30 then print #profile, "               "+chr$(34)+ thirty$+ chr$(34) + ""
print #profile,""
print #profile,"           ],"
print #profile,"             "+chr$(34)+"name "+chr$(34)+": "+chr$(34)+name$+chr$(34)+","
print #profile,"             "+chr$(34)+"password"+chr$(34)+": "+chr$(34)+ password$+chr$(34)+""
print #profile,"}"
close #profile
print #main.Info, "Profile Created Successfuly"
timer 5000, [printno]
goto [SendProfile]
wait

[protect]

protected$ = "true"
    nomainwin

    WindowWidth = 328
    WindowHeight = 205

    textbox #pass.name, 150, 31, 152, 25
    statictext #pass.statictext2, "Name the Profile", 30, 36, 104, 20
    textbox #pass.Password, 150, 81, 152, 25
    statictext #pass.statictext4, "Password Protect", 22, 71, 120, 20
    statictext #pass.statictext5, "this keeps from", 22, 91, 120, 20
    statictext #pass.statictext6, "unrestricted force", 22, 111, 152, 20
    statictext #pass.statictext7, "stops.", 22, 131, 48, 20
    button #pass.button8, "Ok", [button8Click], UL, 230, 131, 50, 25
    open "Name and Protect" for dialog as #pass
    print #pass, "font ms_sans_serif 0 16"
    print #pass, "trapclose [closepass]"



    wait



[button8Click]   'Perform action for the button named 'button8'
print #pass.name, "!contents? name$"
print #pass.Password, "!contents? password$"    'Insert your own code here
close #pass
return
    wait
[closepass]
close #pass
wait


[closesearch]
close #search
wait

[closemain]
close #main
end

[closehelp]
close #help1
return
wait
[review]
profile$ = "open"
run "notepad.exe profile.json"
wait


[help]

loadbmp "var", "bmp\var.bmp"

    nomainwin

    WindowWidth = 696
    WindowHeight = 400

    statictext #help1.statictext1, "In your start menu search for 'Environment Variables'", 22, 11, 320, 20
    statictext #help1.statictext2, "When 'Edit Systemnvironment variables comes up", 22, 36, 328, 20
    statictext #help1.statictext3, "click on that. In the little window that appears find and", 22, 61, 320, 25
    statictext #help1.statictext4, "click on 'Environment Variables' it should be near the", 22, 86, 328, 20
    statictext #help1.statictext5, "bottom of the window. In the next window find the", 22, 111, 304, 20
    statictext #help1.statictext6, "groupbox named 'System Variables' in the box scroll ", 22, 136, 328, 20
    statictext #help1.statictext7, "down to path double click on that, now at the bottom", 22, 166, 320, 20
    statictext #help1.statictext8, "of this help window is a button named 'Copy to Clipboard'", 22, 191, 344, 20
    statictext #help1.statictext9, "click on that to copy your needed information to your", 22, 216, 320, 20
    statictext #help1.statictext10, "clipboard. Back on the last window that you brought up", 22, 241, 328, 20
    statictext #help1.statictext11, "place you curser at the end of the row of paths and", 30, 266, 304, 20
    statictext #help1.statictext12, "do a right click then click on paste. This should have", 22, 296, 328, 20
    statictext #help1.statictext13, "pasted somthing like ; C:/Program File(X86)/platform-tools.", 22, 321, 352, 20
    bmpbutton #help1.link "bmp\link.bmp", [golink], UL, 14, 340
    graphicbox #help1.graph, 374, 11, 304, 315
    button #help1.button15, "Copy to Clipboard", [CTC], UL, 525, 335, 146, 25
    open "Help" for window_nf as #help1
    print #help1.graph, "fill white; flush"
    print #help1.graph, "background var"
    print #help1.graph, "drawsprites"
    print #help1.graph, "flush"
    print #help1, "font ms_sans_serif 0 16"
    print #help1, "trapclose [closehelp]"

    wait



[CTC]   'Perform action for the button named 'button15'
open "Var" for text as #Variable
print #Variable, ";C\Program Files(x86)\platform-tools"
print #Variable, "!selectall"
print #Variable, "!copy"
close #Variable
wait'Insert your own code here
    wait


[golink]
close #help1
    nomainwin

    WindowWidth = 536
    WindowHeight = 260

    statictext #help2.statictext1, "Open up Windows Explorer and find were it says Computer do a right click on that", 14, 16, 480, 20
    statictext #help2.statictext2, "then click on properties. In your computer information window that pops up click on", 14, 36, 488, 20
    statictext #help2.statictext3, "Advanced System Settings. In the 'Advanced System Settings window click on", 14, 61, 488, 20
    statictext #help2.statictext4, "'Environment Variables'. Locate the System Variables box scroll down to the one", 14, 81, 504, 20
    statictext #help2.statictext5, "named 'Path'. Double click on it. Now click on the 'Copy to Clipboard' button at the", 14, 106, 480, 20
    statictext #help2.statictext6, "bottom of this page. Next place your curser at the end of the row of variables, right", 14, 131, 488, 20
    statictext #help2.statictext7, "click, click paste, click all the 'OK' boxes out of there, and your done!", 14, 156, 488, 20
    button #help2.button8, "Return To Help", [returntohelp], UL, 286, 191, 122, 25
    button #help2.button15, "Copy to Clipboard", [CTC], UL, 100, 191, 146, 25
    button #help2.button9, "Done", [closehelp2], UL, 446, 191, 55, 25
    open "Help (Ponderosa Helper)" for window_nf as #help2
    print #help2, "font ms_sans_serif 0 16"
    print #help2, "trapclose [closehelp2]"


[help2.inputLoop]   'wait here for input event
    wait



[returntohelp]   'Perform action for the button named 'button8'
 close #help2
 goto [help]   'Insert your own code here
    wait


[closehelp2]   'Perform action for the button named 'button9'
 close #help2
 return   'Insert your own code here
    wait

[saveprofile]
if name$ = "" then
prompt "Please Name" + chr$(13) + "Please enter a name to save your profile as"; name$
end if
if i = 0 then
 notice "Your profile is empty"
 wait
end if
open ""+name$+".php" for output as #php
print #php, i
print #php, name$
print #php, password$
if i = 1 or i > 1 then print #php, one$
if i = 2 or i > 2 then print #php, two$
if i = 3 or i > 3 then print #php, three$
if i = 4 or i > 4 then print #php, four$
if i = 5 or i > 5 then print #php, five$
if i = 6 or i > 6 then print #php, six$
if i = 7 or i > 7 then print #php, seven$
if i = 8 or i > 8 then print #php, eight$
if i = 9 or i > 9 then print #php, nine$
if i = 10 or i > 10 then print #php, ten$
if i = 11 or i > 11 then print #php, eleven$
if i = 12 or i > 12 then print #php, twelve$
if i = 13 or i > 13 then print #php, thirteen$
if i = 14 or i > 14 then print #php, fourteen$
if i = 15 or i > 15 then print #php, fifteen$
if i = 16 or i > 16 then print #php, sixteen$
if i = 17 or i > 17 then print #php, seventeen$
if i = 18 or i > 18 then print #php, eighteen$
if i = 19 or i > 19 then print #php, nineteen$
if i = 20 or i > 20 then print #php, twenty$
if i = 21 or i > 21 then print #php, twentyone$
if i = 22 or i > 22 then print #php, twentythree$
if i = 23 or i > 23 then print #php, twentyfour$
if i = 24 or i > 24 then print #php, twentyfive$
if i = 25 or i > 25 then print #php, twentysix$
if i = 26 or i > 26 then print #php, twentyseven$
if i = 27 or i > 27 then print #php, twentyeight$
if i = 28 or i > 28 then print #php, twentynine$
if i = 29 or i > 29 then print #php, thirty$
close #php
return
wait

[openprofile]
filedialog "Select a file to open", "*.php", profilepath$

open profilepath$ for input as #php
input #php, i
input #php, name$
input #php, password$
if i = 1 or i > 1 then input #php, one$
if i = 2 or i > 2 then input #php, two$
if i = 3 or i > 3 then input #php, three$
if i = 4 or i > 4 then input #php, four$
if i = 5 or i > 5 then input #php, five$
if i = 6 or i > 6 then input #php, six$
if i = 7 or i > 7 then input #php, seven$
if i = 8 or i > 8 then input #php, eight$
if i = 9 or i > 9 then input #php, nine$
if i = 10 or i > 10 then input #php, ten$
if i = 11 or i > 11 then input #php, eleven$
if i = 12 or i > 12 then input #php, twelve$
if i = 13 or i > 13 then input #php, thirteen$
if i = 14 or i > 14 then input #php, fourteen$
if i = 15 or i > 15 then input #php, fifteen$
if i = 16 or i > 16 then input #php, sixteen$
if i = 17 or i > 17 then input #php, seventeen$
if i = 18 or i > 18 then input #php, eighteen$
if i = 19 or i > 19 then input #php, nineteen$
if i = 20 or i > 20 then input #php, twenty$
if i = 21 or i > 21 then input #php, twentyone$
if i = 22 or i > 22 then input #php, twentythree$
if i = 23 or i > 23 then input #php, twentyfour$
if i = 24 or i > 24 then input #php, twentyfive$
if i = 25 or i > 25 then input #php, twentysix$
if i = 26 or i > 26 then input #php, twentyseven$
if i = 27 or i > 27 then input #php, twentyeight$
if i = 28 or i > 28 then input #php, twentynine$
if i = 29 or i > 29 then input #php, thirty$
close #php
wait
