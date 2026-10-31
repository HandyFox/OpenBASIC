' Sprite Bounce - sprites and a timer, no bitmap files needed.
' The sprite bitmap is drawn first, then captured with getbmp.
' Like Just BASIC, a sprite bitmap has its mask on top (black = solid)
' and the picture underneath (black background).
    nomainwin
    WindowWidth = 520
    WindowHeight = 420
    graphicbox #w.g, 0, 0, 500, 380
    open "Sprite Bounce" for window_nf as #w
    print #w, "trapclose [quit]"

    ' --- draw the mask (white background, black ball) ---
    print #w.g, "fill white ; down"
    print #w.g, "color black ; backcolor black"
    print #w.g, "place 20 20 ; circlefilled 18"
    ' --- draw the picture (black background, colored ball) ---
    print #w.g, "color black ; backcolor black ; place 0 40 ; boxfilled 40 80"
    print #w.g, "color yellow ; backcolor red ; place 20 60 ; circlefilled 18"
    print #w.g, "getbmp ball 0 0 40 80"

    ' --- background ---
    print #w.g, "fill darkblue"
    for i = 1 to 60
        print #w.g, "color white ; set "; int(rnd(1) * 500); " "; int(rnd(1) * 380)
    next i
    print #w.g, "getbmp sky 0 0 500 380"
    print #w.g, "background sky"

    for i = 1 to 5
        print #w.g, "addsprite ball"; i; " ball"
        x(i) = rnd(1) * 400 : y(i) = rnd(1) * 300
        dx(i) = rnd(1) * 6 + 2 : dy(i) = rnd(1) * 6 + 2
    next i
    timer 30, [move]
    wait

[move]
    for i = 1 to 5
        x(i) = x(i) + dx(i) : y(i) = y(i) + dy(i)
        if x(i) < 0 or x(i) > 460 then dx(i) = 0 - dx(i)
        if y(i) < 0 or y(i) > 340 then dy(i) = 0 - dy(i)
        print #w.g, "spritexy ball"; i; " "; int(x(i)); " "; int(y(i))
    next i
    print #w.g, "drawsprites"
    wait

[quit]
    timer 0
    close #w
    end
