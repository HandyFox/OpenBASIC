
    nomainwin

    WindowWidth = 992
    WindowHeight = 625

    loadbmp "gameBackground", "C:\My Basic Files\Barn.bmp"
    loadbmp "target", "C:\My Basic Files\target.bmp"
    loadbmp "horizontal", "C:\My Basic Files\horizontal.bmp"
    loadbmp "vertical", "C:\My Basic Files\vertical.bmp"
    loadbmp "square", "C:\My Basic Files\square.bmp"

    graphicbox #main.graph, 54, 1, 872, 595
    open "Test" for window as #main
    print #main.graph, "fill white; flush"
    print #main, "font ms_sans_serif 0 16"

    print #main.graph, "background gameBackground"
    print #main.graph, "drawsprites"
    print #main.graph, "addsprite square square"
    print #main.graph, "addsprite target target"
    print #main.graph, "addsprite right horizontal"
    print #main.graph, "addsprite left horizontal"
    print #main.graph, "addsprite top vertical"
    print #main.graph, "addsprite bottom vertical"
    print #main.graph, "setfocus"
    print #main.graph, "when mouseMove [move]"
    print #main, "trapclose [quit]"
[genrand]

 RandomNumber = int(rnd(1)*6) + 1
 if RandomNumber = 1 then goto [topwin]
 if RandomNumber = 2 then goto [topleftwin]
 if RandomNumber = 3 then goto [toprightwin]
 if RandomNumber = 4 then goto [topmiddlewin]
 if RandomNumber = 5 then goto [bottomleftwin]
 if RandomNumber = 6 then goto [bottomrightwin]



[move]
print #main.graph, "spritexy square "; MouseX-20; " ";MouseY-4;
print #main.graph, "spritexy right "; MouseX-8; " "; MouseY-4;
print #main.graph, "spritexy top "; MouseX-20; " "; MouseY+8;
print #main.graph, "spritexy bottom "; MouseX-20; " "; MouseY-40;
print #main.graph, "spritexy left "; MouseX-80; " "; MouseY-4;
print #main.graph, "drawsprites"
wait
[topwin]
print #main.graph, "spritexy target 415 147"
print #main.graph, "drawsprites"
wait

[topleftwin]
print #main.graph, "spritexy target 185 294"
print #main.graph, "drawsprites"

wait
[topmiddlewin]

print #main.graph, "spritexy target 406 295"
print #main.graph, "drawsprites"

wait

[toprightwin]
print #main.graph, "spritexy target 613 294"
print #main.graph, "drawsprites"

wait


[bottomrightwin]
print #main.graph, "spritexy target 626 479"
print #main.graph, "drawsprites"

wait

[bottomleftwin]
print #main.graph, "spritexy target 188 472"
print #main.graph, "drawsprites"

wait

[quit]

close #main
end
