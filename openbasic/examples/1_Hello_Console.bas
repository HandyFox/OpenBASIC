' Hello Console - the classic mainwin text window
print "Welcome to OpenBASIC!"
print
input "What is your name? "; name$
print "Hello, "; name$; "!"
print
print "Here are the squares from 1 to 10:"
for i = 1 to 10
    print i; " squared is "; i ^ 2
next i
print
print "Today is "; date$(); " and the time is "; time$()
end
