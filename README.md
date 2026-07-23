# BPIL: A Compact Intermediate Representation for LLM-Based Generation of BPMN Process Models

This repository contains the implementation and reproducibility material accompanying the paper:

> **BPIL: A Compact Intermediate Representation for LLM-Based Generation of BPMN Process Models**

## Overview

Business Process Intermediate Language (BPIL) is a compact, JSON-based intermediate representation for BPMN collaboration models. It was designed specifically for Large Language Model (LLM)-based process model generation, reducing the verbosity of BPMN 2.0 XML while preserving deterministic translation into standard BPMN models.

Compared to BPMN XML, BPIL replaces verbose XML tags with a concise symbolic syntax, removes layout information, and introduces a structured representation that is easier for LLMs to generate while remaining fully translatable to BPMN 2.0 XML.

The paper investigates whether using BPIL instead of BPMN XML improves the generation of valid process models by LLMs and evaluates the effect of supervised fine-tuning on the proposed representation.

---

## Repository Structure

### `src/`

Contains the implementation of the BPIL framework, including:

- BPIL parser
- BPIL ↔ BPMN translation
- training pipeline for fine-tuning LLMs on BPIL
- scripts for generating BPIL datasets as extension for BEF4LLM  

---

### `statistical_tests/`

Contains the statistical analyses reported in the paper, including:

- validity analyses
- paired statistical tests
- confidence interval calculations
- generation of result tables and figures

---

## Evaluation Framework

The evaluation framework used to assess syntactic, semantic, pragmatic quality and validity is **not included in this repository**.

It is available separately in the **BEF4LLM** repository (https://gitlab-iwi.dfki.de/lauer/bef4llm.git), which contains the complete benchmarking framework used in the experiments reported in the paper. 

