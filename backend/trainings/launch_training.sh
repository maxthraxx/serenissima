#!/bin/bash
# Script optimisé pour lancer le fine-tuning du modèle de conscience marchande

# Configuration GPU
export CUDA_VISIBLE_DEVICES=0
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128

# Créer un répertoire de logs
LOGS_DIR="./logs"
mkdir -p "$LOGS_DIR"
LOG_FILE="$LOGS_DIR/training_$(date +%Y%m%d_%H%M%S).log"

echo "Démarrage du fine-tuning. Les logs seront enregistrés dans $LOG_FILE"

# Générer d'abord le dataset JSONL
echo "Génération du dataset JSONL pour le fine-tuning..."
python3 prepareDataset.py --jsonl-only

# Paramètres optimisés pour le modèle DeepSeek-R1
python3 finetuneModel.py \
    --epochs 3 \
    --batch_size 1 \
    --gradient_accumulation_steps 4 \
    --output_dir "./merchant-consciousness-v2" \
    --learning_rate 2e-6 \
    --weight_decay 0.01 \
    --warmup_steps 100 \
    --save_steps 500 \
    --no-fp16 \
    --no-int8 \
    2>&1 | tee "$LOG_FILE"

# Vérifier si l'exécution a réussi
if [ $? -eq 0 ]; then
    echo "Fine-tuning terminé avec succès!"
else
    echo "Erreur lors du fine-tuning. Consultez les logs pour plus de détails."
    exit 1
fi
