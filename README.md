---
title: Risk Scanner BE App
emoji: 🚀
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
app_port: 7860
---

# Chạy lần đầu

python -m src.data_pipeline.full_ingest_neo4j
python scripts/import_embeddings_to_neo4j.py
python -m src.data_pipeline.legal_segment_index apply


python -m src.cross_reference.ingest_llm_relations


# Cách chạy code

## Bật 3 terminal 
uvicorn infra.api.app:app --port 8000 --log-level info

python -m uvicorn infra.embedding_service.app:app --host 0.0.0.0 --port 8080

cd frontend  
npm ci  #nếu chạy lần đầu  
npm run dev

