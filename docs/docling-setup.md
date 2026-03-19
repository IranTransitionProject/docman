# Docling Setup and Performance Tuning

Configuration guide for IBM Docling in the DocMan pipeline, tuned for Apple Silicon (M1 Pro 32GB RAM).

## Installation

Docling is installed as a dependency of DocMan:

```bash
# From the project root
uv sync --extra dev

# Or install Docling standalone
uv pip install "docling>=2.0.0"
```

This pulls in PyTorch, torchvision, and Docling's model dependencies. On Apple Silicon, PyTorch automatically includes MPS (Metal Performance Shaders) support.

### Verify installation

```python
import docling
print(docling.__version__)  # Should be >= 2.0.0

import torch
print(torch.backends.mps.is_available())  # Should be True on Apple Silicon
```

## Model downloads

Docling downloads detection models from HuggingFace on first use. Pre-download them to avoid delays during pipeline runs:

```bash
# Pre-download all default models
docling-tools models download

# Models are cached at:
#   ~/.cache/docling/models/
#
# Override with:
export DOCLING_CACHE_DIR="/path/to/custom/cache"
```

### Available layout detection models

| Model | Size | Accuracy | Speed | Recommended for |
|-------|------|----------|-------|-----------------|
| `DOCLING_LAYOUT_HERON` | Small | Good | Fast | Default, general use |
| `DOCLING_LAYOUT_EGRET_MEDIUM` | Medium | Better | Medium | Better accuracy needed |
| `DOCLING_LAYOUT_EGRET_LARGE` | Large | High | Slower | High-quality extraction |
| `DOCLING_LAYOUT_EGRET_XLARGE` | XLarge | Highest | Slowest | Maximum accuracy |

For M1 Pro 32GB, `HERON` (default) is the best balance. Use `EGRET_MEDIUM` if you need higher accuracy and can tolerate ~2x slower processing.

## Hardware acceleration (Apple Silicon)

### MPS (Metal Performance Shaders)

MPS offloads PyTorch operations to the Apple GPU. This significantly speeds up layout detection and table structure recognition.

```python
from docling.datamodel.accelerator_options import AcceleratorOptions

accel = AcceleratorOptions(
    device="mps",       # Use Apple GPU (auto-detected if available)
    num_threads=8,      # M1 Pro has 8 performance cores
)
```

**Environment variable alternative:**

```bash
export DOCLING_DEVICE=mps
export DOCLING_NUM_THREADS=8
```

### MLX models (Apple-native)

Docling supports MLX-optimized models that run natively on Apple Silicon without PyTorch overhead. These are used with the VLM (Vision-Language Model) pipeline:

- `SMOLDOCLING_MLX` — SmolDocling converted for MLX
- `GRANITE_DOCLING_MLX` — Granite Docling converted for MLX

MLX models require the `mlx` package:

```bash
uv pip install mlx mlx-lm
```

**Note:** MLX models are for the VLM pipeline (`VlmPipelineOptions`), not the standard PDF pipeline. They replace the traditional layout detection + OCR approach with a single vision-language model. This is experimental and may not match the accuracy of the standard pipeline for all document types.

## OCR configuration

### OcrMac (recommended for macOS)

OcrMac uses Apple's native Vision framework for OCR. It's fast, requires no additional model downloads, and handles most languages well.

```python
from docling.datamodel.pipeline_options import PdfPipelineOptions, OcrMacOptions

pipeline_options = PdfPipelineOptions(
    do_ocr=True,
    ocr_options=OcrMacOptions(
        recognition="accurate",    # "fast" or "accurate"
        framework="vision",        # Uses Apple Vision framework
    ),
)
```

### Other OCR engines

| Engine | Class | Notes |
|--------|-------|-------|
| EasyOCR | `EasyOcrOptions` | Good multilingual support, GPU-accelerated |
| Tesseract | `TesseractOcrOptions` | Classic, requires system install (`brew install tesseract`) |
| RapidOCR | `RapidOcrOptions` | Fast, lightweight |
| Tesserocr | `TesserOcrOptions` | Python binding for Tesseract |
| OcrMac | `OcrMacOptions` | macOS-native, no extra install needed |

For Apple Silicon, **OcrMac** is recommended unless you need specific language support that it doesn't cover.

## Pipeline configuration

### Standard PDF pipeline (recommended)

```python
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    AcceleratorOptions,
    OcrMacOptions,
    TableStructureOptions,
)
from docling.datamodel.base_models import InputFormat

# --- M1 Pro 32GB optimized settings ---
accel = AcceleratorOptions(
    device="mps",
    num_threads=8,
)

pipeline_options = PdfPipelineOptions(
    # Layout detection
    accelerator_options=accel,

    # OCR (macOS native)
    do_ocr=True,
    ocr_options=OcrMacOptions(recognition="accurate"),

    # Table structure recognition
    do_table_structure=True,
    table_structure_options=TableStructureOptions(
        do_cell_matching=True,
    ),

    # Batch sizes (tune based on available memory)
    # Higher = faster but more memory. M1 Pro 32GB can handle 4-8.
    layout_batch_size=4,
    ocr_batch_size=4,

    # Optional enrichment (disabled by default for speed)
    do_code_enrichment=False,
    do_formula_enrichment=False,
)

converter = DocumentConverter(
    allowed_formats=[InputFormat.PDF, InputFormat.DOCX],
    format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_options=pipeline_options,
        ),
    },
)

result = converter.convert("document.pdf")
text = result.document.export_to_markdown()
```

### Batch processing

For processing multiple documents:

```python
from docling.document_converter import DocumentConverter

converter = DocumentConverter(...)  # Same config as above

# Convert multiple files
input_paths = ["doc1.pdf", "doc2.pdf", "doc3.docx"]
results = converter.convert_all(input_paths)

for result in results:
    print(f"{result.input.file}: {len(result.document.pages)} pages")
```

## Performance tuning for M1 Pro 32GB

### Recommended settings

| Setting | Value | Rationale |
|---------|-------|-----------|
| `device` | `"mps"` | GPU acceleration via Metal |
| `num_threads` | `8` | M1 Pro has 8 performance cores |
| `layout_batch_size` | `4` | Balances speed and memory usage |
| `ocr_batch_size` | `4` | Same rationale |
| `do_ocr` | `True` | Enable for scanned PDFs |
| `ocr_engine` | `OcrMacOptions` | Native, fast, no extra install |
| `layout_model` | `HERON` (default) | Best speed/accuracy balance |
| `do_code_enrichment` | `False` | Disable unless needed (saves time) |
| `do_formula_enrichment` | `False` | Disable unless needed |

### Memory considerations

- **Default models (Heron):** ~2GB VRAM, fits easily in 32GB unified memory
- **Egret Large/XLarge:** ~4-8GB VRAM, still fits but leaves less room for other processes
- **MLX VLM models:** ~4-8GB, efficient on Apple Silicon unified memory
- **Batch sizes:** Each increment of batch size adds ~500MB memory usage. With 32GB, batch sizes of 4-8 are safe.
- **Large documents (100+ pages):** Process in chunks if memory pressure is observed. Docling processes page-by-page internally but holds the full document model in memory.

### Speed benchmarks (approximate, M1 Pro)

| Document type | Pages | Heron + OcrMac | Egret Medium + OcrMac |
|---------------|-------|----------------|----------------------|
| Text-heavy PDF | 10 | ~5s | ~10s |
| Scanned PDF | 10 | ~15s | ~25s |
| Table-heavy PDF | 10 | ~20s | ~35s |
| DOCX | 10 | ~2s | ~2s (no layout model) |

*These are rough estimates. Actual times depend on document complexity, image count, and table density.*

### Troubleshooting

**MPS not available:**
```python
import torch
print(torch.backends.mps.is_available())
# If False, check PyTorch version: uv pip install --upgrade torch
```

**Model download failures:**
```bash
# Clear cache and retry
rm -rf ~/.cache/docling/models/
docling-tools models download
```

**Out of memory on large PDFs:**
- Reduce `layout_batch_size` and `ocr_batch_size` to 1-2
- Process fewer pages at a time
- Close other memory-intensive applications

**Slow first run:**
- Models are downloaded and compiled on first use. Subsequent runs will be faster.
- Pre-download models with `docling-tools models download`.

## Environment variables reference

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCLING_DEVICE` | `"auto"` | Device for inference: `auto`, `cpu`, `mps`, `cuda` |
| `DOCLING_NUM_THREADS` | System default | Number of CPU threads for inference |
| `DOCLING_CACHE_DIR` | `~/.cache/docling/models/` | Model cache directory |

## Supported input formats

| Format | Extension | Notes |
|--------|-----------|-------|
| PDF | `.pdf` | Full support: layout, OCR, tables, figures |
| DOCX | `.docx` | Direct parsing, no OCR needed |
| HTML | `.html` | Structure preserved |
| PPTX | `.pptx` | Slide content extraction |
| Images | `.png`, `.jpg`, `.tiff` | OCR-based extraction |
| Markdown | `.md` | Pass-through with structure parsing |
| AsciiDoc | `.adoc` | Structure parsing |
| CSV/Excel | `.csv`, `.xlsx` | Tabular data extraction |

## Integration with DocMan

The `DoclingBackend` in `src/docman/backends/docling_backend.py` uses Docling's `DocumentConverter`. To apply the M1 Pro optimized settings, either:

1. **Set environment variables** before running the extractor:
   ```bash
   export DOCLING_DEVICE=mps
   export DOCLING_NUM_THREADS=8
   loom processor --config configs/workers/doc_extractor.yaml \
                  --nats-url nats://localhost:4222 \
                  --workspace-dir /tmp/docman-workspace
   ```

2. **Configure via backend_config** in `doc_extractor.yaml`:
   ```yaml
   backend_config:
     workspace_dir: "/tmp/docman-workspace"
     device: "mps"
     num_threads: 8
     ocr_engine: "ocrmac"
     layout_batch_size: 4
     ocr_batch_size: 4
   ```
   *(Requires DoclingBackend to read these config values — see updated backend code.)*

3. **Modify DoclingBackend directly** to hardcode optimized defaults for your environment.

Option 2 is the recommended approach for flexibility across environments.
