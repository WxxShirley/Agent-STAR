MODEL_PATH=${1:-"/PATH/TO/MODEL"}
VLLM_PORT=${2:-8001}
SUFFIX=${3:-"TESTSET"}
timeout=${timeout:-1200}
sleep_interval=${sleep_interval:-60}


BASE_MODEL_NAME=$(basename $MODEL_PATH)
echo "Using model path: $MODEL_PATH"
echo ""

# Create log directory if it doesn't exist
LOG_DIR="/PATH/TO/.vllm_cache/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/vllm_server_${VLLM_PORT}.log"

echo "Starting vLLM server on port $VLLM_PORT..."
echo "Log file: $LOG_FILE"

CUDA_VISIBLE_DEVICES=0 vllm serve "$MODEL_PATH" \
    --host 0.0.0.0 \
    --port $VLLM_PORT \
    --tensor-parallel-size 1 \
    --gpu-memory-utilization 0.7 \
    --max-model-len 32768 > "$LOG_FILE" 2>&1 &
VLLM_PID=$!

# Wait a moment and check if process is still running
sleep 2
if ! ps -p $VLLM_PID > /dev/null 2>&1; then
    echo "ERROR: vLLM process failed to start!"
    echo "Last 50 lines of log:"
    tail -50 "$LOG_FILE" 2>/dev/null || echo "Log file is empty or doesn't exist"
    exit 1
fi

echo "vLLM server started with PID: $VLLM_PID" 
trap 'echo "Stopping vLLM ($VLLM_PID)"; kill $VLLM_PID 2>/dev/null' EXIT

check_port() {
    local port=$1
    local model_name=$2
    local start_time=$(date +%s)
    
    echo "Wait for $port ($model_name) to start..."
    while true; do
        # Check if port is listening
        if (netstat -tuln 2>/dev/null | grep -q ":$port ") || (ss -tuln 2>/dev/null | grep -q ":$port "); then
            # Try to connect via HTTP
            if curl -s --connect-timeout 5 --max-time 5 "http://localhost:$port/" > /dev/null 2>&1 || \
               curl -s --connect-timeout 5 --max-time 5 "http://localhost:$port/health" > /dev/null 2>&1 || \
               curl -s --connect-timeout 5 --max-time 5 "http://localhost:$port/v1" > /dev/null 2>&1; then
                echo "Port $port ($model_name) is ready."
                return 0
            fi
        fi
    
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))
        if [ $elapsed -gt $timeout ]; then
            echo "Error: start port $port ($model_name) timeout ($timeout seconds)!"
            return 1
        fi
        echo "Port $port ($model_name) is not started, waiting $sleep_interval seconds to retry... (elapsed ${elapsed} seconds)"
        sleep $sleep_interval
    done
}

check_port $VLLM_PORT "Eval Model" || exit 1 

echo "Starting inference..."

cd /PATH/TO/Inference

python3 -u main.py --model $MODEL_PATH --save_suffix $SUFFIX --max_workers 64 --split test --server_url http://localhost:$VLLM_PORT/v1 --max_context 32768 >>logs/testset/$BASE_MODEL_NAME+$SUFFIX.log 

# post-process 
python3 -u post_process.py --path output/${BASE_MODEL_NAME}_test_${SUFFIX}/predictions.jsonl --format_model deepseek-chat --split test 
