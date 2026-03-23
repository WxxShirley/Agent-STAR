MODEL=${1:-"google/gemini-3-pro-preview"} # default model is Gemini-3-Pro
SUFFIX=${2:-"0210"}                       # default suffix is the current date
SPLIT=${3:-"validation"}                  # default split is validation

# set temperature: if MODEL contains "kimi", use 1.0, else 0.6
if [[ "$MODEL" == *kimi* ]]; then
  TEMPERATURE=1.0
else
  TEMPERATURE=0.6
fi

cd /PATH/TO/Inference

BASE_MODEL_NAME=$(basename "$MODEL")
LOG_FILE="logs/20260210_SOTA_Model/${BASE_MODEL_NAME}_${SPLIT}_${SUFFIX}.log"
SCORE_FILE="logs/20260210_SOTA_Model/${BASE_MODEL_NAME}_${SPLIT}_${SUFFIX}_score.log"

mkdir -p "logs/20260210_SOTA_Model"

# infernece
python3 -u main.py \
        --model "$MODEL" \
        --save_suffix "$SUFFIX" \
        --max_workers 20 \
        --use_custom_server \
        --max_context 131072 \
        --max_turns 100 \
        --temperature "$TEMPERATURE" \
        --top_p 0.95 \
        --split "$SPLIT" >> "$LOG_FILE" 2>&1

# post-process
python3 -u post_process.py \
        --path "output/${BASE_MODEL_NAME}_${SPLIT}_${SUFFIX}/predictions.jsonl" \
        --format_model deepseek-chat \
        --split "$SPLIT"

# score
if [ "$SPLIT" = "validation" ]; then
  python3 -u eval.py \
    --path "output/${BASE_MODEL_NAME}_${SPLIT}_${SUFFIX}/predictions_deepseek-chat_formatted.jsonl" \
    --save_score >> "$SCORE_FILE" 2>&1
fi
