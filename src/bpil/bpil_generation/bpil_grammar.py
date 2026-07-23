BPIL_GRAMMAR = r'''
root ::= bpil-object

bpil-object ::= "{\"id\":" qstring ",\"pools\":" pools-array ",\"lanes\":" lanes-object ",\"flows\":" flows-array "}"

qstring ::= "\"" qchar* "\""
qchar ::= [^"\\] | "\\" ["\\/bfnrt]

pools-array ::= "[]" | "[" pool-item ("," pool-item)* "]"
pool-item ::= "\"" pool-id "(" label-text ")\""

lanes-object ::= "{}" | "{" lane-entry ("," lane-entry)* "}"
lane-entry ::= "\"" pool-id "\"" ":" lane-array
lane-array ::= "[]" | "[" lane-item ("," lane-item)* "]"
lane-item ::= "\"" lane-id "(" label-text ")\""

flows-array ::= "[]" | "[" flow-item ("," flow-item)* "]"
flow-item ::= "\"" flow-def "\""

flow-def ::= seq-flow | msg-flow
seq-flow ::= flow-elem seq-arrow flow-elem
msg-flow ::= flow-elem msg-arrow msg-target

seq-arrow ::= "--->" | "--(" arrow-label ")->" | "--((" arrow-label "))->"
msg-arrow ::= "..->" | "..(" arrow-label ")->"

arrow-label ::= arrow-char+
arrow-char ::= [^)>"\\]

msg-target ::= flow-elem | pool-id

flow-elem ::= elem-with-def | elem-ref

elem-with-def ::= task-elem | event-elem | gateway-elem
elem-ref ::= elem-prefix

task-elem ::= container-id ".t" digit digit digit ":" task-type "(" label-text ")"
task-type ::= "none" | "user" | "service" | "businessRule" | "script"

event-elem ::= container-id ".e" digit digit digit ":" event-type "(" label-text ")"
event-type ::= event-base | event-base "_" event-def
event-base ::= "start" | "end" | "icatch" | "ithrow"
event-def ::= "m" | "t" | "e"

gateway-elem ::= container-id ".g" digit digit digit ":" gateway-type "(" label-text ")"
gateway-type ::= "xor" | "and" | "or" | "event"

elem-prefix ::= container-id "." elem-id
container-id ::= lane-id | pool-id

lane-id ::= "l" digit digit digit
pool-id ::= "p" digit digit digit
elem-id ::= [teg] digit digit digit
digit ::= [0-9]

label-text ::= label-part*
label-part ::= label-char+ | "(" label-inner ")"
label-inner ::= [^()"\\]*
label-char ::= [^()"\\]
'''