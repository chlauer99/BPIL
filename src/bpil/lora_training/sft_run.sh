#!/bin/bash

FORCE_TORCHRUN=1 llamafactory-cli train sft_config.yaml

llamafactory-cli export \
    --model_name_or_path <original_hf_model_name> \
    --adapter_name_or_path <path_of_lora> \
    --template <template_for_model> \
    --finetuning_type lora \
    --export_dir Training/<model_name>/sft-merged \
    --export_size 2 \
    --export_legacy_format False