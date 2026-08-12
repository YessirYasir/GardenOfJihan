# Local meaning model

Garden of Jihan uses `intfloat/multilingual-e5-small` only for an optional local candidate-reranking pass.

- Model card: <https://huggingface.co/intfloat/multilingual-e5-small>
- License: MIT
- Runtime: FastEmbed with CPU-only ONNX Runtime and the upstream `model_O4.onnx` artifact
- Pinned revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- Integrity: every required tokenizer/config file and the ONNX model have pinned SHA-256 values in `analysis/semantics.py`
- Cache: the user's Garden of Jihan application-data directory, never this repository
- Network behavior: downloaded on first use, then reused locally

No model weights, downloaded snapshots, or cache files belong in Git. The model maps transcript segments to dense vectors; Garden of Jihan uses relative within-video topic coherence and similarity, not an unsupported universal “virality” probability. If model import, download, or inference fails, the application reports a base-ranking fallback and does not call a cloud or paid API.

The upstream model supports the XLM-R multilingual language set and warns that low-resource languages can perform worse. Somali ranking therefore remains subject to the licensed, dialect-aware evaluation gate in [`../data/somali/README.md`](../data/somali/README.md). Qur’an mode does not use the semantic reranker.
