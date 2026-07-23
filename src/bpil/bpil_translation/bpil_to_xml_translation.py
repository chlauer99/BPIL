import xml.etree.ElementTree as ET
import re
import random
from json import loads

from BPIL.translation_definition import meta_model_to_xml as mm_to_xml


class TranslationBpilToXml:
    def __init__(self):
        self.collaborations = {}
        self.pools = {}
        self.lanes = {}
        self.nodes = {}
        self.sequence_flows = {}
        self.message_flows = {}
        self.random_ids = []
        self.cur_colaboration = None

    def translate_bpil_to_xml(self, bpil_string):
        #bpil_string = bpil_string.replace("\\", "")#.replace("'", '"')
        #grammer_check = BPILGrammarChecker()
        #bpil = grammer_check.check_and_fix_bpil(bpil_string)
        #print("gammer checked")
        #print(bpil)
        bpil = loads(bpil_string)
        self.parse_bpil(bpil)

        if not self.pools:
            return self.generate_xml_without_collaboration()
        else:
            return self.generate_xml_with_collaboration()

    def parse_bpil(self, bpil):
        self.cur_colaboration = bpil["id"]
        self.collaborations[bpil["id"]] = {"pools": [], "s_flows": [], "m_flows": []}

        for pool_string in bpil.get("pools", []):
            pool_id, pool_label = self.extract_id_and_label(pool_string)
            self.pools[pool_id] = {
                "id": pool_id,
                "label": pool_label,
                "lanes": [],
                "s_flows": [],
                "m_flows": [],
                "processRef": f"process_{self.get_random_id()}",
                "parent": self.cur_colaboration,
            }
            self.collaborations[bpil["id"]]["pools"].append(pool_id)

        for pool_id, lanes in bpil.get("lanes", {}).items():
            for lane_string in lanes:
                lane_id, lane_label = self.extract_id_and_label(lane_string)
                self.pools[pool_id]["lanes"].append(lane_id)
                self.lanes[lane_id] = {
                    "id": lane_id,
                    "name": lane_label,
                    "elements": [],
                    "s_flows": [],
                    "m_flows": [],
                    "parent": pool_id,
                }

        for flow in bpil.get("flows", []):
            if "->" not in flow or flow.endswith("->"):
                continue
            self.parse_flow(flow)

    def parse_flow(self, flow_string):

        def get_flow_object_definition(node_str):
            """
            Fixes some syntax mistakes and returns the flow object definition and the ID of the lane the flow object is in
            Parameters
            ----------
            node_str

            Returns
            -------
            laneID/poolID
            flow object definition
            """

            #only count/split dots in prefix, not inside labels
            paren_pos = node_str.find("(")
            prefix = node_str[:paren_pos] if paren_pos != -1 else node_str
            label_suffix = node_str[paren_pos:] if paren_pos != -1 else ""

            if prefix.count(".") > 1:
                node_str_new = prefix.split(".")
                node_str_new[-1] += label_suffix
                # case that pools is also defined: p123.l123.t354....
                if not node_str_new[-1].startswith("g") or not node_str_new[-1].startswith("e") or not node_str_new[-1].startswith("t")\
                    and node_str_new[-2].startswith("p") or node_str_new[-2].startswith("l"):
                    return node_str_new[-2], node_str_new[-1]

                # case with syntax mistake: l123.e123.xor(label)
                elif node_str_new[-1].startswith("g") or node_str_new[-1].startswith("e") or node_str_new[-1].startswith("t")\
                    and node_str_new[-2].startswith("p") or node_str_new[-2].startswith("l"):
                    return node_str_new[-3], f"{node_str_new[-2]}:{node_str_new[-1]}"

            elif prefix.count(".") == 1:
                # usual case
                if node_str.startswith("p") or node_str.startswith("l"):
                    return node_str.split(".", 1) if "." in node_str else ("", node_str)
                # no lane is mentioned and syntax mist
                else:
                    return None, node_str.replace(".", ":")
            # lane or pool not mentioned
            else:
                return None, node_str

        def get_flow_parts(flow_string):

            s_match = re.match(r"(.+?)\s*--(\(.*?\))?->\s*(.+)", flow_string, re.DOTALL)
            m_match = re.match(r"(.+?)\s*\.\.(\(.*?\))?->\s*(.+)", flow_string, re.DOTALL)

            if not s_match and not m_match:
                # try wider match -> can lead to issues
                s_match = re.search(r'(.*?)\s*--(.*?)-?>\s*(.+)', flow_string, re.DOTALL)
                m_match = re.search(r'(.*?)\s*\.\.(.*?)-?>\s*(.+)', flow_string, re.DOTALL)

            if s_match:
                source_full, label, target_full = s_match.groups()
                flow_type = "s_flows"
            elif m_match:
                source_full, label, target_full = m_match.groups()
                flow_type = "m_flows"
            else:
                raise ValueError(f"Invalid flow format: {flow_string}")

            if label and not label[0].isalnum():
                label = label[1:]

            if label and not label[-1].isalnum():
                label = label[:-1]

            return source_full, target_full, flow_type, label
        #print("___________________")
        #print(flow_string)
        source_full, target_full, flow_type, label = get_flow_parts(flow_string)
        if not source_full:
            return
        #source_lane, source = source_full.split(".", 1) if "." in source_full else ("", source_full)
        #target_lane, target = target_full.split(".", 1) if "." in target_full else ("", target_full)
        source_lane, source = get_flow_object_definition(source_full)
        target_lane, target = get_flow_object_definition(target_full)
        #print(flow_string, source_full, target_full, flow_type, label)
        _, _, source_id, _ = self.get_element_attributes(source)
        _, _, target_id, _ = self.get_element_attributes(target)

        flow_id = f"{'SequenceFlow' if flow_type == 's_flows' else 'mf'}_{self.get_random_id()}"
        flow_obj = {"source": source_id, "target": target_id, "name": (label or "").strip("[]"), "collaboration": self.cur_colaboration}

        if flow_type == "s_flows":
            self.sequence_flows[flow_id] = flow_obj
        else:
            self.message_flows[flow_id] = flow_obj

        if source_lane in self.lanes:
            self.lanes[source_lane][flow_type].append(flow_id)
            if source_id not in self.lanes[source_lane]["elements"]:
                self.lanes[source_lane]["elements"].extend([source_id])
        elif source_lane in self.pools and flow_id not in self.pools[source_lane][flow_type]:
            pool_lanes = self.pools[source_lane]["lanes"]
            if len(pool_lanes) == 1:
                #single lane pool: forward element + flow to the only lane
                single_lane = pool_lanes[0]
                self.lanes[single_lane][flow_type].append(flow_id)
                if source_id not in self.lanes[single_lane]["elements"]:
                    self.lanes[single_lane]["elements"].append(source_id)
            else:
                self.pools[source_lane][flow_type].append(flow_id)

        if target_lane in self.lanes and target_id not in self.lanes[target_lane]["elements"]:
            #self.lanes[target_lane][flow_type].append(flow_id)
            self.lanes[target_lane]["elements"].extend([target_id])
        elif target_lane in self.pools and flow_id not in self.pools[target_lane][flow_type]:
            pool_lanes = self.pools[target_lane]["lanes"]
            if len(pool_lanes) == 1:
                #check above
                single_lane = pool_lanes[0]
                if target_id not in self.lanes[single_lane]["elements"]:
                    self.lanes[single_lane]["elements"].append(target_id)
            else:
                self.pools[target_lane][flow_type].append(flow_id)

    def extract_id_and_label(self, element_str):
        match = re.match(r"([a-z]\d+)\(((?:[^()]*|\([^()]*\))*)\)", element_str, re.DOTALL)
        if not match:
            # no numbers but words used as ID
            match = re.match(r"([a-zA-Z]*?)\(((?:[^()]*|\([^()]*\))*)\)", element_str, re.DOTALL)
        return match.groups() if match else (element_str, "")

    def get_element_attributes(self, element):

        element = element.strip()

        if "(" not in element:
            if element.startswith("p") or element.startswith("l"):
                return None, None, element, None
            else:
                node = self.nodes[element]
                return node["el_group"], node["type"], element, node["label"]

        #label patternd defs for reusability in e, g, t this fixed "(Check weight (kg))"
        _label_re = r"((?:[^()]*|\([^()]*\))*)"
        # Event
        if element.startswith("e"):
            match = re.match(rf"([a-zA-Z]\d+):([^()]*?)\({_label_re}\)", element, re.DOTALL)
            if not match:
                raise ValueError(f"Invalid event format: {element}")
            el_id, type, label = match.groups()
            el_group = "event"


            if "_"  in type:
                type1, type2 = type.split("_")
                el_type = (mm_to_xml[type1], mm_to_xml[type2])
            else:
                type1 = type
                el_type = (mm_to_xml[type1], None)

        # Gateway
        elif element.startswith("g"):
            match = re.match(rf"([a-zA-Z]\d+):([a-zA-Z_]*?)\({_label_re}\)", element, re.DOTALL)
            if not match:
                raise ValueError(f"Invalid gateway format: {element}")
            el_id, el_type, label = match.groups()
            el_group = "gateway"
            el_type = mm_to_xml[el_type]
        # Task
        elif element.startswith("t"):
            match = re.match(rf"([a-zA-Z]\d+):([^()]*?)\({_label_re}\)", element, re.DOTALL)
            if not match:
                raise ValueError(f"Invalid task format: {element}")
            el_id, type, label = match.groups()
            if type and type != "" and type != "task":
                if type in mm_to_xml:
                    el_type = mm_to_xml[type]
                else:
                    el_type = "task"
            else:
                el_type = "task"
            el_group = "task"
        else:
            return None, None, None, None
            #raise ValueError(f"Invalid element format: {element}")

        if el_id in self.nodes:
            return self.nodes[el_id]["el_group"], self.nodes[el_id]["type"], self.nodes[el_id]["id"], self.nodes[el_id]["label"]

        if el_group in ["event", "task", "gateway"]:
            self.nodes[el_id] = {"id": el_id, "type": el_type, "label": label, "el_group": el_group}

        return el_group, el_type, el_id, label

    def get_random_id(self):
        rid = random.randint(1000, 9999)
        while rid in self.random_ids:
            rid = random.randint(1000, 9999)
        self.random_ids.append(rid)
        return rid

    # generate_xml_with_collaboration and generate_xml_without_collaboration are unchanged
    # so you can keep them as in your original file

    def generate_xml_with_collaboration(self):
        """
        Generates the xml file based on the analysed bpil
        :return: root of the element tree (xml is saved as element tree)
        """
        bpmn_namespace = "http://www.omg.org/spec/BPMN/20100524/MODEL"
        ET.register_namespace("bpmn", bpmn_namespace)
        bpmndi_namespace = "http://www.omg.org/spec/BPMN/20100524/DI"
        ET.register_namespace("bpmndi", bpmndi_namespace)
        omgdi_namespace = "http://www.omg.org/spec/DD/20100524/DI"
        ET.register_namespace("omgdi", omgdi_namespace)
        omgdc_namespace = "http://www.omg.org/spec/DD/20100524/DC"
        ET.register_namespace("omgdc", omgdc_namespace)
        xsi_namespace = "http://www.w3.org/2001/XMLSchema-instance"
        ET.register_namespace("xsi", xsi_namespace)
        root = ET.Element(f"{{{bpmn_namespace}}}definitions",
                          {"targetNamespace": "http://bpmn.io/schema/bpmn",
                           "typeLanguage": "http://www.w3.org/2001/XMLSchema"})

        node_incoming = {node: [] for node in self.nodes}
        node_outgoing = {node: [] for node in self.nodes}

        # add collabotrations
        for collaboration_id in self.collaborations:
            col_et = ET.SubElement(root, f"{{{bpmn_namespace}}}collaboration", attrib={"id": collaboration_id})
            self.collaborations[collaboration_id]["ET"] = col_et

        # add pools
        for pool_id in self.pools:
            pool_nodes = set()

            parent = self.collaborations[self.pools[pool_id]["parent"]]["ET"]
            attributes = {"id": pool_id, "processRef": self.pools[pool_id]["processRef"]}
            if "label" in self.pools[pool_id]:
                attributes["name"] = self.pools[pool_id]["label"]

            pool = ET.SubElement(parent, f"{{{bpmn_namespace}}}participant", attrib=attributes)
            self.pools[pool_id]["ET"] = pool

            process = ET.SubElement(root, f"{{{bpmn_namespace}}}process", attrib={"id": self.pools[pool_id]["processRef"]})
            # add lanes
            if self.pools[pool_id]["lanes"] != []:
                parent = ET.SubElement(process, f"{{{bpmn_namespace}}}laneSet")
                for lane_id in self.pools[pool_id]["lanes"]:
                    name = self.lanes[lane_id]["name"]
                    lane = ET.SubElement(parent, f"{{{bpmn_namespace}}}lane", attrib={"id": lane_id, "name": name})

                    # add flowNodeRefs per lane
                    for element in set(self.lanes[lane_id]["elements"]):
                        node = ET.SubElement(lane, f"{{{bpmn_namespace}}}flowNodeRef")
                        node.text = element

                    # add all sequence flows in this lane
                    for seq_flow_id in self.lanes[lane_id]["s_flows"]:
                        attributes = {"id": seq_flow_id, "name": self.sequence_flows[seq_flow_id]["name"],
                                      "sourceRef": self.sequence_flows[seq_flow_id]["source"],
                                      "targetRef": self.sequence_flows[seq_flow_id]["target"]}
                        ET.SubElement(process, f"{{{bpmn_namespace}}}sequenceFlow", attrib=attributes)
                        node_incoming[self.sequence_flows[seq_flow_id]["target"]].append(seq_flow_id)
                        node_outgoing[self.sequence_flows[seq_flow_id]["source"]].append(seq_flow_id)
                        pool_nodes.add(self.sequence_flows[seq_flow_id]["source"])
                        pool_nodes.add(self.sequence_flows[seq_flow_id]["target"])

            # add sequence flows between lanes / sequenceflows for pools without lanes
            for seq_flow_id in self.pools[pool_id]["s_flows"]:
                attributes = {"id": seq_flow_id, "name": self.sequence_flows[seq_flow_id]["name"],
                              "sourceRef": self.sequence_flows[seq_flow_id]["source"],
                              "targetRef": self.sequence_flows[seq_flow_id]["target"]}
                ET.SubElement(process, f"{{{bpmn_namespace}}}sequenceFlow", attrib=attributes)
                #print(seq_flow_id)
                #print(self.sequence_flows[seq_flow_id])
                node_incoming[self.sequence_flows[seq_flow_id]["target"]].append(seq_flow_id)
                node_outgoing[self.sequence_flows[seq_flow_id]["source"]].append(seq_flow_id)
                pool_nodes.add(self.sequence_flows[seq_flow_id]["source"])
                pool_nodes.add(self.sequence_flows[seq_flow_id]["target"])

            #also include message-flow-only nodes that belong to this pool lanes
            for lane_id in self.pools[pool_id]["lanes"]:
                for elem_id in self.lanes[lane_id]["elements"]:
                    if elem_id in self.nodes:
                        pool_nodes.add(elem_id)

            # add flownode definitions per process (attributes, incoming & outgoing)
            for node in pool_nodes:
                type = self.nodes[node]["type"]
                if isinstance(self.nodes[node]["type"], tuple):
                    node_et = ET.SubElement(process, f"{{{bpmn_namespace}}}{type[0]}",
                                            attrib={"id": node, "name": self.nodes[node]["label"]})
                    #if type[1] and type[1] != "":
                    #    type_2_def = ET.SubElement(node_et, f"{{{bpmn_namespace}}}{type[1]}")
                else:
                    node_et = ET.SubElement(process, f"{{{bpmn_namespace}}}{type}", attrib={"id": node, "name": self.nodes[node]["label"]})
                if node in node_incoming:
                    for in_sf in node_incoming[node]:
                        node_sf = ET.SubElement(node_et, f"{{{bpmn_namespace}}}incoming")
                        node_sf.text = in_sf

                if node in node_outgoing:
                    for out_sf in node_outgoing[node]:
                        node_sf = ET.SubElement(node_et, f"{{{bpmn_namespace}}}outgoing")
                        node_sf.text = out_sf
                if isinstance(self.nodes[node]["type"], tuple) and type[1] and type[1] != "":
                    type_2_def = ET.SubElement(node_et, f"{{{bpmn_namespace}}}{type[1]}")

        # add message flows
        for message_flow_id in self.message_flows:
            parent = self.collaborations[self.message_flows[message_flow_id]["collaboration"]]["ET"]
            attributes = {"id": message_flow_id, "sourceRef": self.message_flows[message_flow_id]["source"],
                          "targetRef": self.message_flows[message_flow_id]["target"]}

            ET.SubElement(parent, f"{{{bpmn_namespace}}}messageFlow", attrib=attributes)
        return root

    def generate_xml_without_collaboration(self):
        bpmn_namespace = "http://www.omg.org/spec/BPMN/20100524/MODEL"
        ET.register_namespace("bpmn", bpmn_namespace)
        bpmndi_namespace = "http://www.omg.org/spec/BPMN/20100524/DI"
        ET.register_namespace("bpmndi", bpmndi_namespace)
        omgdi_namespace = "http://www.omg.org/spec/DD/20100524/DI"
        ET.register_namespace("omgdi", omgdi_namespace)
        omgdc_namespace = "http://www.omg.org/spec/DD/20100524/DC"
        ET.register_namespace("omgdc", omgdc_namespace)
        xsi_namespace = "http://www.w3.org/2001/XMLSchema-instance"
        ET.register_namespace("xsi", xsi_namespace)
        root = ET.Element(f"{{{bpmn_namespace}}}definitions",
                          {"targetNamespace": "http://bpmn.io/schema/bpmn",
                           "typeLanguage": "http://www.w3.org/2001/XMLSchema"})

        process = ET.SubElement(root, f"{{{bpmn_namespace}}}process", attrib={"id": "process 1"})

        node_incoming = {node: [] for node in self.nodes}
        node_outgoing = {node: [] for node in self.nodes}

        for seq_flow_id in self.sequence_flows:
            attributes = {"id": seq_flow_id, "sourceRef": self.sequence_flows[seq_flow_id]["source"],
                          "targetRef": self.sequence_flows[seq_flow_id]["target"]}
            ET.SubElement(process, f"{{{bpmn_namespace}}}sequenceFlow", attrib=attributes)
            node_incoming[self.sequence_flows[seq_flow_id]["target"]].append(seq_flow_id)
            node_outgoing[self.sequence_flows[seq_flow_id]["source"]].append(seq_flow_id)

        for node in self.nodes:
            type = self.nodes[node]["type"]
            if isinstance(self.nodes[node]["type"], tuple):
                node_et = ET.SubElement(process, f"{{{bpmn_namespace}}}{type[0]}",
                                        attrib={"id": node, "name": self.nodes[node]["label"]})
                if type[1] and type[1] != "":
                    type_2_def = ET.SubElement(node_et, f"{{{bpmn_namespace}}}{type[1]}")
            else:
                node_et = ET.SubElement(process, f"{{{bpmn_namespace}}}{type}",
                                        attrib={"id": node, "name": self.nodes[node]["label"]})
            if node in node_incoming:
                for in_sf in node_incoming[node]:
                    node_sf = ET.SubElement(node_et, f"{{{bpmn_namespace}}}incoming")
                    node_sf.text = in_sf

            if node in node_outgoing:
                for out_sf in node_outgoing[node]:
                    node_sf = ET.SubElement(node_et, f"{{{bpmn_namespace}}}outgoing")
                    node_sf.text = out_sf

        for message_flow_id in self.message_flows:
            attributes = {"id": message_flow_id, "sourceRef": self.message_flows[message_flow_id]["source"],
                          "targetRef": self.message_flows[message_flow_id]["target"]}
            ET.SubElement(process, f"{{{bpmn_namespace}}}messageFlow", attrib=attributes)


        return root