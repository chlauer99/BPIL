import json
import re
import time
import os
from tqdm import tqdm
import concurrent.futures
from ftfy import fix_text

from bpil.bpil_generation.bpil_system_prompt import bpil_json_v3_system_prompt, bpil_json_v3_demostration_prompt, bpil_empty, modeling_prompt_bpil
from bpil.bpil_generation.llm_connection.connect_llms_ollama import ConnectLLMsOllama
from bpil.bpil_generation.llm_connection.connect_llms_vllm import ConnectLLMsVLLM
from bpil.bpil_translation.bpil_to_xml_translation import TranslationBpilToXml
import xml.etree.ElementTree as ET


class Benchmark_BPIL_VLLM():
    """
    Class for generateing BPIL files with VLLM based in given Datasets
    """
    def __init__(self, dataset, llm:str, sys_msg=None, grammar=None, refinement=0):

        self.text_model_pairs = dataset
        self.syntax_scores = []
        self.pragmatic_scores = []
        self.semantic_scores = []
        self.sys_msg = sys_msg
        self.llm_model = llm
        self.llm = None
        self.grammar = grammar
        self.modeling_time = []
        self.current_lang = "english"
        self.refinement = refinement
        print("Refinement: ", refinement)
        if not self.sys_msg:
            self.sys_msg = bpil_json_v3_system_prompt + bpil_json_v3_demostration_prompt
        self.init_llm(self.sys_msg)

        self.response_schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "pools": {"type": "array", "items": {"type": "string"}},
                "lanes": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "flows": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["id", "pools", "lanes", "flows"]
        }

    async def model_processes(self, target_dir, prompt_order=None):
        """
        Here for each text-model pair in the dataset a coresponding process model is modeled by the LLM

        Parameters
        ----------
        target_dir : str
            directory, where to BPMN is saved to

        Returns:
        -------
        not_modelled: list
            list of BPMN names, that are not modelled (e.g. due to timeout)
        """
        import time
        # validation check mit einem Loop
        not_modelled = []
        if not os.path.isdir(target_dir):
            os.makedirs(target_dir)

        messages = []
        system_prompt = None
        for pair in tqdm(self.text_model_pairs):
            if not os.path.isfile(f"{target_dir}/{pair}.bpmn"):
                lang, text, r_models = self.text_model_pairs[pair]
                system_prompt, message = self.create_modeling_prompt(pair, text, prompt_order=prompt_order)
                messages.append(message)

        self.llm = ConnectLLMsVLLM(llm_modell=self.llm_model, sys_msg=system_prompt, grammar=self.grammar)
        start_time = time.perf_counter()
        responses = await self.chat_with_timeout(messages)
        end_time = time.perf_counter()
        self.modeling_time.append(end_time - start_time)

        with open(f"{target_dir}/modeling_times.txt", 'w') as f:
            f.write(str(self.modeling_time))


        await self.validate_process_model_responses(responses, target_dir)

        return [] #return an empty list, for compatibility with benchmarking_llms.py

    async def validate_process_model_responses(self, responses, target_dir):
        if not os.path.isdir(f"{target_dir}/bpil"):
            os.makedirs(f"{target_dir}/bpil")

        if not os.path.isdir(f"{target_dir}/refinement/bpil/"):
            os.makedirs(f"{target_dir}/refinement/bpil/")

        bpil_dict = {pair: response for pair, response in responses}
        refined_bpils = {}

        start_time = time.perf_counter()
        end_time = time.perf_counter()
        with open(f"{target_dir}/refinement_times.txt", "w") as f:
            f.write(str(end_time-start_time))

        not_valid_bpils = []
        for pair in bpil_dict:
            bpil = bpil_dict[pair] if pair not in refined_bpils else refined_bpils[pair]

            # write refined bpil for analyse
            with open(f"{target_dir}/bpil/{pair}.bpil", 'w') as f:
                f.write(bpil)

            # translate bpil for xml, if translation fails and refinement should be done, refinement is done
            try:
                xml_string = self.translate_bpil_to_xml(bpil)
            except Exception as e:
                xml_string = ""
            with open(f"{target_dir}/{pair}.bpmn", 'w') as f:
                f.write(xml_string)




    def translate_bpil_to_xml(self, bpil):
        """
        Translate BPIL to XML, if error occurs in translation, "" is returned.-
        Parameters
        ----------
        bpil: str
            bpil to translate

        Returns
        -------
        XML string if translation was successful, else ""
        """
        try:
            xml_trans = TranslationBpilToXml()
            #this idea originated from parse the response to
            #extract the bpmn field (response has {bpmn:{...}, response:...} wrapper)
            try:
                parsed = json.loads(bpil)
                if "bpmn" in parsed:
                    bpil_obj = parsed["bpmn"]
                    bpil_for_translation = json.dumps(bpil_obj) if isinstance(bpil_obj, dict) else str(bpil_obj)
                else:
                    bpil_for_translation = bpil  #no wrapper, use as-is
            except json.JSONDecodeError:
                bpil_for_translation = bpil  #not valid JSON, use as-is
            xml = xml_trans.translate_bpil_to_xml(bpil_for_translation)
            xml_string = ET.tostring(xml, encoding="utf-8", xml_declaration=True).decode()
            return xml_string

        except Exception as e:
            print("BPIL not translated: ", e)
            return ""


    def create_modeling_prompt(self, pair, text, prompt_order=None):
        """
        Actual interaction with the llm. To ensure the xml is valid, a validation loop is added
        If the xml is still not valid after an second try a empty file is saved.
        Each process model is saved in a file in the target directory.

        Parameters
        ----------
        text: str
            textual description of the BPMN
        pair: str
            name of the text-model pair
        target_dir: str
            directory, where to BPMN is saved to

        Returns:
        -------
        not_modelled: list
            list of BPMN names, that are not modelled (e.g. due to timeout)
        """
        # adapt prompt here, gives possibility to check if position of demonstration makes difference
        if prompt_order == "ssp":
            prompt = json.dumps({"bpmn": bpil_empty, "request": modeling_prompt_bpil + text})
            self.change_sys_msg((bpil_json_v3_demostration_prompt + bpil_json_v3_system_prompt).strip())
        elif prompt_order == "esp":
            prompt = json.dumps({"bpmn": bpil_empty, "request": modeling_prompt_bpil + text})
            self.change_sys_msg((bpil_json_v3_system_prompt + bpil_json_v3_demostration_prompt).strip())
        elif prompt_order == "sum":
            prompt = json.dumps({"bpmn": bpil_empty, "request": bpil_json_v3_demostration_prompt + modeling_prompt_bpil + text})
            self.change_sys_msg((bpil_json_v3_system_prompt).strip())
        elif prompt_order == "eum":
            prompt = json.dumps({"bpmn": bpil_empty,
                                 "request": modeling_prompt_bpil + text + bpil_json_v3_demostration_prompt})
            self.change_sys_msg((bpil_json_v3_system_prompt).strip())
        else:
            #prompt = json.dumps({"bpmn": bpil_empty, "request": modeling_prompt_bpil + text})
            prompt = json.dumps(modeling_prompt_bpil + text)
            self.change_sys_msg((bpil_json_v3_system_prompt).strip() + bpil_json_v3_demostration_prompt)

        message = [
            {"role": "system", "content": self.sys_msg},
            {"role": "user", "content": prompt}
        ]

        #return "abc", [{"role": "user", "content": "Generie random text. Er soll 300 Wörter haben"}]
        return self.sys_msg, (pair, message)

    def change_sys_msg(self, prompt, timeout=300):
        """
        Allows to adapt the language of the system message

        Parameters
        ----------
        lang: Language
            indicates the language of the system message
        """
        self.sys_msg = prompt  # + "\\no_think" disable thinking mode

        if not self.llm:
            self.llm = ConnectLLMsOllama(llm_modell=self.llm_model, sys_msg=self.sys_msg, timeout=timeout)
        else:
            self.llm.init_sys_role(self.sys_msg)


    def parse_response(self, response):
        # print("Response: \n", response)
        successful = False
        bpil_code = text_response = ""

        # Extract XML content from the response using regex.
        bpil_search = re.search(r'"bpmn":\s* ([\s\S]*),\s*"response"', response)
        text_response_search = re.search(r'"response": "([\s\S]*)"', response)

        if bpil_search:
            bpil_code = bpil_search.group(1)  # Retrieve XML content.

        if text_response_search:
            text_response = text_response_search.group(1)  # Retrieve text response.

        # If either XML or text response is missing, log the failure.
        if bpil_code == "" or text_response == "":
            print("_" * 50, "\nParse not successful:\n", response, "\n", "_" * 50)
            # if xml_code == "":
            #     text_response = "It looks like the generated BPMN XML couldn't be parsed correctly. You might want to try a different prompt or rephrase your request for better results."

        else:
            successful = True  # Mark parsing as successful if both values are extracted.

        xml_code = fix_text(bpil_code)
        # print("Text Response: ", text_response)
        # print("XML Code: ", xml_code)

        return successful, xml_code

    def init_llm(self, sys_msg, timeout=300):
        """
        Allows to change the system message e.g. if the language is switched
        """
        #if lang == Language.ENGLISH:
        #    self.sys_msg = sys_msg # + "\\no_think" disable thinking mode
        #elif lang == Language.GERMAN:
        #    raise Exception("Language is not implemented yet")

        self.sys_msg = sys_msg
        if not self.llm:
            self.llm = ConnectLLMsVLLM(llm_modell=self.llm_model, sys_msg=self.sys_msg, timeout=timeout, grammar=self.grammar)
        else:
            self.llm.init_sys_role(sys_msg)
        #self.current_lang = lang

    def chat_with_timeout(self, messages):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            try:
                response = self.llm.chat_without_history(messages, format=None)
                return response
            except TimeoutError:
                return None
            # catch possible exceptions
            except Exception as e:
                print(e)
                return None



class Benchmark_BPIL():
    """
    Modelling instance of an LLM for the benchmark
    """
    def __init__(self, dataset, llm:str, sys_msg=None):

        self.text_model_pairs = dataset
        self.syntax_scores = []
        self.pragmatic_scores = []
        self.semantic_scores = []
        self.sys_msg = sys_msg
        self.llm_model = llm
        self.llm = None
        self.modeling_time = []
        #self.current_lang = list(self.text_model_pairs.values())[0][0]
        self.current_lang = "english"
        if not self.sys_msg:
            self.sys_msg = bpil_json_v3_system_prompt + bpil_json_v3_demostration_prompt
        self.init_llm(self.sys_msg)

        #self.response_schema = {
        #    "type": "object",
        #    "properties": {
        #        "bpmn": {"type": "string"},
        #        "response": {"type": "string"}
        #    },
        #    "required": ["bpmn", "response"]
        #}

        self.response_schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "pools": {"type": "array", "items": {"type": "string"}},
                "lanes": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "flows": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["id", "pools", "lanes", "flows"]
        }

    def model_processes(self, target_dir):
        """
        Here for each task in the dataset a coresponding process model is modeled by the LLM
        """
        # validation check mit einem Loop
        not_modelled = []
        not_valid_first_time = []
        if not os.path.isdir(target_dir):
            os.makedirs(target_dir)

        if not os.path.isdir(f"{target_dir}/bpil"):
            os.makedirs(f"{target_dir}/bpil")

        for pair in tqdm(self.text_model_pairs):
            if not os.path.isfile(f"{target_dir}/{pair}.bpmn"):
                # check if system message is in right language
                lang, text, r_models = self.text_model_pairs[pair]
                #if self.current_lang != lang:
                    #self.change_sys_msg(lang)
                model_succ, valid_first_time = self.llm_modelling(text, pair, target_dir)

                if not model_succ:
                    not_modelled.append(pair)

                if not valid_first_time:
                    not_valid_first_time.append(pair)

        with open(f"{target_dir}/modeling_times.txt", "w") as f:
            f.write(str(self.modeling_time))

        return not_modelled, not_valid_first_time


    def llm_modelling(self, text, pair, target_dir):
        """
        Actual interaction with the llm. To ensure the xml is valid, a validation loop is added
        If the xml is still not valid after an second try a empty file is saved.
        Each process model is saved in a file in the target directory.

        """
        # adapt prompt here
        #prompt = (modeling_prompt + text).strip()
        #prompt = json.dumps({"bpmn": bpil_empty, "request": modeling_prompt_bpil + text})
        prompt = modeling_prompt_bpil + text
        start_time = time.perf_counter()
        response = self.chat_with_timeout(prompt=prompt)
        end_time = time.perf_counter()
        self.modeling_time.append(end_time - start_time)

        if not response:
            print(f"No process is modelled due to timeout: Model = {pair}")
            return False, False

        try:
            successful, bpil = self.parse_response(response)
        except Exception as e:
            print("response not parsed: ", e)
            successful = False
            bpil = ""

        if successful:
            # save bpil
            with open(f"{target_dir}/bpil/{pair}.bpil", 'w') as f:
                f.write(bpil)
            # translate tp xml & save
            try:
                xml_trans = TranslationBpilToXml()
                xml = xml_trans.translate_bpil_to_xml(bpil)
                xml_string = ET.tostring(xml, encoding="utf-8", xml_declaration=True).decode()
            except Exception as e:
                print("BPIL not translated: ", e)
                xml_string = ""
            #save whole response
            with open(f"{target_dir}/bpil/{pair}.json", 'w') as f:
                f.write(response)
        else:
            xml_string = ""
            # save whole response
            with open(f"{target_dir}/bpil/{pair}.json", 'w') as f:
                f.write(response)
        with open(f"{target_dir}/{pair}.bpmn", 'w') as f:
            f.write(xml_string)

        # ensures that each process model is modelled without interferences from previous modelling
        self.llm.reset_chat_history()

        return True, True

    def parse_response(self, response):
        # print("Response: \n", response)
        successful = False
        bpil_code = text_response = ""

        print(response)
        # Extract XML content from the response using regex.
        bpil_search = re.search(r'"bpmn":\s* ([\s\S]*),\s*"response"', response)
        text_response_search = re.search(r'"response": "([\s\S]*)"', response)

        if bpil_search:
            bpil_code = bpil_search.group(1)  # Retrieve XML content.

        if text_response_search:
            text_response = text_response_search.group(1)  # Retrieve text response.

        # If either XML or text response is missing, log the failure.
        if bpil_code == "" or text_response == "":
            print("_" * 50, "\nParse not successful:\n", response, "\n", "_" * 50)
            # if xml_code == "":
            #     text_response = "It looks like the generated BPMN XML couldn't be parsed correctly. You might want to try a different prompt or rephrase your request for better results."

        else:
            successful = True  # Mark parsing as successful if both values are extracted.

        xml_code = fix_text(bpil_code)
        # print("Text Response: ", text_response)
        # print("XML Code: ", xml_code)

        return successful, xml_code


    def init_llm(self, sys_msg, timeout=300):
        """
        Allows to change the system message e.g. if the language is switched
        """
        #if lang == Language.ENGLISH:
        #    self.sys_msg = sys_msg # + "\\no_think" disable thinking mode
        #elif lang == Language.GERMAN:
        #    raise Exception("Language is not implemented yet")

        self.sys_msg = sys_msg
        if not self.llm:
            self.llm = ConnectLLMsOllama(llm_modell=self.llm_model, sys_msg=self.sys_msg, timeout=timeout)
        else:
            self.llm.init_sys_role(sys_msg)
        #self.current_lang = lang

    def chat_with_timeout(self, prompt):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            try:
                response = self.llm.chat_with_history(role="user", content=prompt)
                return response
            except TimeoutError:
                return None
            # catch possible exceptions
            except Exception as e:
                print(e)
                return None

