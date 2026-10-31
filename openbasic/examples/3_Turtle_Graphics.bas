' Turtle Graphics - draw a colorful spiral, click to redraw
    nomainwin
    WindowWidth = 520
    WindowHeight = 560
    open "Turtle Spiral (click to redraw)" for graphics_nf_nsb as #g
    print #g, "trapclose [quit]"
    print #g, "when leftButtonDown [draw]"

[draw]
    print #g, "fill black"
    print #g, "size 2"
    print #g, "home ; north ; down"
    colors$ = "red yellow green cyan blue pink"
    angle = int(rnd(1) * 4) + 89
    for i = 1 to 220
        print #g, "color "; word$(colors$, (i mod 6) + 1)
        print #g, "go "; i * 1.1
        print #g, "turn "; angle
    next i
    print #g, "up ; place 10 20 ; color white"
    print #g, "\Turn angle: "; angle
    print #g, "flush"
    wait

[quit]
    close #g
    end
