from enum import Enum


meta_model_to_xml =  {
    # events
    "start": "startEvent",
    "end": "endEvent",
    "icatch": "intermediateCatchEvent",
    "ithrow":  "intermediateThrowEvent",
    "m": "messageEventDefinition",
    "t": "timerEventDefinition",
    "e": "errorEventDefinition",
    # gateways
    "event": "eventBasedGateway",
    "xor": "exclusiveGateway",
    "or": "inclusiveGateway",
    "and": "parallelGateway",
    # tasks
    "u": "userTask",
    "se": "serviceTask",
    "b": "businessRuleTask",
    "sc": "scriptTask",
    "task": "task",
    "": ""
}


xml_to_meta_model = {
    "startEvent": "start",
    "endEvent": "end",
    "intermediateCatchEvent": "icatch",
    "intermediateThrowEvent": "ithrow",
    "messageEventDefinition": "m",
    "timerEventDefinition": "t",
    "errorEventDefinition": "e",
    "eventBasedGateway": "event",
    "exclusiveGateway": "xor",
    "inclusiveGateway": "or",
    "parallelGateway": "and",
    "userTask": "u",
    "serviceTask": "se",
    "businessRuleTask": "b",
    "scriptTask": "sc",
    "task": "task",
    "": ""
}


event_definitions = ["messageEventDefinition", "timerEventDefinition", "errorEventDefinition"]