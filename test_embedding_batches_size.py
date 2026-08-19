"""
Benchmark different EMBED_BATCH_SIZE values against the real upload pipeline.

For each batch size in [128, 256, 512, 1024] this script:
  1. Overrides settings.embed_batch_size in-process.
  2. Uploads sources/ARHO_DEScendants_scrap.docx through the FastAPI app.
  3. Reads the resulting `file_upload` event from rag_summary.json —
     the same metrics (duration + per-step seconds) the app already logs.
  4. Deletes the uploaded document via the API and re-uploads with the next
     batch size. The LAST iteration's document is kept.

Results are printed as a comparison table and appended as JSON Lines to
app/backend/embedding_batch_test_results.json.

Run from the repo root with the venv activated (Ollama must be running and
the backend's .env / database must be reachable):

    python test_embedding_batches_size.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app" / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from config import settings  # noqa: E402
from embedding_service import embedding_service  # noqa: E402
from rag_logging import DEFAULT_JSON_PATH  # noqa: E402

DOCX = ROOT / "sources" / "ARHO_DEScendants_scrap.docx"
RESULTS_PATH = ROOT / "app" / "backend" / "embedding_batch_test_results.json"
BATCH_SIZES = [128, 256, 512, 1024]


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as fh:
        return sum(1 for _ in fh)


def _read_new_events(path: Path, start_line: int):
    events = []
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh):
            if idx >= start_line and line.strip():
                events.append(json.loads(line))
    return events


def main() -> None:
    if not DOCX.exists():
        raise SystemExit(f"Missing test document: {DOCX}")

    results = []

    # Warm up the embedding model so the first iteration doesn't pay the
    # one-time model load cost.
    print("Warming up the embedding model...")
    embedding_service.embed_texts(["warmup"], batch_size=1)

    with TestClient(app) as client:
        for i, batch_size in enumerate(BATCH_SIZES):
            settings.embed_batch_size = batch_size
            print(f"\n=== batch_size={batch_size} ({i + 1}/{len(BATCH_SIZES)}) ===")

            lines_before = _count_lines(DEFAULT_JSON_PATH)
            with DOCX.open("rb") as fh:
                resp = client.post(
                    "/api/documents/upload",
                    files={
                        "file": (
                            DOCX.name,
                            fh,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                    },
                    data={"document_type": "journal"},
                )

            if resp.status_code != 200:
                print(f"Upload failed ({resp.status_code}): {resp.text}")
                results.append(
                    {"batch_size": batch_size, "error": resp.text[:500]}
                )
                continue

            payload = resp.json()
            document_id = payload.get("document_id")

            event = None
            for ev in _read_new_events(DEFAULT_JSON_PATH, lines_before):
                if ev.get("action_type") == "file_upload":
                    event = ev
            if event is None:
                print("WARNING: no file_upload event found in rag_summary.json")

            record = {
                "batch_size": batch_size,
                "document_id": document_id,
                "api_chunks": payload.get("chunks"),
                "api_person_records": payload.get("person_records"),
                "duration_seconds": (event or {}).get("duration_seconds"),
                "steps_taken": (event or {}).get("steps_taken", []),
            }
            results.append(record)
            with RESULTS_PATH.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")

            if i < len(BATCH_SIZES) - 1:
                del_resp = client.delete(f"/api/documents/{document_id}")
                print(
                    f"Deleted document {document_id} "
                    f"(status {del_resp.status_code})"
                )
            else:
                print(f"Keeping document {document_id} (final iteration)")

    print("\n=== RESULTS ===")
    print(
        f"{'batch':>7} | {'upload(s)':>9} | {'embed chunks(s)':>15} | "
        f"{'embed records(s)':>16} | {'chunks':>7}"
    )
    print("-" * 68)
    for r in results:
        if "error" in r:
            print(f"{r['batch_size']:>7} | ERROR: {r['error'][:60]}")
            continue
        steps = {s.get("step"): s.get("seconds", 0) for s in r["steps_taken"]}
        print(
            f"{r['batch_size']:>7} | {r['duration_seconds']:>9.2f} | "
            f"{steps.get('embed chunks', 0):>15.2f} | "
            f"{steps.get('embed + store ancestry records', 0):>16.2f} | "
            f"{str(r['api_chunks']):>7}"
        )
    print(f"\nFull results appended to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
